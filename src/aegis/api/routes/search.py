"""FastAPI Authorized Hybrid Search Endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from aegis.api.deps import get_correlation_id, get_current_user
from aegis.core.security import UserContext
from aegis.rag.hybrid_retriever import HybridRetriever

router = APIRouter(prefix="/api/v1", tags=["Authorized Search"])
_retriever = HybridRetriever()


class SearchQueryRequest(BaseModel):
    query: str = Field(description="Search text or query terms", min_length=2, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchCandidateResponse(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    tenant_id: str
    department: str
    access_tier: int
    source_filename: str
    document_date: str
    page_number: Optional[int] = None
    row_identifier: Optional[str] = None
    section_heading: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    total_found: int
    results: List[SearchCandidateResponse]


@router.post("/search", response_model=SearchResponse, status_code=status.HTTP_200_OK)
async def authorized_search(
    request: SearchQueryRequest,
    user: UserContext = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """Execute authorized hybrid (dense + lexical BM25) search with zero-trust ACL boundary."""
    results = _retriever.retrieve(
        query=request.query,
        user=user,
        top_k=request.top_k,
        correlation_id=correlation_id,
    )

    candidates = [
        SearchCandidateResponse(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            text=r.text,
            score=round(r.score, 4),
            tenant_id=r.tenant_id,
            department=r.department,
            access_tier=r.access_tier,
            source_filename=r.source_filename,
            document_date=r.document_date,
            page_number=r.page_number,
            row_identifier=r.row_identifier,
            section_heading=r.section_heading,
        )
        for r in results
    ]

    return SearchResponse(
        query=request.query,
        total_found=len(candidates),
        results=candidates,
    )
