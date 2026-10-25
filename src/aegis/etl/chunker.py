"""Structure-aware chunking engine with deterministic content-hash deduplication."""

import hashlib
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from aegis.etl.parsers.base import DocumentPassage, ParsedDocument


class Chunk(BaseModel):
    """Atomic indexable chunk retaining complete provenance and ACL boundaries."""
    chunk_id: str
    text: str
    content_hash: str
    token_count: int
    tenant_id: str
    document_id: str
    department: str
    access_tier: int
    source_filename: str
    document_date: str
    page_number: Optional[int] = None
    row_identifier: Optional[str] = None
    section_heading: Optional[str] = None
    parser_version: str = "1.0.0"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_vector_metadata(self) -> Dict[str, Any]:
        """Convert chunk attributes to flat dictionary for vector store filtering."""
        return {
            "chunk_id": self.chunk_id,
            "tenant_id": self.tenant_id,
            "document_id": self.document_id,
            "department": self.department,
            "access_tier": int(self.access_tier),
            "source_filename": self.source_filename,
            "document_date": self.document_date or "",
            "page_number": int(self.page_number) if self.page_number is not None else -1,
            "row_identifier": self.row_identifier or "",
            "section_heading": self.section_heading or "",
            "content_hash": self.content_hash,
            "parser_version": self.parser_version,
        }


class StructureAwareChunker:
    """Chunks structured passages while preserving section and sentence boundaries."""

    SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+")

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @staticmethod
    def compute_sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _split_into_sentences(self, text: str) -> List[str]:
        return [s.strip() for s in self.SENTENCE_SPLIT_REGEX.split(text) if s.strip()]

    def chunk_passage(self, passage: DocumentPassage, doc: ParsedDocument) -> List[Chunk]:
        """Chunk a single passage into one or more chunks with boundary awareness."""
        text = passage.text.strip()
        if not text:
            return []

        chunks: List[Chunk] = []
        provenance_tag = (
            f"p{passage.page_number}"
            if passage.page_number is not None
            else (passage.row_identifier or "sec")
        )

        # If text fits comfortably in target size, keep as single coherent chunk
        if len(text) <= self.chunk_size:
            content_hash = self.compute_sha256(text)
            chunk_id = f"{doc.document_id}_{provenance_tag}_c0"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=text,
                    content_hash=content_hash,
                    token_count=max(1, len(text) // 4),
                    tenant_id=doc.tenant_id,
                    document_id=doc.document_id,
                    department=doc.department,
                    access_tier=doc.access_tier,
                    source_filename=doc.source_filename,
                    document_date=doc.document_date,
                    page_number=passage.page_number,
                    row_identifier=passage.row_identifier,
                    section_heading=passage.section_heading,
                    parser_version=doc.parser_version,
                    metadata=passage.metadata,
                )
            )
            return chunks

        # Text exceeds chunk_size: split on sentence boundaries
        sentences = self._split_into_sentences(text)
        current_chunk_sentences: List[str] = []
        current_len = 0
        chunk_idx = 0

        for sentence in sentences:
            sentence_len = len(sentence)
            if current_len + sentence_len > self.chunk_size and current_chunk_sentences:
                chunk_text = " ".join(current_chunk_sentences)
                content_hash = self.compute_sha256(chunk_text)
                chunk_id = f"{doc.document_id}_{provenance_tag}_c{chunk_idx}"
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        text=chunk_text,
                        content_hash=content_hash,
                        token_count=max(1, len(chunk_text) // 4),
                        tenant_id=doc.tenant_id,
                        document_id=doc.document_id,
                        department=doc.department,
                        access_tier=doc.access_tier,
                        source_filename=doc.source_filename,
                        document_date=doc.document_date,
                        page_number=passage.page_number,
                        row_identifier=passage.row_identifier,
                        section_heading=passage.section_heading,
                        parser_version=doc.parser_version,
                        metadata=passage.metadata,
                    )
                )
                chunk_idx += 1

                # Retain overlap sentences
                overlap_sentences: List[str] = []
                overlap_len = 0
                for s in reversed(current_chunk_sentences):
                    if overlap_len + len(s) <= self.chunk_overlap:
                        overlap_sentences.insert(0, s)
                        overlap_len += len(s)
                    else:
                        break
                current_chunk_sentences = overlap_sentences
                current_len = overlap_len

            current_chunk_sentences.append(sentence)
            current_len += sentence_len

        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences)
            content_hash = self.compute_sha256(chunk_text)
            chunk_id = f"{doc.document_id}_{provenance_tag}_c{chunk_idx}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=chunk_text,
                    content_hash=content_hash,
                    token_count=max(1, len(chunk_text) // 4),
                    tenant_id=doc.tenant_id,
                    document_id=doc.document_id,
                    department=doc.department,
                    access_tier=doc.access_tier,
                    source_filename=doc.source_filename,
                    document_date=doc.document_date,
                    page_number=passage.page_number,
                    row_identifier=passage.row_identifier,
                    section_heading=passage.section_heading,
                    parser_version=doc.parser_version,
                    metadata=passage.metadata,
                )
            )

        return chunks

    def chunk_document(self, doc: ParsedDocument) -> List[Chunk]:
        """Process all passages in document into chunks."""
        all_chunks: List[Chunk] = []
        for passage in doc.passages:
            all_chunks.extend(self.chunk_passage(passage, doc))
        return all_chunks
