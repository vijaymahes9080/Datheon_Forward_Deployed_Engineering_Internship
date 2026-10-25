"""Integration tests for FastAPI endpoints: Ingest, Search, RAG, Agent, and Telemetry."""

import base64
import pytest
from fastapi.testclient import TestClient

from aegis.api.server import app
from aegis.core.database import init_db


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_metrics_endpoints(client: TestClient):
    # Liveness
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ALIVE"

    # Readiness
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "READY"

    # Prometheus metrics
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    assert b"aegis_http_requests_total" in metrics_resp.content


def test_batch_ingest_and_job_status(client: TestClient):
    content = b"# Corporate Policy\nAll employees must wear ID badges."
    payload = {
        "documents": [
            {
                "filename": "badge_policy.md",
                "content_base64": base64.b64encode(content).decode("utf-8"),
                "department": "security",
                "access_tier": 2,
            }
        ]
    }
    headers = {"X-Tenant-ID": "tenant_alpha", "X-Roles": "admin"}

    # Ingest
    ingest_resp = client.post("/api/v1/ingest", json=payload, headers=headers)
    assert ingest_resp.status_code == 200
    manifest = ingest_resp.json()
    assert manifest["status"] in ["COMPLETED", "PARTIAL_SUCCESS"]
    assert manifest["files_accepted"] == 1
    job_id = manifest["job_id"]

    # Check job status
    job_resp = client.get(f"/api/v1/ingest/jobs/{job_id}", headers=headers)
    assert job_resp.status_code == 200
    assert job_resp.json()["job_id"] == job_id


def test_authorized_search_and_rag_query(client: TestClient):
    headers = {"X-Tenant-ID": "tenant_alpha", "X-Roles": "analyst", "X-Department": "security", "X-Clearance": "3"}

    # Search
    search_resp = client.post("/api/v1/search", json={"query": "ID badges", "top_k": 3}, headers=headers)
    assert search_resp.status_code == 200
    assert search_resp.json()["total_found"] >= 1

    # RAG Query
    rag_resp = client.post("/api/v1/rag/query", json={"query": "What are the rules for ID badges?", "top_k": 3}, headers=headers)
    assert rag_resp.status_code == 200
    data = rag_resp.json()
    assert "answer" in data
    assert len(data["sources"]) >= 1


def test_agent_action_and_approval_workflow(client: TestClient):
    user_headers = {"X-Tenant-ID": "tenant_alpha", "X-User-ID": "usr_op_01", "X-Roles": "operator"}
    mgr_headers = {"X-Tenant-ID": "tenant_alpha", "X-User-ID": "usr_mgr_01", "X-Roles": "manager"}

    # 1. Read-only inventory lookup (auto-approved)
    inv_req = {
        "operation": "inventory_lookup",
        "arguments": {"sku": "SKU-INV-1001"},
    }
    inv_resp = client.post("/api/v1/agent/action", json=inv_req, headers=user_headers)
    assert inv_resp.status_code == 200
    assert inv_resp.json()["status"] == "SUCCESS"
    assert inv_resp.json()["result"]["found"] is True

    # 2. Sensitive write: lead status update (requires approval)
    import uuid
    fresh_idem_key = f"lead-update-{uuid.uuid4().hex[:8]}"
    lead_req = {
        "operation": "lead_status_update",
        "arguments": {"lead_id": "LEAD-501", "new_status": "CLOSED_WON", "note": "Deal signed."},
        "idempotency_key": fresh_idem_key,
    }
    lead_resp = client.post("/api/v1/agent/action", json=lead_req, headers=user_headers)
    assert lead_resp.status_code == 200
    assert lead_resp.json()["status"] == "PENDING_APPROVAL"
    approval_id = lead_resp.json()["approval_id"]
    assert approval_id is not None

    # 3. Manager approves the request
    appr_resp = client.post(
        f"/api/v1/agent/approvals/{approval_id}",
        json={"decision": "APPROVED"},
        headers=mgr_headers,
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "SUCCESS"

    # 4. Execute with approved token
    lead_req["approval_id"] = approval_id
    exec_resp = client.post("/api/v1/agent/action", json=lead_req, headers=user_headers)
    assert exec_resp.status_code == 200
    assert exec_resp.json()["status"] == "SUCCESS"
    tx_id = exec_resp.json()["transaction_id"]

    # 5. Check transaction status endpoint
    tx_resp = client.get(f"/api/v1/agent/transactions/{tx_id}", headers=user_headers)
    assert tx_resp.status_code == 200
    assert tx_resp.json()["status"] == "SUCCESS"
