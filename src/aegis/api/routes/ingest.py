"""FastAPI Ingestion and Document Lifecycle Endpoints."""

import base64
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from aegis.api.deps import get_correlation_id, get_current_user
from aegis.core.database import DocumentRecord, IngestionJobRecord, get_db_session
from aegis.core.security import ClearanceLevel, Role, UserContext
from aegis.etl.pipeline import ETLPipeline, IngestionItem, IngestionManifest

router = APIRouter(prefix="/api/v1", tags=["Document Ingestion & Lifecycle"])
_pipeline = ETLPipeline()


class Base64DocumentPayload(BaseModel):
    filename: str
    content_base64: str
    department: str
    access_tier: int = ClearanceLevel.INTERNAL.value
    document_date: Optional[str] = None
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class BatchIngestionJSONRequest(BaseModel):
    documents: List[Base64DocumentPayload]


@router.post("/ingest", response_model=IngestionManifest, status_code=status.HTTP_200_OK)
async def ingest_documents_json(
    payload: BatchIngestionJSONRequest,
    user: UserContext = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """Ingest a batch of documents (PDF, CSV, MD) with provenance tracking and deduplication."""
    if not user.has_role(Role.OPERATOR.value, Role.ADMIN.value, Role.ENGINEER.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Insufficient privileges for document ingestion.",
        )

    items: List[IngestionItem] = []
    for doc in payload.documents:
        try:
            content_bytes = base64.b64decode(doc.content_base64)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid base64 encoding for file {doc.filename}",
            )

        items.append(
            IngestionItem(
                filename=doc.filename,
                content_bytes=content_bytes,
                tenant_id=user.tenant_id,
                department=doc.department,
                access_tier=doc.access_tier,
                document_date=doc.document_date,
                extra_metadata=doc.extra_metadata,
            )
        )

    manifest = _pipeline.ingest_batch(
        items=items,
        tenant_id=user.tenant_id,
        actor_id=user.user_id,
        correlation_id=correlation_id,
    )
    return manifest


@router.get("/ingest/jobs/{job_id}", status_code=status.HTTP_200_OK)
async def get_ingestion_job_status(
    job_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Retrieve execution manifest and status for an ingestion job."""
    db_gen = get_db_session()
    db = next(db_gen)
    try:
        job = (
            db.query(IngestionJobRecord)
            .filter(
                IngestionJobRecord.id == job_id,
                IngestionJobRecord.tenant_id == user.tenant_id,
            )
            .first()
        )
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ingestion job '{job_id}' not found.",
            )

        return {
            "job_id": job.id,
            "tenant_id": job.tenant_id,
            "status": job.status,
            "files_discovered": job.files_discovered,
            "files_accepted": job.files_accepted,
            "files_rejected": job.files_rejected,
            "chunks_created": job.chunks_created,
            "warnings": json.loads(job.warnings_json) if job.warnings_json else [],
            "failed_operations": json.loads(job.failed_ops_json) if job.failed_ops_json else [],
            "duration_seconds": job.duration_seconds,
            "started_at": job.started_at.isoformat() if job.started_at else None,
        }
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


@router.delete("/documents/{document_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: str,
    user: UserContext = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """Propagate document deletion to vector store and catalog."""
    if not user.has_role(Role.ADMIN.value, Role.OPERATOR.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin or Operator role required for deletion.",
        )

    deleted = _pipeline.delete_document(
        document_id=document_id,
        tenant_id=user.tenant_id,
        actor_id=user.user_id,
        correlation_id=correlation_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for tenant '{user.tenant_id}'.",
        )
    return {"status": "SUCCESS", "deleted_document_id": document_id}
