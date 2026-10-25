"""Immutable Security and Transaction Audit Event Ledger with Cryptographic Chaining."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from aegis.core.config import get_settings
from aegis.core.security import generate_hmac_signature


class AuditEventType(str):
    # Ingestion Events
    DOCUMENT_INGESTED = "DOCUMENT_INGESTED"
    DOCUMENT_DELETED = "DOCUMENT_DELETED"
    INGESTION_FAILED = "INGESTION_FAILED"

    # Retrieval and RAG Security Events
    SEARCH_QUERY = "SEARCH_QUERY"
    RAG_QUERY = "RAG_QUERY"
    ACCESS_DENIED = "ACCESS_DENIED"
    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    CITATION_VALIDATED = "CITATION_VALIDATED"
    CITATION_FAILED = "CITATION_FAILED"
    ABSTENTION_TRIGGERED = "ABSTENTION_TRIGGERED"

    # Agent and Governance Events
    AGENT_OPERATION_REQUESTED = "AGENT_OPERATION_REQUESTED"
    AGENT_POLICY_EVALUATED = "AGENT_POLICY_EVALUATED"
    AGENT_APPROVAL_REQUESTED = "AGENT_APPROVAL_REQUESTED"
    AGENT_APPROVAL_DECIDED = "AGENT_APPROVAL_DECIDED"
    AGENT_EXECUTION_COMPLETED = "AGENT_EXECUTION_COMPLETED"
    AGENT_EXECUTION_FAILED = "AGENT_EXECUTION_FAILED"
    AGENT_RETRY_ATTEMPT = "AGENT_RETRY_ATTEMPT"


class AuditEvent(BaseModel):
    """Tamper-evident audit event record."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str
    tenant_id: str
    actor_id: str
    correlation_id: str
    resource_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = "GENESIS"
    event_hash: str = ""

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of the canonical serialized event content."""
        canonical_content = f"{self.event_id}:{self.timestamp}:{self.event_type}:{self.tenant_id}:{self.actor_id}:{self.correlation_id}:{self.resource_id}:{json.dumps(self.details, sort_keys=True)}:{self.prev_hash}"
        return hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()


class AuditLedger:
    """Append-only audit ledger with cryptographic verification."""

    def __init__(self, log_path: Optional[str] = None):
        settings = get_settings()
        self.log_path = Path(log_path or "./storage/audit_ledger.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._get_tail_hash()

    def _get_tail_hash(self) -> str:
        """Retrieve the hash of the last entry in the ledger, or GENESIS."""
        if not self.log_path.exists():
            return "GENESIS"
        last_line = ""
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line.strip()
        if not last_line:
            return "GENESIS"
        try:
            entry = json.loads(last_line)
            return entry.get("event_hash", "GENESIS")
        except Exception:
            return "GENESIS"

    def record_event(
        self,
        event_type: str,
        tenant_id: str,
        actor_id: str,
        correlation_id: str,
        details: Optional[Dict[str, Any]] = None,
        resource_id: Optional[str] = None,
    ) -> AuditEvent:
        """Append an immutable, hashed audit record to the ledger."""
        safe_details = details or {}
        event = AuditEvent(
            event_type=event_type,
            tenant_id=tenant_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            resource_id=resource_id,
            details=safe_details,
            prev_hash=self._last_hash,
        )
        event.event_hash = event.compute_hash()
        self._last_hash = event.event_hash

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

        return event

    def verify_integrity(self) -> bool:
        """Verify the cryptographic chain of all records in the ledger."""
        if not self.log_path.exists():
            return True
        expected_prev = "GENESIS"
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                event = AuditEvent(**data)
                if event.prev_hash != expected_prev:
                    return False
                if event.compute_hash() != event.event_hash:
                    return False
                expected_prev = event.event_hash
        return True


# Singleton ledger instance
_audit_ledger: Optional[AuditLedger] = None


def get_audit_ledger() -> AuditLedger:
    """Get singleton audit ledger instance."""
    global _audit_ledger
    if _audit_ledger is None:
        _audit_ledger = AuditLedger()
    return _audit_ledger
