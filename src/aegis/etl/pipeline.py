"""Batch Ingestion Pipeline, Manifest Generation, and Document Lifecycle Management."""

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Union
import uuid
from pydantic import BaseModel, Field

from aegis.core.audit import AuditEventType, get_audit_ledger
from aegis.core.config import get_settings
from aegis.core.database import DocumentRecord, IngestionJobRecord, get_db_session
from aegis.core.telemetry import (
    ETL_CHUNKS_INDEXED_TOTAL,
    ETL_DOCUMENTS_TOTAL,
    ETL_DURATION_SECONDS,
    logger,
)
from aegis.etl.chunker import StructureAwareChunker
from aegis.etl.parsers.base import BaseDocumentParser, ParsedDocument
from aegis.etl.parsers.csv_parser import CSVDocumentParser
from aegis.etl.parsers.markdown_parser import MarkdownDocumentParser
from aegis.etl.parsers.pdf_parser import PDFDocumentParser
from aegis.etl.vector_store import BaseVectorStore, get_vector_store


class IngestionItem(BaseModel):
    """File payload submitted for ingestion."""
    filename: str
    content_bytes: bytes
    tenant_id: str
    department: str
    access_tier: int = 2
    document_date: Optional[str] = None
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestionManifest(BaseModel):
    """Complete auditable manifest of a batch ingestion operation."""
    job_id: str
    tenant_id: str
    status: str  # COMPLETED, PARTIAL_SUCCESS, FAILED
    files_discovered: int = 0
    files_accepted: int = 0
    files_rejected: int = 0
    chunks_created: int = 0
    chunks_indexed: int = 0
    warnings: List[str] = Field(default_factory=list)
    failed_operations: List[Dict[str, str]] = Field(default_factory=list)
    duration_seconds: float = 0.0
    config_version: str = "1.0.0"
    model_version: str = "1.0.0"
    started_at: str
    finished_at: str


