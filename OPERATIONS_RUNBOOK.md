# AegisAI Enterprise Gateway — Operations Runbook & Disaster Recovery

## 1. System Health Monitoring

### 1.1 Automated Health Probes
- **Liveness Probe**: `GET /health/live` (Checks if HTTP event loop is responding).
- **Readiness Probe**: `GET /health/ready` (Validates database connection and vector store initialization).

### 1.2 Prometheus Alerting Thresholds
- **High Error Rate**: Alert when `rate(aegis_http_requests_total{status_code=~"5.."}[5m]) > 0.05`
- **High RAG Latency**: Alert when `histogram_quantile(0.95, sum(rate(aegis_rag_retrieval_duration_seconds_bucket[5m])) by (le)) > 0.500`
- **Security Alert**: Alert immediately when `increase(aegis_rag_queries_total{status="access_denied"}[5m]) > 10`

---

## 2. Common Operational Incidents & Triage

### 2.1 Ingestion Failures or Malformed Files
- **Symptom**: `POST /api/v1/ingest` returns status `PARTIAL_SUCCESS` or `FAILED`.
- **Diagnosis**: Query the job manifest:
  ```bash
  curl -X GET http://localhost:8000/api/v1/ingest/jobs/{job_id} -H "X-Tenant-ID: {tenant}"
  ```
- **Remediation**:
  1. Inspect `warnings` and `failed_operations` arrays.
  2. If the document is password-protected or image-only scanned, notify the data owner to provide OCR-processed or unencrypted versions.
  3. Re-submit only the corrected documents; unchanged documents will automatically deduplicate without re-indexing.

### 2.2 Agent Action Timeout or Ambiguous Status
- **Symptom**: Agent write operation times out due to transient network failure with downstream mock ERP/CRM.
- **Rule**: Never immediately re-execute an unconfirmed write!
- **Diagnosis**: Lookup transaction status using idempotency key:
  ```bash
  curl -X GET http://localhost:8000/api/v1/agent/transactions/{transaction_id}
  ```
- **Remediation**:
  1. If status is `RECONCILING`, execute `transaction_status_verify` to determine whether downstream system committed the state change.
  2. If downstream committed, mark transaction `SUCCESS`.
  3. If downstream did not commit, retry the operation using the identical `idempotency_key`.

### 2.3 Approval Expiration & Replay Rejection
- **Symptom**: Client receives `400 Bad Request: Approval token has expired` or `Security Violation: Replay Attack`.
- **Remediation**:
  1. Expired tokens cannot be renewed. Operator must initiate a fresh agent action to generate a new approval token with a new 15-minute TTL.
  2. If a replay attack warning is logged, verify whether client application has automatic retry logic that re-submits previously approved transactions.

---

## 3. Disaster Recovery & State Restoration

### 3.1 Backup Verification
- Database: `./storage/aegis.db` (or PostgreSQL dump)
- ChromaDB: `./storage/chroma_db/`
- Audit Ledger: `./storage/audit_ledger.jsonl`

### 3.2 Audit Ledger Tamper Verification
To verify that audit records have not been tampered with or truncated:
```powershell
python -c "from aegis.core.audit import get_audit_ledger; ledger = get_audit_ledger(); valid = ledger.verify_integrity(); print('Ledger Chain Valid:', valid); assert valid"
```
