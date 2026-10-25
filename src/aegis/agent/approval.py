"""Human-in-the-Loop Approval Ledger with Anti-Replay TTL and Argument Hash Verification."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Dict, Optional, Tuple
import uuid

from aegis.core.audit import AuditEventType, get_audit_ledger
from aegis.core.config import get_settings
from aegis.core.database import ApprovalRecord, get_db_session
from aegis.core.security import Role, UserContext
from aegis.core.telemetry import AGENT_APPROVALS_TOTAL, logger


class ApprovalManager:
    """Manages creation, verification, anti-replay, and consumption of human approvals."""

    def __init__(self):
        self.settings = get_settings()
        self.audit_ledger = get_audit_ledger()

    @staticmethod
    def compute_arg_hash(arguments: Dict[str, Any]) -> str:
        """Compute canonical SHA-256 hash of tool arguments to detect parameter tampering."""
        canonical_str = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    def create_approval_request(
        self,
        operation: str,
        arguments: Dict[str, Any],
        actor_id: str,
        tenant_id: str,
        correlation_id: str = "approval_request",
    ) -> ApprovalRecord:
        """Create a pending approval request bound to exact operation, arguments, and actor."""
        approval_id = f"appr_{uuid.uuid4().hex[:12]}"
        nonce = uuid.uuid4().hex
        arg_hash = self.compute_arg_hash(arguments)
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.APPROVAL_TTL_SECONDS
        )

        record = ApprovalRecord(
            id=approval_id,
            operation=operation,
            arg_hash=arg_hash,
            arguments_json=json.dumps(arguments),
            actor_id=actor_id,
            tenant_id=tenant_id,
            status="PENDING",
            nonce=nonce,
            expires_at=expires_at,
        )

        db_gen = get_db_session()
        db = next(db_gen)
        try:
            db.add(record)
            db.commit()
            db.refresh(record)

            self.audit_ledger.record_event(
                event_type=AuditEventType.AGENT_APPROVAL_REQUESTED,
                tenant_id=tenant_id,
                actor_id=actor_id,
                correlation_id=correlation_id,
                resource_id=approval_id,
                details={"operation": operation, "arg_hash": arg_hash},
            )
            return record
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

    def decide_approval(
        self,
        approval_id: str,
        decision: str,  # "APPROVED" or "REJECTED"
        approver: UserContext,
        correlation_id: str = "approval_decision",
    ) -> Tuple[bool, str]:
        """Manager or Admin approves or rejects a pending operation."""
        if not approver.has_role(Role.MANAGER.value, Role.ADMIN.value):
            return False, "Forbidden: Only Manager or Admin can decide approvals."

        db_gen = get_db_session()
        db = next(db_gen)
        try:
            record = db.query(ApprovalRecord).filter(ApprovalRecord.id == approval_id).first()
            if not record:
                return False, f"Approval request '{approval_id}' not found."

            if record.tenant_id != approver.tenant_id:
                return False, "Access Denied: Cross-tenant approval attempt."

            if record.status != "PENDING":
                return False, f"Approval already decided with status '{record.status}'."

            # Check expiration
            # Ensure both datetimes are timezone-aware for comparison
            exp = record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                record.status = "EXPIRED"
                db.commit()
                AGENT_APPROVALS_TOTAL.labels(decision="expired").inc()
                return False, "Approval request has expired."

            new_status = decision.upper()
            if new_status not in ["APPROVED", "REJECTED"]:
                return False, "Invalid decision: Must be APPROVED or REJECTED."

            record.status = new_status
            record.decided_at = datetime.now(timezone.utc)
            record.decision_by = approver.user_id
            db.commit()

            AGENT_APPROVALS_TOTAL.labels(decision=new_status.lower()).inc()
            self.audit_ledger.record_event(
                event_type=AuditEventType.AGENT_APPROVAL_DECIDED,
                tenant_id=approver.tenant_id,
                actor_id=approver.user_id,
                correlation_id=correlation_id,
                resource_id=approval_id,
                details={"decision": new_status, "operation": record.operation},
            )
            return True, f"Approval request {new_status.lower()} successfully."
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

    def verify_and_consume(
        self,
        approval_id: str,
        operation: str,
        arguments: Dict[str, Any],
        actor: UserContext,
    ) -> Tuple[bool, str]:
        """Verify that an approved token is valid, matches arguments, and consume it to prevent replay."""
        db_gen = get_db_session()
        db = next(db_gen)
        try:
            record = db.query(ApprovalRecord).filter(ApprovalRecord.id == approval_id).first()
            if not record:
                return False, "Invalid approval token: record not found."

            if record.tenant_id != actor.tenant_id:
                return False, "Access Denied: Cross-tenant approval usage."

            if record.status == "CONSUMED":
                return False, "Security Violation: Approval token has already been consumed (Replay Attack)."

            if record.status != "APPROVED":
                return False, f"Approval token is not in APPROVED state (current: {record.status})."

            exp = record.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                record.status = "EXPIRED"
                db.commit()
                return False, "Approval token has expired."

            if record.operation != operation:
                return False, f"Operation mismatch: token authorized for '{record.operation}', not '{operation}'."

            # Verify Argument Hash Integrity
            current_arg_hash = self.compute_arg_hash(arguments)
            if current_arg_hash != record.arg_hash:
                return False, "Security Violation: Arguments have been modified since approval was granted."

            # Anti-replay: single-use consumption
            record.status = "CONSUMED"
            db.commit()
            return True, "Approval token verified and consumed."
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass


# Singleton approval manager
_approval_mgr = None


def get_approval_manager() -> ApprovalManager:
    global _approval_mgr
    if _approval_mgr is None:
        _approval_mgr = ApprovalManager()
    return _approval_mgr
