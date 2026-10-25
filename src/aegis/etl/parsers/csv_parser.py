"""Tabular CSV parser with row-level provenance and structured header preservation."""

import csv
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from aegis.etl.parsers.base import BaseDocumentParser, DocumentPassage, ParsedDocument


class CSVDocumentParser(BaseDocumentParser):
    """Parses tabular CSV files into row-level passages with header schema preservation."""

    def can_parse(self, filename: str) -> bool:
        return filename.lower().endswith(".csv")

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
            warnings.append("CSV document is empty (0 bytes).")
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

        # Decoding with graceful fallbacks
        text_content = ""
        for encoding in ["utf-8-sig", "utf-8", "latin-1"]:
            try:
                text_content = raw_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not text_content:
            warnings.append("Failed to decode CSV bytes with supported encodings (UTF-8, Latin-1).")
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
            stream = io.StringIO(text_content)
            reader = csv.reader(stream)
            headers: List[str] = []
            
            try:
                headers = next(reader)
            except StopIteration:
                warnings.append("CSV contains no rows.")
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

            headers = [h.strip() for h in headers]
            row_idx = 1  # 1-indexed for data rows (header is row 0)

            for row in reader:
                if not row or all(not cell.strip() for cell in row):
                    continue

                if len(row) != len(headers):
                    warnings.append(
                        f"Row {row_idx} column mismatch: expected {len(headers)} columns, got {len(row)}."
                    )

                # Format record into semantic key-value pairs for optimal embedding & retrieval
                fields_text: List[str] = []
                record_dict: Dict[str, Any] = {}
                for col_idx, col_name in enumerate(headers):
                    val = row[col_idx].strip() if col_idx < len(row) else ""
                    fields_text.append(f"{col_name}: {val}")
                    record_dict[col_name] = val

                passage_text = f"Record [Row {row_idx}]: " + " | ".join(fields_text)
                passages.append(
                    DocumentPassage(
                        passage_id=f"{document_id}_row{row_idx}",
                        text=passage_text,
                        row_identifier=f"row_{row_idx}",
                        metadata={
                            "row_index": row_idx,
                            "headers": headers,
                            "record": record_dict,
                        },
                    )
                )
                row_idx += 1

            if not passages:
                warnings.append("CSV contained header but zero data records.")

        except Exception as e:
            warnings.append(f"CSV parsing error: {str(e)}")

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
            metadata={"headers": headers, **(extra_metadata or {})},
        )
