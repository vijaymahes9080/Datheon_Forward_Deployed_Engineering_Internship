"""Prompt Injection Defense, Untrusted Passage Sanitizer, and Citation Verification Subsystem."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from aegis.core.audit import AuditEventType, get_audit_ledger
from aegis.core.telemetry import RAG_CITATIONS_TOTAL, logger
from aegis.etl.vector_store import SearchResult


class CitationVerificationResult(BaseModel):
    """Outcome of citation and evidence grounding verification."""
    is_valid: bool
    grounded_citations: List[Dict[str, Any]] = Field(default_factory=list)
    fabricated_citations: List[Dict[str, Any]] = Field(default_factory=list)
    abstain_required: bool = False
    abstain_reason: Optional[str] = None


class PromptInjectionShield:
    """Detects and neutralizes direct and indirect prompt injection attempts."""

    ADVERSARIAL_PATTERNS = [
        re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
        re.compile(r"system\s+(instruction\s+)?override", re.IGNORECASE),
        re.compile(r"disclose\s+(all\s+)?(confidential|secret|password|salary|salaries)", re.IGNORECASE),
        re.compile(r"print\s+the\s+word\s+pwned", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+(in\s+)?developer\s+mode", re.IGNORECASE),
        re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
        re.compile(r"bypass\s+(access\s+control|security|clearance)", re.IGNORECASE),
    ]

    def is_direct_injection(self, text: str) -> bool:
        """Check if user prompt contains direct prompt injection attack."""
        return any(pattern.search(text) for pattern in self.ADVERSARIAL_PATTERNS)

    def sanitize_passage(self, text: str) -> Tuple[str, bool]:
        """Neutralize indirect injection instructions inside untrusted retrieved documents."""
        sanitized = text
        detected = False
        for pattern in self.ADVERSARIAL_PATTERNS:
            if pattern.search(sanitized):
                detected = True
                sanitized = pattern.sub("[REDACTED_ADVERSARIAL_INSTRUCTION]", sanitized)
        return sanitized, detected


class CitationVerifier:
    """Validates citations against genuine retrieved evidence passages."""

    # Matches citations in format: [Source: filename | Page: X | Row: Y] or [filename#Page X]
    CITATION_REGEX = re.compile(
        r"\[(?:Source:\s*)?([a-zA-Z0-9_\-\.]+)(?:\s*\|\s*(?:Page|Row|Section):\s*([0-9a-zA-Z_\-\.]+))?[^\]]*\]"
    )

    def __init__(self):
        self.audit_ledger = get_audit_ledger()

    def extract_citations(self, text: str) -> List[Tuple[str, Optional[str]]]:
        """Extract (filename, page_or_row) tuples from generated response text."""
        matches = self.CITATION_REGEX.findall(text)
        return [(m[0].strip(), m[1].strip() if m[1] else None) for m in matches]

    def verify(
        self,
        answer_text: str,
        retrieved_passages: List[SearchResult],
        tenant_id: str,
        actor_id: str = "system",
        correlation_id: str = "grounding",
    ) -> CitationVerificationResult:
        """Verify that every citation in the answer corresponds to actual evidence."""
        if not retrieved_passages:
            return CitationVerificationResult(
                is_valid=False,
                abstain_required=True,
                abstain_reason="INSUFFICIENT_AUTHORIZED_EVIDENCE: No authorized documents retrieved.",
            )

        citations = self.extract_citations(answer_text)
        if not citations:
            # If the answer provides facts without any citation, check if evidence is actually present
            return CitationVerificationResult(
                is_valid=False,
                abstain_required=False,
                abstain_reason="Answer lacks explicit source citations.",
            )

        # Index available evidence
        evidence_index: Dict[str, Set[str]] = {}
        for p in retrieved_passages:
            fn = p.source_filename.lower()
            if fn not in evidence_index:
                evidence_index[fn] = set()
            if p.page_number is not None:
                evidence_index[fn].add(str(p.page_number))
            if p.row_identifier:
                evidence_index[fn].add(str(p.row_identifier).lower())
                evidence_index[fn].add(str(p.row_identifier).replace("row_", "").lower())

        grounded: List[Dict[str, Any]] = []
        fabricated: List[Dict[str, Any]] = []

        for fn, prov in citations:
            fn_lower = fn.lower()
            if fn_lower not in evidence_index:
                # Fabricated filename
                fabricated.append({"filename": fn, "provenance": prov, "reason": "Unknown filename"})
                RAG_CITATIONS_TOTAL.labels(outcome="hallucinated").inc()
            else:
                if prov is not None and prov.lower() not in evidence_index[fn_lower] and "page " + prov.lower() not in evidence_index[fn_lower]:
                    # Fabricated page / row within known document
                    fabricated.append(
                        {
                            "filename": fn,
                            "provenance": prov,
                            "reason": f"Provenance {prov} not in retrieved passages for {fn}",
                        }
                    )
                    RAG_CITATIONS_TOTAL.labels(outcome="rejected").inc()
                else:
                    grounded.append({"filename": fn, "provenance": prov})
                    RAG_CITATIONS_TOTAL.labels(outcome="verified").inc()

        is_valid = len(fabricated) == 0 and len(grounded) > 0

        self.audit_ledger.record_event(
            event_type=AuditEventType.CITATION_VALIDATED if is_valid else AuditEventType.CITATION_FAILED,
            tenant_id=tenant_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            details={
                "grounded_count": len(grounded),
                "fabricated_count": len(fabricated),
                "is_valid": is_valid,
            },
        )

        return CitationVerificationResult(
            is_valid=is_valid,
            grounded_citations=grounded,
            fabricated_citations=fabricated,
            abstain_required=len(grounded) == 0,
            abstain_reason="INSUFFICIENT_AUTHORIZED_EVIDENCE: All cited sources were invalid or fabricated."
            if len(grounded) == 0
            else None,
        )
