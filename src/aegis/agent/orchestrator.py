"""Policy-Governed 9-Stage Agent Orchestrator with Idempotency and Retry Controls."""

from datetime import datetime, timezone
import json
import time
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from aegis.agent.approval import ApprovalManager, get_approval_manager
from aegis.agent.policy import AgentPolicyEngine, PolicyDecision
from aegis.agent.tools import (
    CustomerLookupInput,
    InventoryLookupInput,
    LeadStatusUpdateInput,
    OperationType,
    SandboxedERPService,
    SupportTicketCreateInput,
    TicketStatusLookupInput,
    TransactionStatusVerifyInput,
    get_erp_service,
)
from aegis.core.audit import AuditEventType, get_audit_ledger
from aegis.core.database import TransactionRecord, get_db_session
from aegis.core.security import UserContext
from aegis.core.telemetry import (
    AGENT_OPERATIONS_TOTAL,
    AGENT_RETRIES_TOTAL,
    logger,
)


class AgentActionRequest(BaseModel):
    operation: str
    arguments: Dict[str, Any]
    idempotency_key: Optional[str] = None
    approval_id: Optional[str] = None  # Provided when executing previously approved write


class StageTrace(BaseModel):
    stage: str
    status: str  # PASSED, FAILED, PENDING, SKIPPED
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentExecutionResult(BaseModel):
    success: bool
    status: str  # SUCCESS, FAILED, PENDING_APPROVAL, POLICY_DENIED, RECONCILING
    transaction_id: str
    operation: str
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    approval_id: Optional[str] = None
    execution_trace: List[StageTrace] = Field(default_factory=list)
    duration_seconds: float = 0.0


