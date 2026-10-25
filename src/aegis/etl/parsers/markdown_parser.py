"""Hierarchical Markdown parser with section breadcrumb preservation."""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from aegis.etl.parsers.base import BaseDocumentParser, DocumentPassage, ParsedDocument


class MarkdownDocumentParser(BaseDocumentParser):
    """Parses Markdown documents preserving hierarchical section breadcrumbs."""

    HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.+)$")

    def can_parse(self, filename: str) -> bool:
        return filename.lower().endswith((".md", ".markdown"))

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
            warnings.append("Markdown document is empty (0 bytes).")
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

        text_content = ""
        for encoding in ["utf-8", "utf-8-sig", "latin-1"]:
            try:
                text_content = raw_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not text_content:
            warnings.append("Failed to decode Markdown bytes.")
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

        # Parse sections based on headings
        lines = text_content.splitlines()
        heading_stack: List[Tuple[int, str]] = []  # (level, title)
        current_section_lines: List[str] = []
        section_idx = 1

        def get_current_breadcrumb() -> str:
            if not heading_stack:
                return "Introduction"
            return " > ".join(f"{'#' * level} {title}" for level, title in heading_stack)

        def flush_current_section():
            nonlocal section_idx, current_section_lines
            content = self.normalize_text("\n".join(current_section_lines))
            if content:
                breadcrumb = get_current_breadcrumb()
                passages.append(
                    DocumentPassage(
                        passage_id=f"{document_id}_sec{section_idx}",
                        text=f"[{breadcrumb}]\n{content}",
                        section_heading=breadcrumb,
                        metadata={"section_index": section_idx, "breadcrumb": breadcrumb},
                    )
                )
                section_idx += 1
            current_section_lines = []

        for line in lines:
            match = self.HEADING_REGEX.match(line)
            if match:
                flush_current_section()
                level = len(match.group(1))
                title = match.group(2).strip()

                # Pop headings of equal or deeper level
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))
            else:
                current_section_lines.append(line)

        flush_current_section()

        if not passages:
            warnings.append("Document contained no readable text content.")

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
