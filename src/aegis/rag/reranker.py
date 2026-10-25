"""Cross-Encoder Semantic Reranker and Bounded Context Assembler."""

from abc import ABC, abstractmethod
import math
import re
from typing import List, Optional, Tuple
from pydantic import BaseModel

from aegis.core.config import get_settings
from aegis.etl.vector_store import SearchResult


class BaseCrossEncoderReranker(ABC):
    """Abstract interface for cross-encoder reranking."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: List[SearchResult],
        top_k: int = 5,
    ) -> List[SearchResult]:
        """Rescore and rerank candidate passages against the query."""
        pass


class DeterministicCrossEncoderReranker(BaseCrossEncoderReranker):
    """Deterministic cross-encoder reranker for test and local execution.
    
    Computes cross-sentence token alignment, exact n-gram matching, and term proximity
    to re-evaluate semantic relevance with higher precision than bi-encoder vector similarity.
    """

    TOKEN_REGEX = re.compile(r"\b\w+\b")

    def _tokenize(self, text: str) -> List[str]:
        return [t.lower() for t in self.TOKEN_REGEX.findall(text)]

    def rerank(
        self,
        query: str,
        candidates: List[SearchResult],
        top_k: int = 5,
    ) -> List[SearchResult]:
        if not candidates or not query:
            return candidates[:top_k]

        q_tokens = self._tokenize(query)
        if not q_tokens:
            return candidates[:top_k]

        scored_candidates: List[Tuple[float, SearchResult]] = []

        for candidate in candidates:
            c_tokens = self._tokenize(candidate.text)
            c_text_lower = candidate.text.lower()

            # 1. Exact phrase match bonus
            exact_bonus = 2.0 if query.lower() in c_text_lower else 0.0

            # 2. Token overlap ratio
            matched_tokens = sum(1 for t in q_tokens if t in c_tokens)
            overlap_ratio = matched_tokens / len(q_tokens)

            # 3. Term proximity calculation (if multiple query tokens match)
            proximity_score = 0.0
            positions = [i for i, t in enumerate(c_tokens) if t in q_tokens]
            if len(positions) >= 2:
                span = positions[-1] - positions[0] + 1
                proximity_score = 1.0 / max(1.0, float(span) / len(positions))

            # Combine baseline similarity, overlap, and proximity
            base_score = candidate.score
            composite_score = (
                (0.3 * base_score)
                + (0.4 * overlap_ratio)
                + (0.2 * proximity_score)
                + (0.1 * exact_bonus)
            )

            res_copy = candidate.model_copy()
            res_copy.metadata["cross_encoder_score"] = round(composite_score, 4)
            scored_candidates.append((composite_score, res_copy))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored_candidates[:top_k]]


class BoundedContextAssembler:
    """Assembles retrieved evidence into a strictly bounded token budget with provenance tags."""

    def __init__(self, max_token_budget: int = 2000):
        self.max_token_budget = max_token_budget

    def assemble(self, passages: List[SearchResult]) -> Tuple[str, List[SearchResult]]:
        """Format passages with explicit citations and cap at max_token_budget."""
        if not passages:
            return "", []

        assembled_blocks: List[str] = []
        included_passages: List[SearchResult] = []
        current_tokens = 0

        for idx, p in enumerate(passages):
            # Format provenance tag
            prov_details = []
            if p.page_number is not None and p.page_number > 0:
                prov_details.append(f"Page {p.page_number}")
            if p.row_identifier:
                prov_details.append(f"Row {p.row_identifier}")
            if p.section_heading:
                prov_details.append(f"Section {p.section_heading}")

            prov_str = " | ".join(prov_details) if prov_details else "General"
            header = f"[Evidence #{idx + 1} | Source: {p.source_filename} | {prov_str} | DocID: {p.document_id}]"
            block = f"{header}\n{p.text}\n"

            # Estimate tokens (~4 characters per token)
            block_tokens = max(1, len(block) // 4)
            if current_tokens + block_tokens > self.max_token_budget and assembled_blocks:
                break

            assembled_blocks.append(block)
            included_passages.append(p)
            current_tokens += block_tokens

        assembled_context = "\n---\n".join(assembled_blocks)
        return assembled_context, included_passages
