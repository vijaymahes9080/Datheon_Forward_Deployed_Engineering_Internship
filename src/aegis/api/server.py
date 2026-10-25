"""FastAPI Application Entrypoint and Lifecycle Orchestration."""

from contextlib import asynccontextmanager
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aegis.api.routes import health
from aegis.core.config import get_settings
from aegis.core.database import init_db
from aegis.core.telemetry import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    correlation_id_ctx,
    logger,
    setup_telemetry_logging,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown hooks."""
    settings = get_settings()
    setup_telemetry_logging(settings.LOG_LEVEL)
    logger.info("Initializing AegisAI Enterprise Gateway runtime...")
    settings.ensure_directories()
    init_db()
    logger.info("Persistence and storage initialized.")
    yield
    logger.info("Graceful shutdown completed.")


def create_app() -> FastAPI:
    """Build and configure production-hardened FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AegisAI Enterprise Gateway",
        description="Zero-Trust Enterprise AI Integration Engine API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS policy
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Request Correlation and Prometheus Latency Middleware
    @app.middleware("http")
    async def telemetry_middleware(request: Request, call_next):
        start_time = time.time()
        cid = request.headers.get("X-Correlation-ID", "")
        if cid:
            correlation_id_ctx.set(cid)

        endpoint = request.url.path
        method = request.method

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Filter out metric scraping from high-frequency metric observation
            if endpoint != "/metrics":
                HTTP_REQUESTS_TOTAL.labels(
                    method=method, endpoint=endpoint, status_code=str(response.status_code)
                ).inc()
                HTTP_REQUEST_DURATION_SECONDS.labels(
                    method=method, endpoint=endpoint
                ).observe(duration)

            if cid:
                response.headers["X-Correlation-ID"] = cid
            return response

        except Exception as exc:
            duration = time.time() - start_time
            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, status_code="500"
            ).inc()
            logger.error(f"Unhandled exception at {method} {endpoint}: {str(exc)}")
            return JSONResponse(
                status_code=500,
                content={"error": "INTERNAL_SERVER_ERROR", "message": "An internal error occurred."},
            )

    # Mount routers
    app.include_router(health.router)
    from aegis.api.routes import ingest, search, rag, agent
    app.include_router(ingest.router)
    app.include_router(search.router)
    app.include_router(rag.router)
    app.include_router(agent.router)

    return app


app = create_app()
