"""Base Parser interfaces and provenance data models."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class DocumentPassage(BaseModel):
    """Atomic text block extracted from a document with full source provenance."""
    passage_id: str
    text: str
    page_number: Optional[int] = None  # 1-indexed for PDF
    row_identifier: Optional[str] = None  # e.g., "row_12" for CSV
    section_heading: Optional[str] = None  # e.g., "# Security Policy > Incident Response" for MD
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    """Normalized document representation containing extracted passages and provenance."""
    document_id: str  # Deterministic SHA-256 hash
    source_filename: str
    content_hash: str
    tenant_id: str
    department: str
    access_tier: int  # 1 to 4
    document_date: str = Field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    parser_version: str = "1.0.0"
    passages: List[DocumentPassage] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def total_text(self) -> str:
        """Concatenated text of all passages."""
        return "\n\n".join(p.text for p in self.passages)


class BaseDocumentParser(ABC):
    """Abstract base class for format-specific document extraction."""

    @abstractmethod
    def can_parse(self, filename: str) -> bool:
        """Check if parser handles this file format."""
        pass

    @abstractmethod
    def parse(
        self,
        file_path_or_bytes: Union[str, Path, bytes],
        source_filename: str,
        tenant_id: str,
        department: str,
        access_tier: int = 2,
        document_date: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> ParsedDocument:
        """Parse raw document into structured passages with provenance."""
        pass

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Compute SHA-256 digest of raw byte content."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize unicode whitespace while preserving semantic paragraphs."""
        if not text:
            return ""
        # Normalize non-breaking spaces and tabs
        text = text.replace("\u00a0", " ").replace("\t", " ")
        lines = [line.strip() for line in text.splitlines()]
        # Collapse multi-blank lines into maximum 2 newlines (paragraph boundary)
        normalized_paragraphs = []
        current_p: List[str] = []
        for line in lines:
            if line:
                current_p.append(line)
            else:
                if current_p:
                    normalized_paragraphs.append(" ".join(current_p))
                    current_p = []
        if current_p:
            normalized_paragraphs.append(" ".join(current_p))
        return "\n\n".join(normalized_paragraphs)
