"""Zero-Trust Pre-Retrieval Authorization Boundary, BM25 Lexical Retrieval, and Reciprocal Rank Fusion."""

from collections import Counter
import math
import re
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from aegis.core.audit import AuditEventType, get_audit_ledger
from aegis.core.config import get_settings
from aegis.core.security import Role, UserContext
from aegis.core.telemetry import RAG_QUERIES_TOTAL, RAG_RETRIEVAL_DURATION_SECONDS, logger
from aegis.etl.vector_store import BaseVectorStore, SearchResult, get_vector_store


class BM25Retriever:
    """Okapi BM25 Lexical Retriever for exact token, SKU, and code keyword matching."""

    TOKEN_REGEX = re.compile(r"\b\w+\b")

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

    def tokenize(self, text: str) -> List[str]:
        return [t.lower() for t in self.TOKEN_REGEX.findall(text)]

    def score_corpus(
        self,
        query: str,
        corpus_results: List[SearchResult],
    ) -> List[SearchResult]:
        """Compute BM25 scores across candidate documents."""
        query_tokens = self.tokenize(query)
        if not query_tokens or not corpus_results:
            return corpus_results

        n_docs = len(corpus_results)
        doc_tokens = [self.tokenize(r.text) for r in corpus_results]
        doc_lengths = [len(t) for t in doc_tokens]
        avg_doc_len = sum(doc_lengths) / max(1, n_docs)

        # Document frequencies for query terms
        df: Dict[str, int] = Counter()
        for tokens in doc_tokens:
            unique_terms = set(tokens)
            for t in query_tokens:
                if t in unique_terms:
                    df[t] += 1

        # Calculate BM25 score for each document
        scored_results: List[SearchResult] = []
        for idx, (res, tokens, doc_len) in enumerate(zip(corpus_results, doc_tokens, doc_lengths)):
            tf_counter = Counter(tokens)
            bm25_score = 0.0
            for term in query_tokens:
                if term in tf_counter:
                    tf = tf_counter[term]
                    term_df = df.get(term, 0)
                    idf = math.log((n_docs - term_df + 0.5) / (term_df + 0.5) + 1.0)
                    numerator = tf * (self.k1 + 1.0)
                    denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / max(1.0, avg_doc_len)))
                    bm25_score += idf * (numerator / denominator)

            # Create updated SearchResult with BM25 score
            res_copy = res.model_copy()
            res_copy.metadata["bm25_score"] = bm25_score
            scored_results.append(res_copy)

        scored_results.sort(key=lambda r: r.metadata.get("bm25_score", 0.0), reverse=True)
        return scored_results


class HybridRetriever:
    """Combines Dense Vector and Lexical BM25 search via Reciprocal Rank Fusion with Pre-Retrieval ACLs."""

    def __init__(
        self,
        vector_store: Optional[BaseVectorStore] = None,
        rrf_k: int = 60,
    ):
        settings = get_settings()
        self.vector_store = vector_store or get_vector_store()
        self.bm25 = BM25Retriever()
        self.rrf_k = rrf_k
        self.min_similarity = settings.SIMILARITY_THRESHOLD
        self.audit_ledger = get_audit_ledger()

    def _resolve_allowed_departments(self, user: UserContext) -> List[str]:
        """Resolve departments user is authorized to query based on RBAC and clearance."""
        if user.has_role(Role.ADMIN.value, Role.AUDITOR.value):
            # Admins/Auditors within the tenant have broader visibility across tenant departments
            return []  # Empty means all departments within the tenant
        # Regular users only search their department plus general
        return [user.department, "general"]

    def retrieve(
        self,
        query: str,
        user: UserContext,
        top_k: int = 5,
        correlation_id: str = "retrieval",
    ) -> List[SearchResult]:
        """Authorized Hybrid Search with zero-trust pre-retrieval boundary."""
        if not user or not user.tenant_id:
            logger.warning("Unauthenticated retrieval query rejected at security boundary")
            return []

        allowed_depts = self._resolve_allowed_departments(user)

        # 1. Vector Search (dense embeddings) with minimum similarity threshold
        query_vec = self.vector_store.embedding_provider.embed_text(query)
        dense_candidates = self.vector_store.search(
            query_vector=query_vec,
            tenant_id=user.tenant_id,
            allowed_departments=allowed_depts,
            max_clearance=user.clearance_level,
            top_k=top_k * 3,
            min_score=self.min_similarity,
        )

        if not dense_candidates:
            return []

        # 2. Lexical Search (BM25) over candidate pool
        lexical_candidates = self.bm25.score_corpus(query, dense_candidates)

        # 3. Reciprocal Rank Fusion (RRF)
        # RRF score: 1 / (k + rank_dense) + 1 / (k + rank_lexical)
        rrf_scores: Dict[str, float] = {}
        candidate_map: Dict[str, SearchResult] = {}

        for rank, res in enumerate(dense_candidates):
            cid = res.chunk_id
            candidate_map[cid] = res
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (self.rrf_k + rank + 1))

        for rank, res in enumerate(lexical_candidates):
            cid = res.chunk_id
            candidate_map[cid] = res
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (self.rrf_k + rank + 1))

        # Rank fused results
        sorted_ids = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        fused_results: List[SearchResult] = []

        for cid in sorted_ids[:top_k]:
            res = candidate_map[cid].model_copy()
            res.metadata["rrf_score"] = rrf_scores[cid]
            # Ensure final candidate satisfies user clearance and tenant
            if user.can_access_document(res.tenant_id, res.department, res.access_tier):
                fused_results.append(res)

        return fused_results
