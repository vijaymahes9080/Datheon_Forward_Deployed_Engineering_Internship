# AegisAI Enterprise Gateway — Threat Model (STRIDE Methodology)

## 1. Scope & Objective

This threat model assesses potential adversarial vectors targeting AegisAI Enterprise Gateway across its four core modules, applying the STRIDE threat categorization framework.

---

## 2. Threat Analysis & Mitigations

### 2.1 Spoofing Identity
- **Threat**: An attacker attempts to forge HTTP headers (e.g. `X-Tenant-ID`, `X-Clearance`) or forge JWT tokens to impersonate another tenant or elevated admin.
- **Impact**: Cross-tenant data breach or unauthorized administrative write execution.
- **Mitigations**:
  - In production, server enforces cryptographic HMAC-SHA256 signature verification over session tokens with constant-time comparison.
  - Identity headers are validated against trusted backend tenant registries; untrusted client-supplied identity overrides are dropped at the API gateway layer.

### 2.2 Tampering with Data
- **Threat**: An attacker intercepts an approved human-in-the-loop transaction and alters arguments (e.g. changing `lead_id` or modifying transaction amounts).
- **Impact**: Unauthorized state modification in CRM/ERP systems.
- **Mitigations**:
  - Approval tokens store a cryptographic hash `arg_hash = SHA-256(canonical_json(arguments))`.
  - During execution, current arguments are re-hashed and compared against `arg_hash`. Any modification results in immediate transaction termination and security alert.

### 2.3 Repudiation
- **Threat**: A compromised user or malicious operator performs sensitive CRM changes or data extractions and claims they did not initiate them.
- **Impact**: Inability to hold actors legally and administratively accountable.
- **Mitigations**:
  - Immutable audit ledger chains each event with SHA-256 cryptographic hashes (`prev_hash` -> `event_hash`).
  - Every event captures `actor_id`, `tenant_id`, `correlation_id`, `timestamp`, and sanitized action details.

### 2.4 Information Disclosure
- **Threat 1**: Direct or Indirect Prompt Injection attempting to bypass RAG filters to reveal confidential salaries, API keys, or cross-tenant files.
- **Threat 2**: Low-clearance users guessing document names or searching for metadata remnants.
- **Mitigations**:
  - **Pre-Retrieval ACL Barrier**: Search queries filter by tenant and clearance at the database layer. Unauthorized files are never retrieved or sent to LLM context.
  - **Indirect Injection Sanitizer**: Ingested passages are scanned for adversarial overrides (`[SYSTEM OVERRIDE]`) and redacted.
  - **Zero Existence Leakage**: Unauthorized searches return empty result sets with no hints of document existence.

### 2.5 Denial of Service (DoS)
- **Threat**: Ingestion of maliciously crafted malformed PDFs (billion laughs, circular xrefs, or decompression bombs) or infinite retry loops on failing ERP endpoints.
- **Impact**: Gateway resource exhaustion, CPU spike, or system downtime.
- **Mitigations**:
  - `pypdf` defensive extraction catches corrupted and empty streams gracefully with structured warnings.
  - Bounded concurrency limits on batch ingestion (`AEGIS_MAX_CONCURRENT_INGESTIONS=4`).
  - Exponential backoff retry policies capped at `max_retries=3` with fallback to `RECONCILING` state.

### 2.6 Elevation of Privilege
- **Threat**: An agent model autonomously calling unauthorized tools (e.g. arbitrary code execution or shell commands).
- **Impact**: Full server takeover.
- **Mitigations**:
  - Explicit tool allowlist: Only pre-registered tools (`inventory_lookup`, `customer_lookup`, `lead_status_update`, `support_ticket_create`, `ticket_status_lookup`, `transaction_status_verify`) can be executed.
  - Arbitrary shell, raw SQL, and unconstrained network destinations are completely excluded from the agent registry.
  - Write capabilities are strictly separated from read capabilities and gated by human approvals.