class GovernedAgentOrchestrator:
    """Executes business tools through the strict 9-stage zero-trust execution pipeline."""

    INPUT_SCHEMA_MAP = {
        OperationType.INVENTORY_LOOKUP.value: InventoryLookupInput,
        OperationType.CUSTOMER_LOOKUP.value: CustomerLookupInput,
        OperationType.LEAD_STATUS_UPDATE.value: LeadStatusUpdateInput,
        OperationType.SUPPORT_TICKET_CREATE.value: SupportTicketCreateInput,
        OperationType.TICKET_STATUS_LOOKUP.value: TicketStatusLookupInput,
        OperationType.TRANSACTION_STATUS_VERIFY.value: TransactionStatusVerifyInput,
    }

    def __init__(
        self,
        erp_service: Optional[SandboxedERPService] = None,
        policy_engine: Optional[AgentPolicyEngine] = None,
        approval_manager: Optional[ApprovalManager] = None,
        max_retries: int = 3,
    ):
        self.erp = erp_service or get_erp_service()
        self.policy = policy_engine or AgentPolicyEngine()
        self.approvals = approval_manager or get_approval_manager()
        self.max_retries = max_retries
        self.audit_ledger = get_audit_ledger()

    def execute(
        self,
        request: AgentActionRequest,
        user: UserContext,
        correlation_id: str = "agent_action",
    ) -> AgentExecutionResult:
        start_time = time.time()
        transaction_id = f"tx_{uuid.uuid4().hex[:12]}"
        traces: List[StageTrace] = []

        # Stage 1: REQUEST INGESTION & IDEMPOTENCY CHECK
        traces.append(StageTrace(stage="1_REQUEST", status="PASSED", details={"operation": request.operation}))

        if request.idempotency_key:
            db_gen = get_db_session()
            db = next(db_gen)
            try:
                existing_tx = (
                    db.query(TransactionRecord)
                    .filter(
                        TransactionRecord.idempotency_key == request.idempotency_key,
                        TransactionRecord.tenant_id == user.tenant_id,
                    )
                    .first()
                )
                if existing_tx:
                    traces.append(
                        StageTrace(
                            stage="IDEMPOTENCY_CACHE_HIT",
                            status="PASSED",
                            details={"existing_tx_id": existing_tx.id, "status": existing_tx.status},
                        )
                    )
                    cached_res = json.loads(existing_tx.result_json) if existing_tx.result_json else {}
                    return AgentExecutionResult(
                        success=existing_tx.status == "SUCCESS",
                        status=existing_tx.status,
                        transaction_id=existing_tx.id,
                        operation=existing_tx.operation,
                        result=cached_res,
                        execution_trace=traces,
                        duration_seconds=round(time.time() - start_time, 3),
                    )
            finally:
                try:
                    next(db_gen)
                except StopIteration:
                    pass

        # Stage 2: INTENT PARSING & TOOL RESOLUTION
        op = request.operation.strip().lower()
        if op not in self.INPUT_SCHEMA_MAP:
            traces.append(StageTrace(stage="2_INTENT_PARSING", status="FAILED", details={"error": "Unknown tool"}))
            AGENT_OPERATIONS_TOTAL.labels(tool_name=op, status="failure").inc()
            return AgentExecutionResult(
                success=False,
                status="FAILED",
                transaction_id=transaction_id,
                operation=op,
                error_message=f"Unknown tool operation: {op}",
                execution_trace=traces,
                duration_seconds=round(time.time() - start_time, 3),
            )
        traces.append(StageTrace(stage="2_INTENT_PARSING", status="PASSED", details={"resolved_tool": op}))

        # Stage 3: SCHEMA VALIDATION
        schema_cls = self.INPUT_SCHEMA_MAP[op]
        try:
            validated_input = schema_cls(**request.arguments)
            traces.append(StageTrace(stage="3_SCHEMA_VALIDATION", status="PASSED"))
        except Exception as ex:
            traces.append(StageTrace(stage="3_SCHEMA_VALIDATION", status="FAILED", details={"validation_error": str(ex)}))
            AGENT_OPERATIONS_TOTAL.labels(tool_name=op, status="failure").inc()
            return AgentExecutionResult(
                success=False,
                status="FAILED",
                transaction_id=transaction_id,
                operation=op,
                error_message=f"Schema validation error: {str(ex)}",
                execution_trace=traces,
                duration_seconds=round(time.time() - start_time, 3),
            )

        # Stage 4: IDENTITY CHECK
        if not user or not user.is_authenticated:
            traces.append(StageTrace(stage="4_IDENTITY_CHECK", status="FAILED", details={"error": "Unauthenticated"}))
            AGENT_OPERATIONS_TOTAL.labels(tool_name=op, status="policy_denied").inc()
            return AgentExecutionResult(
                success=False,
                status="POLICY_DENIED",
                transaction_id=transaction_id,
                operation=op,
                error_message="Identity verification failed.",
                execution_trace=traces,
                duration_seconds=round(time.time() - start_time, 3),
            )
        traces.append(
            StageTrace(
                stage="4_IDENTITY_CHECK",
                status="PASSED",
                details={"user_id": user.user_id, "tenant_id": user.tenant_id, "roles": user.roles},
            )
        )

        # Stage 5: POLICY DECISION
        decision: PolicyDecision = self.policy.evaluate(
            operation=op,
            arguments=validated_input.model_dump(),
            user=user,
        )
        if not decision.allowed:
            traces.append(StageTrace(stage="5_POLICY_DECISION", status="FAILED", details={"reason": decision.reason}))
            AGENT_OPERATIONS_TOTAL.labels(tool_name=op, status="policy_denied").inc()
            return AgentExecutionResult(
                success=False,
                status="POLICY_DENIED",
                transaction_id=transaction_id,
                operation=op,
                error_message=decision.reason,
                execution_trace=traces,
                duration_seconds=round(time.time() - start_time, 3),
            )
        traces.append(
            StageTrace(
                stage="5_POLICY_DECISION",
                status="PASSED",
                details={"requires_approval": decision.requires_approval, "risk": decision.risk_level},
            )
        )

        # Stage 6: APPROVAL GATE
        if decision.requires_approval:
            if not request.approval_id:
                # Create pending approval request
                appr_rec = self.approvals.create_approval_request(
                    operation=op,
                    arguments=validated_input.model_dump(),
                    actor_id=user.user_id,
                    tenant_id=user.tenant_id,
                    correlation_id=correlation_id,
                )
                traces.append(
                    StageTrace(
                        stage="6_APPROVAL_GATE",
                        status="PENDING",
                        details={"approval_id": appr_rec.id, "reason": decision.reason},
                    )
                )
                AGENT_OPERATIONS_TOTAL.labels(tool_name=op, status="pending_approval").inc()
                return AgentExecutionResult(
                    success=False,
                    status="PENDING_APPROVAL",
                    transaction_id=transaction_id,
                    operation=op,
                    approval_id=appr_rec.id,
                    error_message=f"Action requires human approval: {decision.reason}",
                    execution_trace=traces,
                    duration_seconds=round(time.time() - start_time, 3),
                )
            else:
                # Verify and consume provided approval token
                verified, msg = self.approvals.verify_and_consume(
                    approval_id=request.approval_id,
                    operation=op,
                    arguments=validated_input.model_dump(),
                    actor=user,
                )
                if not verified:
                    traces.append(StageTrace(stage="6_APPROVAL_GATE", status="FAILED", details={"error": msg}))
                    AGENT_OPERATIONS_TOTAL.labels(tool_name=op, status="policy_denied").inc()
                    return AgentExecutionResult(
                        success=False,
                        status="POLICY_DENIED",
                        transaction_id=transaction_id,
                        operation=op,
                        error_message=msg,
                        execution_trace=traces,
                        duration_seconds=round(time.time() - start_time, 3),
                    )
                traces.append(
                    StageTrace(
                        stage="6_APPROVAL_GATE",
                        status="PASSED",
                        details={"approval_id": request.approval_id, "consumed": True},
                    )
                )
        else:
            traces.append(StageTrace(stage="6_APPROVAL_GATE", status="SKIPPED", details={"auto_approved": True}))

        # Stage 7: EXECUTION WITH BOUNDED EXPONENTIAL-BACKOFF RETRIES
        tool_method = getattr(self.erp, op)
        result: Optional[Dict[str, Any]] = None
        execution_err: Optional[str] = None
        attempts = 0

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            try:
                result = tool_method(validated_input)
                traces.append(StageTrace(stage="7_EXECUTION", status="PASSED", details={"attempts": attempts}))
                break
            except Exception as ex:
                execution_err = str(ex)
                AGENT_RETRIES_TOTAL.labels(tool_name=op).inc()
                if attempt < self.max_retries:
                    # Exponential backoff sleep: 0.05s, 0.1s, 0.2s
                    sleep_time = 0.05 * (2 ** (attempt - 1))
                    time.sleep(sleep_time)

        if result is None:
            traces.append(
                StageTrace(
                    stage="7_EXECUTION",
                    status="FAILED",
                    details={"error": execution_err, "total_attempts": attempts},
                )
            )
            AGENT_OPERATIONS_TOTAL.labels(tool_name=op, status="failure").inc()
            return AgentExecutionResult(
                success=False,
                status="FAILED",
                transaction_id=transaction_id,
                operation=op,
                error_message=f"Execution failed after {attempts} attempts: {execution_err}",
                execution_trace=traces,
                duration_seconds=round(time.time() - start_time, 3),
            )

        # Stage 8: POSTCONDITION VERIFICATION & RECONCILIATION
        postcondition_passed = True
        if op == OperationType.LEAD_STATUS_UPDATE.value and result:
            postcondition_passed = result.get("success", False)
        elif op == OperationType.SUPPORT_TICKET_CREATE.value and result:
            postcondition_passed = result.get("success", False)

        if not postcondition_passed:
            traces.append(
                StageTrace(
                    stage="8_POSTCONDITION_VERIFICATION",
                    status="RECONCILING",
                    details={"result": result},
                )
            )
            return AgentExecutionResult(
                success=False,
                status="RECONCILING",
                transaction_id=transaction_id,
                operation=op,
                result=result,
                error_message="Postcondition check failed; entered reconciliation state.",
                execution_trace=traces,
                duration_seconds=round(time.time() - start_time, 3),
            )
        traces.append(StageTrace(stage="8_POSTCONDITION_VERIFICATION", status="PASSED"))

        # Stage 9: AUDIT LEDGER PERSISTENCE
        duration = round(time.time() - start_time, 3)
        traces.append(StageTrace(stage="9_AUDIT", status="PASSED", details={"duration": duration}))

        # Persist transaction in SQLite
        db_gen = get_db_session()
        db = next(db_gen)
        try:
            tx_record = TransactionRecord(
                id=transaction_id,
                idempotency_key=request.idempotency_key or transaction_id,
                operation=op,
                actor_id=user.user_id,
                tenant_id=user.tenant_id,
                status="SUCCESS",
                input_json=json.dumps(validated_input.model_dump()),
                result_json=json.dumps(result),
                retry_count=attempts - 1,
            )
            db.merge(tx_record)
            db.commit()
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        self.audit_ledger.record_event(
            event_type=AuditEventType.AGENT_EXECUTION_COMPLETED,
            tenant_id=user.tenant_id,
            actor_id=user.user_id,
            correlation_id=correlation_id,
            resource_id=transaction_id,
            details={"operation": op, "duration": duration},
        )
        AGENT_OPERATIONS_TOTAL.labels(tool_name=op, status="success").inc()

        return AgentExecutionResult(
            success=True,
            status="SUCCESS",
            transaction_id=transaction_id,
            operation=op,
            result=result,
            execution_trace=traces,
            duration_seconds=duration,
        )
