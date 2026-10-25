"""Enterprise Telemetry: Structured JSON Logging, Correlation IDs, and Prometheus Metrics."""

import contextvars
import json
import logging
import sys
import time
from typing import Any, Dict, Optional
import uuid

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    REGISTRY,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# Correlation Context Variables
correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")
tenant_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="")
user_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


class SafeJSONFormatter(logging.Formatter):
    """JSON log formatter with sensitive credential masking."""

    SENSITIVE_KEYS = {
        "password",
        "secret",
        "token",
        "authorization",
        "api_key",
        "access_token",
        "secret_key",
        "prompt",
        "raw_text",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_ctx.get() or "system",
            "tenant_id": tenant_id_ctx.get() or "none",
            "user_id": user_id_ctx.get() or "none",
        }

        # Include extra fields passed in kwargs, sanitizing sensitive keys
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            for k, v in record.extra_fields.items():
                if any(sens in k.lower() for sens in self.SENSITIVE_KEYS):
                    log_data[k] = "[MASKED_SENSITIVE_DATA]"
                else:
                    log_data[k] = v

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_telemetry_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure root structured JSON logger."""
    logger = logging.getLogger("aegis")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Avoid duplicate handlers if reconfigured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(SafeJSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


logger = setup_telemetry_logging()

# =====================================================================
# Prometheus Metrics Registry (Zero Sensitive Data in Metric Labels)
# =====================================================================

HTTP_REQUESTS_TOTAL = Counter(
    "aegis_http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "aegis_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

ETL_DOCUMENTS_TOTAL = Counter(
    "aegis_etl_documents_total",
    "Total documents processed by ETL",
    ["doc_type", "status"],
)

ETL_CHUNKS_INDEXED_TOTAL = Counter(
    "aegis_etl_chunks_indexed_total",
    "Total chunks indexed into vector storage",
    ["doc_type"],
)

ETL_DURATION_SECONDS = Histogram(
    "aegis_etl_duration_seconds",
    "Time taken for document ingestion",
    ["doc_type"],
    buckets=(0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0),
)

RAG_QUERIES_TOTAL = Counter(
    "aegis_rag_queries_total",
    "Total RAG search queries executed",
    ["status"],  # success, abstained, access_denied, error
)

RAG_RETRIEVAL_DURATION_SECONDS = Histogram(
    "aegis_rag_retrieval_duration_seconds",
    "RAG hybrid retrieval and reranking latency",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)

RAG_GENERATION_DURATION_SECONDS = Histogram(
    "aegis_rag_generation_duration_seconds",
    "RAG LLM generation latency",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)

RAG_CITATIONS_TOTAL = Counter(
    "aegis_rag_citations_total",
    "Outcome of citation grounding validation",
    ["outcome"],  # verified, rejected, hallucinated
)

AGENT_OPERATIONS_TOTAL = Counter(
    "aegis_agent_operations_total",
    "Total ERP/CRM agent operations",
    ["tool_name", "status"],  # success, failure, pending_approval, policy_denied
)

AGENT_APPROVALS_TOTAL = Counter(
    "aegis_agent_approvals_total",
    "Total human-in-the-loop approvals processed",
    ["decision"],  # approved, rejected, expired, invalid
)

AGENT_RETRIES_TOTAL = Counter(
    "aegis_agent_retries_total",
    "Total retry attempts made by agent operations",
    ["tool_name"],
)


def get_prometheus_metrics() -> bytes:
    """Generate latest Prometheus metrics output."""
    return generate_latest(REGISTRY)
