"""FastAPI Citation-Grounded RAG Endpoints."""

from fastapi import APIRouter, Depends, status
from aegis.api.deps import get_correlation_id, get_current_user
from aegis.core.security import UserContext
from aegis.rag.pipeline import RAGQueryRequest, RAGQueryResponse, ZeroTrustRAGPipeline

router = APIRouter(prefix="/api/v1/rag", tags=["Zero-Trust Enterprise RAG"])
_rag_pipeline = ZeroTrustRAGPipeline()


@router.post("/query", response_model=RAGQueryResponse, status_code=status.HTTP_200_OK)
async def execute_rag_query(
    request: RAGQueryRequest,
    user: UserContext = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """Execute citation-grounded RAG query enforcing tenant isolation, ACL boundaries, and abstention."""
    response = _rag_pipeline.query(
        request=request,
        user=user,
        correlation_id=correlation_id,
    )
    return response
