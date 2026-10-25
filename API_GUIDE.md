# AegisAI Enterprise Gateway — API Guide & Reference

This guide details all versioned REST endpoints, request/response schemas, security headers, and curl examples.

---

## 1. Authentication & Security Headers

All requests should supply client identification headers:
- `X-Tenant-ID`: Client tenant identifier (e.g. `tenant_alpha`).
- `X-User-ID`: Authenticated actor identifier (e.g. `usr_john_doe`).
- `X-Roles`: Comma-separated roles (`viewer`, `analyst`, `engineer`, `operator`, `manager`, `admin`).
- `X-Department`: User's organizational department (`finance`, `hr`, `operations`, `security`).
- `X-Clearance`: Integer clearance level (1=Public, 2=Internal, 3=Confidential, 4=Restricted).
- `X-Correlation-ID`: Optional client request trace ID.

---

## 2. API Endpoints

### 2.1 Health & Telemetry

#### Liveness Probe
```bash
curl -X GET http://localhost:8000/health/live
```
**Response (200 OK)**:
```json
{
  "status": "ALIVE",
  "service": "aegisai-enterprise-gateway"
}
```

#### Readiness Probe
```bash
curl -X GET http://localhost:8000/health/ready
```
**Response (200 OK)**:
```json
{
  "status": "READY",
  "components": {
    "database": "UP",
    "vector_store": "UP"
  }
}
```

#### Prometheus Metrics
```bash
curl -X GET http://localhost:8000/metrics
```

---

### 2.2 Document Ingestion & Lifecycle

#### Batch Ingestion
```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_alpha" \
  -H "X-Roles: operator" \
  -d '{
    "documents": [
      {
        "filename": "badge_policy.md",
        "content_base64": "IyBDb3Jwb3JhdGUgUG9saWN5CkFsbCBlbXBsb3llZXMgbXVzdCB3ZWFyIElEIGJhZGdlcy4=",
        "department": "security",
        "access_tier": 2
      }
    ]
  }'
```
**Response (200 OK)**:
```json
{
  "job_id": "job_a1b2c3d4e5f6",
  "tenant_id": "tenant_alpha",
  "status": "COMPLETED",
  "files_discovered": 1,
  "files_accepted": 1,
  "files_rejected": 0,
  "chunks_created": 1,
  "chunks_indexed": 1,
  "warnings": [],
  "failed_operations": [],
  "duration_seconds": 0.045
}
```

#### Ingestion Job Status
```bash
curl -X GET http://localhost:8000/api/v1/ingest/jobs/job_a1b2c3d4e5f6 \
  -H "X-Tenant-ID: tenant_alpha"
```

#### Delete Document
```bash
curl -X DELETE http://localhost:8000/api/v1/documents/doc_402af6d39bf6bd78 \
  -H "X-Tenant-ID: tenant_alpha" \
  -H "X-Roles: admin"
```

---

### 2.3 Authorized Search & Zero-Trust RAG

#### Authorized Hybrid Search
```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_alpha" \
  -H "X-Department: finance" \
  -H "X-Clearance: 3" \
  -d '{
    "query": "Q3 consolidated revenue",
    "top_k": 3
  }'
```

#### Citation-Grounded RAG Query
```bash
curl -X POST http://localhost:8000/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_alpha" \
  -H "X-Department: finance" \
  -H "X-Clearance: 3" \
  -d '{
    "query": "What was the consolidated revenue for Q3 2026?",
    "top_k": 5
  }'
```
**Response (200 OK)**:
```json
{
  "query": "What was the consolidated revenue for Q3 2026?",
  "answer": "Consolidated revenue for Q3 2026 reached $48.2 Million, representing a 14.5% year-over-year increase. [Source: q3_financial_report.pdf | Page: 1]",
  "is_abstained": false,
  "citation_verification": {
    "is_valid": true,
    "grounded_citations": [
      {
        "filename": "q3_financial_report.pdf",
        "provenance": "1"
      }
    ],
    "fabricated_citations": [],
    "abstain_required": false
  },
  "sources": [
    {
      "source_filename": "q3_financial_report.pdf",
      "page_number": 1,
      "row_identifier": null,
      "department": "finance",
      "score": 0.3178
    }
  ],
  "retrieval_count": 1,
  "duration_seconds": 0.015
}
```

---

### 2.4 Governed Agent Workflows

#### Execute Read Tool (Auto-Approved)
```bash
curl -X POST http://localhost:8000/api/v1/agent/action \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_alpha" \
  -H "X-Roles: analyst" \
  -d '{
    "operation": "inventory_lookup",
    "arguments": {
      "sku": "SKU-INV-1001"
    }
  }'
```

#### Request Sensitive Write Action (Transitions to Pending Approval)
```bash
curl -X POST http://localhost:8000/api/v1/agent/action \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_alpha" \
  -H "X-User-ID: usr_op_01" \
  -H "X-Roles: operator" \
  -d '{
    "operation": "lead_status_update",
    "arguments": {
      "lead_id": "LEAD-501",
      "new_status": "CLOSED_WON",
      "note": "Signed enterprise agreement."
    },
    "idempotency_key": "lead-update-key-101"
  }'
```
**Response (200 OK - PENDING_APPROVAL)**:
```json
{
  "success": false,
  "status": "PENDING_APPROVAL",
  "transaction_id": "tx_c9b8a7d6e5f4",
  "operation": "lead_status_update",
  "approval_id": "appr_7f8e9d0a1b2c",
  "error_message": "Action requires human approval: CRM state modification requires human manager approval."
}
```

#### Manager Submits Approval
```bash
curl -X POST http://localhost:8000/api/v1/agent/approvals/appr_7f8e9d0a1b2c \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_alpha" \
  -H "X-Roles: manager" \
  -d '{
    "decision": "APPROVED"
  }'
```

#### Execute Write with Approved Token
```bash
curl -X POST http://localhost:8000/api/v1/agent/action \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_alpha" \
  -H "X-Roles: operator" \
  -d '{
    "operation": "lead_status_update",
    "arguments": {
      "lead_id": "LEAD-501",
      "new_status": "CLOSED_WON",
      "note": "Signed enterprise agreement."
    },
    "approval_id": "appr_7f8e9d0a1b2c",
    "idempotency_key": "lead-update-key-101"
  }'
```
