"""Policy Decision Point (PDP) and Least-Privilege Authorization Engine."""

from typing import Any, Dict
from pydantic import BaseModel

from aegis.agent.tools import OperationType
from aegis.core.security import Role, UserContext


class PolicyDecision(BaseModel):
    """Authorization and governance evaluation verdict."""
    allowed: bool
    requires_approval: bool = False
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH
    reason: str = "Authorized"


class AgentPolicyEngine:
    """Evaluates fine-grained RBAC, ABAC, and write-operation approval requirements."""

    TOOL_ROLE_ALLOWLIST = {
        OperationType.INVENTORY_LOOKUP.value: [
            Role.VIEWER.value,
            Role.ANALYST.value,
            Role.ENGINEER.value,
            Role.OPERATOR.value,
            Role.MANAGER.value,
            Role.ADMIN.value,
        ],
        OperationType.CUSTOMER_LOOKUP.value: [
            Role.ANALYST.value,
            Role.OPERATOR.value,
            Role.MANAGER.value,
            Role.ADMIN.value,
        ],
        OperationType.TICKET_STATUS_LOOKUP.value: [
            Role.VIEWER.value,
            Role.ANALYST.value,
            Role.ENGINEER.value,
            Role.OPERATOR.value,
            Role.MANAGER.value,
            Role.ADMIN.value,
        ],
        OperationType.TRANSACTION_STATUS_VERIFY.value: [
            Role.ANALYST.value,
            Role.OPERATOR.value,
            Role.MANAGER.value,
            Role.ADMIN.value,
        ],
        OperationType.SUPPORT_TICKET_CREATE.value: [
            Role.OPERATOR.value,
            Role.MANAGER.value,
            Role.ADMIN.value,
        ],
        OperationType.LEAD_STATUS_UPDATE.value: [
            Role.OPERATOR.value,
            Role.MANAGER.value,
            Role.ADMIN.value,
        ],
    }

    def evaluate(
        self,
        operation: str,
        arguments: Dict[str, Any],
        user: UserContext,
    ) -> PolicyDecision:
        """Evaluate authorization and approval gates for an operation."""
        # 1. Check if tool is in allowlist
        if operation not in self.TOOL_ROLE_ALLOWLIST:
            return PolicyDecision(
                allowed=False,
                reason=f"Operation '{operation}' is not an authorized enterprise tool.",
            )

        # 2. Role-based least privilege check
        allowed_roles = self.TOOL_ROLE_ALLOWLIST[operation]
        if not user.has_role(*allowed_roles):
            return PolicyDecision(
                allowed=False,
                reason=f"Actor lacks required role for '{operation}'. Required: {allowed_roles}",
            )

        # 3. Separation of Read vs Write & Human Approval Gates
        if operation == OperationType.LEAD_STATUS_UPDATE.value:
            # Irreversible CRM state write requires human approval
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                risk_level="HIGH",
                reason="CRM state modification requires human manager approval.",
            )

        if operation == OperationType.SUPPORT_TICKET_CREATE.value:
            priority = str(arguments.get("priority", "normal")).lower()
            if priority in ["high", "urgent"]:
                return PolicyDecision(
                    allowed=True,
                    requires_approval=True,
                    risk_level="MEDIUM",
                    reason=f"Creation of {priority.upper()} priority support ticket requires human approval.",
                )
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                risk_level="LOW",
                reason="Routine support ticket auto-approved under policy.",
            )

        # Read operations are auto-approved for authorized roles
        return PolicyDecision(
            allowed=True,
            requires_approval=False,
            risk_level="LOW",
            reason="Read-only operation auto-approved.",
        )
