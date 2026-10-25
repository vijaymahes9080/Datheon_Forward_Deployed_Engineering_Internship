"""Structure-aware PDF extractor with page-level provenance."""

import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pypdf

from aegis.etl.parsers.base import BaseDocumentParser, DocumentPassage, ParsedDocument


class PDFDocumentParser(BaseDocumentParser):
    """Extracts text from PDF documents preserving page numbers and metadata."""

    def can_parse(self, filename: str) -> bool:
        return filename.lower().endswith(".pdf")

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
        raw_bytes: bytes
        if isinstance(file_path_or_bytes, bytes):
            raw_bytes = file_path_or_bytes
        else:
            with open(file_path_or_bytes, "rb") as f:
                raw_bytes = f.read()

        content_hash = self.compute_sha256(raw_bytes)
        document_id = f"doc_{content_hash[:16]}"
        passages: List[DocumentPassage] = []
        warnings: List[str] = []

        if len(raw_bytes) == 0:
            warnings.append("Document is empty (0 bytes).")
            return ParsedDocument(
                document_id=document_id,
                source_filename=source_filename,
                content_hash=content_hash,
                tenant_id=tenant_id,
                department=department,
                access_tier=access_tier,
                document_date=document_date or "",
                passages=[],
                warnings=warnings,
                metadata=extra_metadata or {},
            )

        try:
            stream = io.BytesIO(raw_bytes)
            reader = pypdf.PdfReader(stream)

            if reader.is_encrypted:
                try:
                    # Attempt empty password decryption
                    reader.decrypt("")
                except Exception:
                    warnings.append("PDF is password protected or encrypted; extraction aborted.")
                    return ParsedDocument(
                        document_id=document_id,
                        source_filename=source_filename,
                        content_hash=content_hash,
                        tenant_id=tenant_id,
                        department=department,
                        access_tier=access_tier,
                        document_date=document_date or "",
                        passages=[],
                        warnings=warnings,
                        metadata=extra_metadata or {},
                    )

            num_pages = len(reader.pages)
            if num_pages == 0:
                warnings.append("PDF has 0 pages.")

            for page_idx in range(num_pages):
                page_num = page_idx + 1  # 1-indexed provenance
                page = reader.pages[page_idx]
                try:
                    page_text = page.extract_text() or ""
                except Exception as ex:
                    warnings.append(f"Failed to extract text from page {page_num}: {str(ex)}")
                    page_text = ""

                cleaned = self.normalize_text(page_text)
                if cleaned:
                    passages.append(
                        DocumentPassage(
                            passage_id=f"{document_id}_p{page_num}",
                            text=cleaned,
                            page_number=page_num,
                            metadata={"page_count": num_pages},
                        )
                    )
                else:
                    warnings.append(f"Page {page_num} yielded no extractable text (may be image-only).")

        except Exception as e:
            warnings.append(f"Corrupted or invalid PDF structure: {str(e)}")

        return ParsedDocument(
            document_id=document_id,
            source_filename=source_filename,
            content_hash=content_hash,
            tenant_id=tenant_id,
            department=department,
            access_tier=access_tier,
            document_date=document_date or "",
            passages=passages,
            warnings=warnings,
            metadata=extra_metadata or {},
        )
