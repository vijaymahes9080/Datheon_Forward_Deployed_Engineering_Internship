"""Database Persistence Layer: SQLAlchemy Models and Session Management."""

from datetime import datetime, timezone
import json
from typing import Any, Dict, Generator, Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from aegis.core.config import get_settings


class Base(DeclarativeBase):
    """Base model class."""
    pass


class DocumentRecord(Base):
    """Catalog of ingested enterprise documents."""
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True)  # Deterministic SHA-256 or UUID
    tenant_id = Column(String(64), index=True, nullable=False)
    department = Column(String(32), index=True, nullable=False)
    access_tier = Column(Integer, index=True, nullable=False)  # 1-4
    source_filename = Column(String(255), nullable=False)
    content_hash = Column(String(64), index=True, nullable=False)
    parser_version = Column(String(32), default="1.0.0")
    status = Column(String(32), default="INDEXED")  # INDEXED, DELETED, FAILED
    chunk_count = Column(Integer, default=0)
    warnings = Column(Text, default="[]")  # JSON string of warnings
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class IngestionJobRecord(Base):
    """Manifest of asynchronous batch ingestion runs."""
    __tablename__ = "ingestion_jobs"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), index=True, nullable=False)
    status = Column(String(32), default="PENDING")  # PENDING, RUNNING, COMPLETED, PARTIAL_SUCCESS, FAILED
    files_discovered = Column(Integer, default=0)
    files_accepted = Column(Integer, default=0)
    files_rejected = Column(Integer, default=0)
    chunks_created = Column(Integer, default=0)
    warnings_json = Column(Text, default="[]")
    failed_ops_json = Column(Text, default="[]")
    duration_seconds = Column(Float, default=0.0)
    config_version = Column(String(32), default="1.0.0")
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)


class ApprovalRecord(Base):
    """Human-in-the-loop approval requests for sensitive agent operations."""
    __tablename__ = "approval_records"

    id = Column(String(64), primary_key=True)  # Unique approval token/ID
    operation = Column(String(64), nullable=False)
    arg_hash = Column(String(64), nullable=False)  # SHA-256 of canonical arguments
    arguments_json = Column(Text, nullable=False)
    actor_id = Column(String(64), nullable=False)
    tenant_id = Column(String(64), index=True, nullable=False)
    status = Column(String(32), default="PENDING")  # PENDING, APPROVED, REJECTED, EXPIRED
    nonce = Column(String(64), unique=True, nullable=False)  # Single-use anti-replay nonce
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    decided_at = Column(DateTime, nullable=True)
    decision_by = Column(String(64), nullable=True)


class TransactionRecord(Base):
    """State ledger for business API operations and idempotency."""
    __tablename__ = "transactions"

    id = Column(String(64), primary_key=True)
    idempotency_key = Column(String(128), unique=True, index=True, nullable=False)
    operation = Column(String(64), nullable=False)
    actor_id = Column(String(64), nullable=False)
    tenant_id = Column(String(64), index=True, nullable=False)
    status = Column(String(32), default="PENDING")  # PENDING, SUCCESS, FAILED, RECONCILING
    input_json = Column(Text, nullable=False)
    result_json = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# Engine and Session Factory
_engine = None
_SessionFactory = None


def get_engine():
    """Get or create singleton SQLAlchemy engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
        _engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
    return _engine


def init_db() -> None:
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_db_session() -> Generator[Session, None, None]:
    """Provide transactional session scope."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    session = _SessionFactory()
    try:
        yield session
    finally:
        session.close()
