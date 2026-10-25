"""FastAPI Policy-Governed Agent and Approval Endpoints."""

import json
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from aegis.agent.approval import ApprovalManager, get_approval_manager
from aegis.agent.orchestrator import (
    AgentActionRequest,
    AgentExecutionResult,
    GovernedAgentOrchestrator,
)
from aegis.api.deps import get_correlation_id, get_current_user
from aegis.core.database import TransactionRecord, get_db_session
from aegis.core.security import UserContext

router = APIRouter(prefix="/api/v1/agent", tags=["Policy-Governed Agent & Workflows"])
_orchestrator = GovernedAgentOrchestrator()
_approval_mgr = get_approval_manager()


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(description="Decision verdict: APPROVED or REJECTED")


@router.post("/action", response_model=AgentExecutionResult, status_code=status.HTTP_200_OK)
async def execute_agent_action(
    request: AgentActionRequest,
    user: UserContext = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """Execute a controlled ERP/CRM operation through the 9-stage policy pipeline."""
    result = _orchestrator.execute(
        request=request,
        user=user,
        correlation_id=correlation_id,
    )
    return result


@router.post("/approvals/{approval_id}", status_code=status.HTTP_200_OK)
async def submit_human_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    user: UserContext = Depends(get_current_user),
    correlation_id: str = Depends(get_correlation_id),
):
    """Submit Manager/Admin approval or rejection for a pending sensitive write action."""
    success, message = _approval_mgr.decide_approval(
        approval_id=approval_id,
        decision=payload.decision,
        approver=user,
        correlation_id=correlation_id,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return {"status": "SUCCESS", "approval_id": approval_id, "message": message}


@router.get("/transactions/{transaction_id}", status_code=status.HTTP_200_OK)
async def get_transaction_status(
    transaction_id: str,
    user: UserContext = Depends(get_current_user),
):
    """Verify transaction status and postcondition reconciliation state."""
    db_gen = get_db_session()
    db = next(db_gen)
    try:
        tx = (
            db.query(TransactionRecord)
            .filter(
                TransactionRecord.id == transaction_id,
                TransactionRecord.tenant_id == user.tenant_id,
            )
            .first()
        )
        if not tx:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction '{transaction_id}' not found.",
            )

        return {
            "transaction_id": tx.id,
            "idempotency_key": tx.idempotency_key,
            "operation": tx.operation,
            "actor_id": tx.actor_id,
            "tenant_id": tx.tenant_id,
            "status": tx.status,
            "input": json.loads(tx.input_json) if tx.input_json else {},
            "result": json.loads(tx.result_json) if tx.result_json else {},
            "retry_count": tx.retry_count,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
