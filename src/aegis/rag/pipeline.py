"""Zero-Trust RAG Pipeline Orchestrator with Independent Pre-LLM Authorization."""

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from aegis.core.audit import AuditEventType, get_audit_ledger
from aegis.core.security import UserContext
from aegis.core.telemetry import (
    RAG_QUERIES_TOTAL,
    RAG_RETRIEVAL_DURATION_SECONDS,
    RAG_GENERATION_DURATION_SECONDS,
    logger,
)
from aegis.etl.vector_store import SearchResult
from aegis.rag.generator import BaseLLMAdapter, get_llm_adapter
from aegis.rag.grounding import CitationVerificationResult, CitationVerifier, PromptInjectionShield
from aegis.rag.hybrid_retriever import HybridRetriever
from aegis.rag.reranker import BaseCrossEncoderReranker, BoundedContextAssembler, DeterministicCrossEncoderReranker


class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 5
    allow_query_rewriting: bool = True


class RAGQueryResponse(BaseModel):
    query: str
    answer: str
    is_abstained: bool = False
    citation_verification: CitationVerificationResult
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    retrieval_count: int = 0
    duration_seconds: float = 0.0


class ZeroTrustRAGPipeline:
    """Enterprise RAG pipeline where authorization is established independently of the LLM."""

    SYSTEM_PROMPT = (
        "You are an enterprise AI assistant operating under strict zero-trust governance. "
        "Answer the user query ONLY using the provided verified evidence blocks. "
        "Every single factual assertion MUST be explicitly cited with [Source: filename | Page: X] or [Source: filename | Row: Y]. "
        "If the provided evidence is missing, ambiguous, or contradictory, state strictly: "
        "'INSUFFICIENT_AUTHORIZED_EVIDENCE' and do not speculate."
    )

    def __init__(
        self,
        retriever: Optional[HybridRetriever] = None,
        reranker: Optional[BaseCrossEncoderReranker] = None,
        llm_adapter: Optional[BaseLLMAdapter] = None,
    ):
        self.retriever = retriever or HybridRetriever()
        self.reranker = reranker or DeterministicCrossEncoderReranker()
        self.context_assembler = BoundedContextAssembler(max_token_budget=2000)
        self.llm_adapter = llm_adapter or get_llm_adapter()
        self.injection_shield = PromptInjectionShield()
        self.citation_verifier = CitationVerifier()
        self.audit_ledger = get_audit_ledger()

    def query(
        self,
        request: RAGQueryRequest,
        user: UserContext,
        correlation_id: str = "rag_query",
    ) -> RAGQueryResponse:
        start_time = time.time()
        query_text = request.query.strip()

        # Step 1: Pre-Execution Security & Direct Injection Check
        if self.injection_shield.is_direct_injection(query_text):
            logger.warning(f"Direct prompt injection detected in query: {query_text[:60]}")
            self.audit_ledger.record_event(
                event_type=AuditEventType.PROMPT_INJECTION_DETECTED,
                tenant_id=user.tenant_id,
                actor_id=user.user_id,
                correlation_id=correlation_id,
                details={"query_preview": query_text[:60]},
            )
            RAG_QUERIES_TOTAL.labels(status="access_denied").inc()
            return RAGQueryResponse(
                query=query_text,
                answer="INSUFFICIENT_AUTHORIZED_EVIDENCE: Query rejected by security policy.",
                is_abstained=True,
                citation_verification=CitationVerificationResult(
                    is_valid=False, abstain_required=True, abstain_reason="Prompt injection detected."
                ),
                sources=[],
                duration_seconds=round(time.time() - start_time, 3),
            )

        # Step 2: Zero-Trust Pre-Retrieval Authorization & Hybrid Retrieval
        retrieval_start = time.time()
        candidates = self.retriever.retrieve(
            query=query_text,
            user=user,
            top_k=request.top_k * 2,
            correlation_id=correlation_id,
        )
        RAG_RETRIEVAL_DURATION_SECONDS.observe(time.time() - retrieval_start)

        if not candidates:
            # Safe abstention: zero authorized documents found
            RAG_QUERIES_TOTAL.labels(status="abstained").inc()
            self.audit_ledger.record_event(
                event_type=AuditEventType.ABSTENTION_TRIGGERED,
                tenant_id=user.tenant_id,
                actor_id=user.user_id,
                correlation_id=correlation_id,
                details={"reason": "No authorized candidate passages found."},
            )
            return RAGQueryResponse(
                query=query_text,
                answer="INSUFFICIENT_AUTHORIZED_EVIDENCE: No authorized documents available to answer this request.",
                is_abstained=True,
                citation_verification=CitationVerificationResult(
                    is_valid=False,
                    abstain_required=True,
                    abstain_reason="Zero authorized candidate documents found.",
                ),
                sources=[],
                duration_seconds=round(time.time() - start_time, 3),
            )

        # Step 3: Sanitize untrusted retrieved passages for indirect prompt injections
        sanitized_candidates: List[SearchResult] = []
        for candidate in candidates:
            sanitized_text, injection_found = self.injection_shield.sanitize_passage(candidate.text)
            if injection_found:
                self.audit_ledger.record_event(
                    event_type=AuditEventType.PROMPT_INJECTION_DETECTED,
                    tenant_id=user.tenant_id,
                    actor_id=user.user_id,
                    correlation_id=correlation_id,
                    details={"source_file": candidate.source_filename, "type": "indirect_document"},
                )
            c_copy = candidate.model_copy()
            c_copy.text = sanitized_text
            sanitized_candidates.append(c_copy)

        # Step 4: Cross-Encoder Reranking
        reranked = self.reranker.rerank(query_text, sanitized_candidates, top_k=request.top_k)

        # Step 5: Bounded Context Assembly
        context_str, included_evidence = self.context_assembler.assemble(reranked)

        # Step 6: Grounded Answer Generation
        gen_start = time.time()
        prompt_with_context = f"{context_str}\n\nUser Query: {query_text}\nAnswer with citations:"
        raw_answer = self.llm_adapter.generate(
            prompt=prompt_with_context,
            system_prompt=self.SYSTEM_PROMPT,
        )
        RAG_GENERATION_DURATION_SECONDS.observe(time.time() - gen_start)

        # Step 7: Citation Grounding & Verification
        verification = self.citation_verifier.verify(
            answer_text=raw_answer,
            retrieved_passages=included_evidence,
            tenant_id=user.tenant_id,
            actor_id=user.user_id,
            correlation_id=correlation_id,
        )

        is_abstained = "INSUFFICIENT_AUTHORIZED_EVIDENCE" in raw_answer or verification.abstain_required
        final_answer = raw_answer if not is_abstained else "INSUFFICIENT_AUTHORIZED_EVIDENCE: Evidence insufficient or contradictory."

        # Format sources for response (prevent leaking unrequested internal metadata)
        sources_meta = [
            {
                "source_filename": s.source_filename,
                "page_number": s.page_number,
                "row_identifier": s.row_identifier,
                "department": s.department,
                "score": s.score,
            }
            for s in included_evidence
        ]

        duration = round(time.time() - start_time, 3)
        status_label = "abstained" if is_abstained else "success"
        RAG_QUERIES_TOTAL.labels(status=status_label).inc()

        self.audit_ledger.record_event(
            event_type=AuditEventType.RAG_QUERY,
            tenant_id=user.tenant_id,
            actor_id=user.user_id,
            correlation_id=correlation_id,
            details={
                "query": query_text,
                "is_abstained": is_abstained,
                "sources_count": len(sources_meta),
                "duration": duration,
            },
        )

        return RAGQueryResponse(
            query=query_text,
            answer=final_answer,
            is_abstained=is_abstained,
            citation_verification=verification,
            sources=sources_meta,
            retrieval_count=len(included_evidence),
            duration_seconds=duration,
        )
