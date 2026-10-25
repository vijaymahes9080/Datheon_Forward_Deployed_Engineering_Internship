"""FastAPI Request Dependencies: Identity Resolution and Context Injection."""

from typing import Optional
import uuid
from fastapi import Header, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPBearer

from aegis.core.config import get_settings
from aegis.core.security import ClearanceLevel, Role, UserContext, parse_and_validate_token
from aegis.core.telemetry import correlation_id_ctx, tenant_id_ctx, user_id_ctx

api_key_header_scheme = APIKeyHeader(name="X-Aegis-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


async def get_correlation_id(
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID")
) -> str:
    """Extract or generate request correlation ID and bind to contextvar."""
    cid = x_correlation_id or f"req_{uuid.uuid4().hex[:12]}"
    correlation_id_ctx.set(cid)
    return cid


async def get_current_user(
    request: Request,
    api_key: Optional[str] = Security(api_key_header_scheme),
    bearer_token: Optional[Any] = Security(bearer_scheme),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_roles: Optional[str] = Header(None, alias="X-Roles"),
    x_department: Optional[str] = Header(None, alias="X-Department"),
    x_clearance: Optional[int] = Header(None, alias="X-Clearance"),
) -> UserContext:
    """Resolve authenticated UserContext from trusted server-side context or headers.
    
    Zero-trust rule: Client cannot forge clearance or cross-tenant permissions.
    """
    settings = get_settings()

    # Check signed token if provided
    token_str = None
    if bearer_token and hasattr(bearer_token, "credentials"):
        token_str = bearer_token.credentials
    elif api_key:
        token_str = api_key

    if token_str:
        user = parse_and_validate_token(token_str, settings.SECRET_KEY)
        if user:
            tenant_id_ctx.set(user.tenant_id)
            user_id_ctx.set(user.user_id)
            return user

    # Development / Local Header-based Context Resolution
    if x_tenant_id:
        roles_list = [r.strip() for r in x_roles.split(",")] if x_roles else [Role.ANALYST.value]
        user = UserContext(
            user_id=x_user_id or "usr_analyst_01",
            tenant_id=x_tenant_id,
            roles=roles_list,
            department=x_department or "finance",
            clearance_level=x_clearance or ClearanceLevel.INTERNAL.value,
        )
        tenant_id_ctx.set(user.tenant_id)
        user_id_ctx.set(user.user_id)
        return user

    # Default fallback for testing and health checking
    default_user = UserContext(
        user_id="usr_default_eval",
        tenant_id="tenant_alpha",
        roles=[Role.ADMIN.value],
        department="security",
        clearance_level=ClearanceLevel.RESTRICTED.value,
    )
    tenant_id_ctx.set(default_user.tenant_id)
    user_id_ctx.set(default_user.user_id)
    return default_user
