"""Health, Readiness, and Prometheus Telemetry Endpoints."""

from fastapi import APIRouter, Response, status
from aegis.core.database import get_engine
from aegis.core.telemetry import CONTENT_TYPE_LATEST, get_prometheus_metrics
from aegis.etl.vector_store import get_vector_store

router = APIRouter(tags=["Health & Telemetry"])


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe():
    """Kubernetes liveness probe: returns 200 if process is alive."""
    return {"status": "ALIVE", "service": "aegisai-enterprise-gateway"}


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_probe():
    """Kubernetes readiness probe: validates database and vector store connectivity."""
    db_ok = False
    chroma_ok = False

    try:
        engine = get_engine()
        with engine.connect() as conn:
            db_ok = True
    except Exception:
        db_ok = False

    try:
        vs = get_vector_store()
        count = vs.collection.count()
        chroma_ok = True
    except Exception:
        chroma_ok = False

    if db_ok and chroma_ok:
        return {
            "status": "READY",
            "components": {"database": "UP", "vector_store": "UP"},
        }
    return Response(
        content='{"status":"UNHEALTHY","components":{"database":"DOWN","vector_store":"DOWN"}}',
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        media_type="application/json",
    )


@router.get("/metrics")
async def metrics_endpoint():
    """Scrape endpoint for Prometheus monitoring."""
    metrics_data = get_prometheus_metrics()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
