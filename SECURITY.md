# AegisAI Enterprise Gateway — Security Architecture & Controls

## 1. Zero-Trust Security Philosophy

AegisAI Enterprise Gateway rejects perimeter-only security models. Every component enforces explicit authorization, least-privilege access, tamper-evident logging, and defensive boundary verification.

---

## 2. Security Subsystems & Verification

### 2.1 Identity and Access Management (IAM)
- **Role-Based Access Control (RBAC)**: Fine-grained roles (`viewer`, `analyst`, `engineer`, `operator`, `manager`, `admin`, `auditor`).
- **Attribute-Based Access Control (ABAC)**:
  - `department`: Strict segregation between organizational silos.
  - `clearance_level`: Monotonic integer hierarchy (1=Public, 2=Internal, 3=Confidential, 4=Restricted).
- **Cryptographic Token Verification**: HMAC-SHA256 signatures with constant-time comparison (`hmac.compare_digest`) to neutralize timing attacks.

### 2.2 Prompt Injection & Adversarial Defense
- **Direct Prompt Injection Shield**: Queries matching adversarial directive patterns (e.g. `ignore previous instructions`, `system override`, `print pwned`) are halted at the boundary, flagged as `AuditEventType.PROMPT_INJECTION_DETECTED`, and safely rejected with status 400.
- **Indirect Prompt Injection Neutralizer**: Retrieved document passages containing embedded adversarial instructions are sanitized with `[REDACTED_ADVERSARIAL_INSTRUCTION]` prior to context assembly.

### 2.3 Citation Grounding & Anti-Hallucination
- **Proof-of-Evidence Grounding**: Returned answers must cite verifiable provenance tags (`[Source: filename | Page: X]` or `[Source: filename | Row: Y]`).
- **Citation Verification Engine**: Validates that cited documents and page/row indices match actual retrieved evidence.
- **Fail-Closed Safe Abstention**: If evidence is missing, conflicting, or fabricated, the pipeline abstains with `INSUFFICIENT_AUTHORIZED_EVIDENCE`.

### 2.4 Human-in-the-Loop Approval Governance
- **Cryptographic Parameter Binding**: Approvals hash canonical JSON arguments `SHA-256(canonical_json(arguments))`.
- **Anti-Replay Mechanism**: Single-use UUID nonce marked as `CONSUMED` immediately upon execution. Replays return 403 Forbidden.
- **Time-to-Live (TTL)**: Pending approvals expire after 15 minutes (`AEGIS_APPROVAL_TTL_SECONDS=900`).
- **Tampering Detection**: Modifying any tool parameter after approval invalidates the token.

### 2.5 Immutable Audit Ledger
- **Append-Only JSONL Storage**: All security events, ingestion batches, queries, and agent transactions are recorded.
- **Cryptographic Chaining**: Each entry contains `prev_hash` and `event_hash = SHA-256(...)`, forming an unalterable blockchain-like verifiable audit trail.

---

## 3. Data Protection and Secret Management

1. **Zero Hardcoded Secrets**: Secrets are loaded exclusively from environment variables or mounted files via `pydantic-settings`.
2. **Log & Telemetry Masking**: Structured JSON logs and Prometheus metrics automatically mask sensitive keys (`password`, `secret`, `token`, `authorization`, `api_key`).
3. **Non-Root Execution**: Container runs under unprivileged UID `10001:10001` with `no-new-privileges: true`.
