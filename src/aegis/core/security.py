"""Security and Identity Subsystem: RBAC, ABAC, and trusted Context Models."""

from enum import Enum, IntEnum
import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ClearanceLevel(IntEnum):
    """Hierarchical security clearance levels."""
    PUBLIC = 1
    INTERNAL = 2
    CONFIDENTIAL = 3
    RESTRICTED = 4

    @classmethod
    def from_str(cls, val: str) -> "ClearanceLevel":
        mapping = {
            "public": cls.PUBLIC,
            "internal": cls.INTERNAL,
            "confidential": cls.CONFIDENTIAL,
            "restricted": cls.RESTRICTED,
        }
        return mapping.get(val.lower(), cls.INTERNAL)


class Role(str, Enum):
    """Enterprise role-based access control roles."""
    VIEWER = "viewer"
    ANALYST = "analyst"
    ENGINEER = "engineer"
    OPERATOR = "operator"
    MANAGER = "manager"
    ADMIN = "admin"
    AUDITOR = "auditor"


class Department(str, Enum):
    """Organizational departments."""
    FINANCE = "finance"
    HR = "hr"
    OPERATIONS = "operations"
    SECURITY = "security"
    LEGAL = "legal"
    ENGINEERING = "engineering"
    GENERAL = "general"


class UserContext(BaseModel):
    """Trusted server-side identity context representing the authenticated principal."""
    user_id: str
    tenant_id: str
    roles: List[str] = Field(default_factory=lambda: [Role.ANALYST.value])
    department: str = Field(default=Department.GENERAL.value)
    clearance_level: int = Field(default=ClearanceLevel.INTERNAL.value)
    email: Optional[str] = None
    is_authenticated: bool = True

    def has_role(self, *required_roles: str) -> bool:
        """Check if user has any of the specified roles."""
        return any(role in self.roles for role in required_roles) or Role.ADMIN.value in self.roles

    def can_access_document(
        self,
        doc_tenant_id: str,
        doc_department: str,
        doc_access_tier: int,
    ) -> bool:
        """Evaluate multi-tenant RBAC/ABAC access for a target document.
        
        Zero-trust principle: Must strictly match tenant, department (or general),
        and user clearance must meet or exceed document clearance tier.
        """
        # Strict tenant boundary isolation
        if self.tenant_id != doc_tenant_id:
            return False

        # Clearance hierarchy check
        if self.clearance_level < doc_access_tier:
            return False

        # Department boundary check (Admins and Auditors can cross-audit within tenant)
        if (
            self.department != doc_department
            and doc_department != Department.GENERAL.value
            and not self.has_role(Role.ADMIN.value, Role.AUDITOR.value)
        ):
            return False

        return True


class TenantContext(BaseModel):
    """Tenant boundary context."""
    tenant_id: str
    display_name: str
    active: bool = True
    allowed_departments: List[str] = Field(default_factory=list)


def generate_hmac_signature(secret: str, payload: str) -> str:
    """Generate SHA-256 HMAC signature for payload verification."""
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac_signature(secret: str, payload: str, signature: str) -> bool:
    """Verify HMAC signature in constant time against timing attacks."""
    expected = generate_hmac_signature(secret, payload)
    return hmac.compare_digest(expected, signature)


def create_mock_auth_token(user: UserContext, secret: str) -> str:
    """Generate a tamper-evident signed token for testing and local integration."""
    payload = f"{user.user_id}:{user.tenant_id}:{','.join(user.roles)}:{user.department}:{user.clearance_level}:{int(time.time())}"
    sig = generate_hmac_signature(secret, payload)
    return f"{payload}:{sig}"


def parse_and_validate_token(token: str, secret: str, ttl_seconds: int = 3600) -> Optional[UserContext]:
    """Parse and cryptographically validate an auth token into a trusted UserContext."""
    try:
        parts = token.split(":")
        if len(parts) != 7:
            return None
        user_id, tenant_id, roles_str, department, clearance_str, ts_str, signature = parts
        payload = f"{user_id}:{tenant_id}:{roles_str}:{department}:{clearance_str}:{ts_str}"
        
        # Verify HMAC
        if not verify_hmac_signature(secret, payload, signature):
            return None

        # Check TTL
        issue_time = int(ts_str)
        if time.time() - issue_time > ttl_seconds:
            return None

        return UserContext(
            user_id=user_id,
            tenant_id=tenant_id,
            roles=roles_str.split(","),
            department=department,
            clearance_level=int(clearance_str),
        )
    except Exception:
        return None