class ETLPipeline:
    """Configurable enterprise ETL ingestion and document lifecycle orchestrator."""

    def __init__(
        self,
        vector_store: Optional[BaseVectorStore] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        settings = get_settings()
        self.vector_store = vector_store or get_vector_store()
        self.chunker = StructureAwareChunker(
            chunk_size=chunk_size or settings.CHUNK_SIZE,
            chunk_overlap=chunk_overlap or settings.CHUNK_OVERLAP,
        )
        self.parsers: List[BaseDocumentParser] = [
            PDFDocumentParser(),
            CSVDocumentParser(),
            MarkdownDocumentParser(),
        ]
        self.audit_ledger = get_audit_ledger()

    def get_parser_for_file(self, filename: str) -> Optional[BaseDocumentParser]:
        """Resolve parser based on file extension."""
        for parser in self.parsers:
            if parser.can_parse(filename):
                return parser
        return None

    def ingest_batch(
        self,
        items: List[IngestionItem],
        tenant_id: str,
        actor_id: str = "system",
        correlation_id: str = "etl_batch",
    ) -> IngestionManifest:
        """Process batch of document items with deduplication, provenance, and manifest reporting."""
        start_time = time.time()
        started_at = datetime.now(timezone.utc).isoformat()
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        manifest = IngestionManifest(
            job_id=job_id,
            tenant_id=tenant_id,
            status="PENDING",
            files_discovered=len(items),
            started_at=started_at,
            finished_at=started_at,
        )

        db_session_gen = get_db_session()
        db = next(db_session_gen)

        try:
            for item in items:
                parser = self.get_parser_for_file(item.filename)
                if not parser:
                    manifest.files_rejected += 1
                    err_msg = f"Unsupported file format for {item.filename}"
                    manifest.warnings.append(err_msg)
                    manifest.failed_operations.append({"file": item.filename, "reason": err_msg})
                    ETL_DOCUMENTS_TOTAL.labels(doc_type="unknown", status="rejected").inc()
                    continue

                try:
                    # Parse document
                    parsed_doc: ParsedDocument = parser.parse(
                        file_path_or_bytes=item.content_bytes,
                        source_filename=item.filename,
                        tenant_id=item.tenant_id,
                        department=item.department,
                        access_tier=item.access_tier,
                        document_date=item.document_date,
                        extra_metadata=item.extra_metadata,
                    )

                    if parsed_doc.warnings:
                        manifest.warnings.extend(
                            [f"[{item.filename}] {w}" for w in parsed_doc.warnings]
                        )

                    if not parsed_doc.passages:
                        manifest.files_rejected += 1
                        reason = f"No extractable passages in {item.filename}"
                        manifest.failed_operations.append({"file": item.filename, "reason": reason})
                        continue

                    # Deduplication check in persistent DB
                    existing_doc = (
                        db.query(DocumentRecord)
                        .filter(
                            DocumentRecord.tenant_id == item.tenant_id,
                            DocumentRecord.source_filename == item.filename,
                            DocumentRecord.status == "INDEXED",
                        )
                        .first()
                    )

                    if existing_doc and existing_doc.content_hash == parsed_doc.content_hash:
                        # Reprocessing identical source: do not create duplicates
                        manifest.files_accepted += 1
                        manifest.warnings.append(
                            f"[{item.filename}] Content unchanged (hash: {parsed_doc.content_hash[:8]}); skipped re-indexing."
                        )
                        continue

                    # If document exists but hash changed: update lifecycle (delete old chunks)
                    if existing_doc:
                        self.vector_store.delete_document(existing_doc.id, item.tenant_id)
                        existing_doc.status = "SUPERSEDED"
                        db.commit()

                    # Chunk document
                    chunks = self.chunker.chunk_document(parsed_doc)
                    manifest.chunks_created += len(chunks)

                    # Index chunks into Vector Store
                    indexed_count = self.vector_store.index_chunks(chunks)
                    manifest.chunks_indexed += indexed_count
                    manifest.files_accepted += 1

                    # Persist document record
                    doc_record = DocumentRecord(
                        id=parsed_doc.document_id,
                        tenant_id=item.tenant_id,
                        department=item.department,
                        access_tier=item.access_tier,
                        source_filename=item.filename,
                        content_hash=parsed_doc.content_hash,
                        status="INDEXED",
                        chunk_count=indexed_count,
                        warnings=json.dumps(parsed_doc.warnings),
                    )
                    db.merge(doc_record)
                    db.commit()

                    # Telemetry & Audit
                    ext = Path(item.filename).suffix.lstrip(".").lower()
                    ETL_DOCUMENTS_TOTAL.labels(doc_type=ext, status="success").inc()
                    ETL_CHUNKS_INDEXED_TOTAL.labels(doc_type=ext).inc(indexed_count)

                    self.audit_ledger.record_event(
                        event_type=AuditEventType.DOCUMENT_INGESTED,
                        tenant_id=item.tenant_id,
                        actor_id=actor_id,
                        correlation_id=correlation_id,
                        resource_id=parsed_doc.document_id,
                        details={
                            "filename": item.filename,
                            "chunks": indexed_count,
                            "department": item.department,
                            "access_tier": item.access_tier,
                        },
                    )

                except Exception as ex:
                    logger.error(f"Failed to ingest file {item.filename}: {str(ex)}")
                    manifest.files_rejected += 1
                    manifest.failed_operations.append(
                        {"file": item.filename, "reason": str(ex)}
                    )

            # Determine overall job status
            duration = round(time.time() - start_time, 3)
            manifest.duration_seconds = duration
            manifest.finished_at = datetime.now(timezone.utc).isoformat()

            if manifest.files_accepted == len(items) and len(items) > 0:
                manifest.status = "COMPLETED"
            elif manifest.files_accepted > 0:
                manifest.status = "PARTIAL_SUCCESS"
            else:
                manifest.status = "FAILED"

            # Record job in database
            job_record = IngestionJobRecord(
                id=manifest.job_id,
                tenant_id=manifest.tenant_id,
                status=manifest.status,
                files_discovered=manifest.files_discovered,
                files_accepted=manifest.files_accepted,
                files_rejected=manifest.files_rejected,
                chunks_created=manifest.chunks_created,
                warnings_json=json.dumps(manifest.warnings),
                failed_ops_json=json.dumps(manifest.failed_operations),
                duration_seconds=manifest.duration_seconds,
            )
            db.merge(job_record)
            db.commit()

            return manifest

        finally:
            try:
                next(db_session_gen)
            except StopIteration:
                pass

    def delete_document(
        self,
        document_id: str,
        tenant_id: str,
        actor_id: str = "system",
        correlation_id: str = "deletion",
    ) -> bool:
        """Propagate document deletion to vector store and catalog."""
        db_session_gen = get_db_session()
        db = next(db_session_gen)
        try:
            doc = (
                db.query(DocumentRecord)
                .filter(
                    DocumentRecord.id == document_id,
                    DocumentRecord.tenant_id == tenant_id,
                )
                .first()
            )
            if not doc:
                return False

            # Delete from vector store
            self.vector_store.delete_document(document_id, tenant_id)

            # Update database status
            doc.status = "DELETED"
            db.commit()

            self.audit_ledger.record_event(
                event_type=AuditEventType.DOCUMENT_DELETED,
                tenant_id=tenant_id,
                actor_id=actor_id,
                correlation_id=correlation_id,
                resource_id=document_id,
                details={"filename": doc.source_filename},
            )
            return True
        finally:
            try:
                next(db_session_gen)
            except StopIteration:
                pass
