"""Unit tests for Security Context, clearance levels, and token HMAC validation."""

import time
import pytest
from aegis.core.security import (
    ClearanceLevel,
    Role,
    UserContext,
    create_mock_auth_token,
    parse_and_validate_token,
    verify_hmac_signature,
)


def test_clearance_and_role_access():
    user = UserContext(
        user_id="u_finance_01",
        tenant_id="tenant_alpha",
        roles=[Role.ANALYST.value],
        department="finance",
        clearance_level=ClearanceLevel.CONFIDENTIAL.value,  # Level 3
    )

    # Authorized: same tenant, same department, tier 2 <= 3
    assert user.can_access_document("tenant_alpha", "finance", 2) is True
    # Authorized: tier 3 <= 3
    assert user.can_access_document("tenant_alpha", "finance", 3) is True
    # Denied: tier 4 (restricted) > user clearance 3
    assert user.can_access_document("tenant_alpha", "finance", 4) is False
    # Denied: different department
    assert user.can_access_document("tenant_alpha", "hr", 2) is False
    # Denied: different tenant
    assert user.can_access_document("tenant_beta", "finance", 2) is False


def test_token_creation_and_tamper_detection():
    secret = "test-secret-key-32-chars-long-123456"
    user = UserContext(
        user_id="u_admin",
        tenant_id="tenant_alpha",
        roles=[Role.ADMIN.value],
        department="security",
        clearance_level=ClearanceLevel.RESTRICTED.value,
    )

    token = create_mock_auth_token(user, secret)
    parsed = parse_and_validate_token(token, secret)
    assert parsed is not None
    assert parsed.user_id == "u_admin"
    assert parsed.tenant_id == "tenant_alpha"
    assert parsed.clearance_level == ClearanceLevel.RESTRICTED.value

    # Tampered token: attempt to change tenant_id
    tampered_token = token.replace("tenant_alpha", "tenant_beta")
    tampered_parsed = parse_and_validate_token(tampered_token, secret)
    assert tampered_parsed is None  # HMAC validation rejects tampered token
