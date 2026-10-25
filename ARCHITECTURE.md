# AegisAI Enterprise Gateway — System Architecture & Trust Boundaries

## 1. Architectural Principles

AegisAI Enterprise Gateway is architected as a modular monolith adhering to six foundational tenets:

1. **Zero-Trust Security**: No entity (human user, client application, or language model) is implicitly trusted. Permissions, tenant boundaries, and clearance levels are validated server-side at the perimeter and re-verified prior to data retrieval or state mutation.
2. **Pre-Retrieval Authorization**: Authorization filters are applied directly within storage engines (ChromaDB and SQLite) before vector search or lexical retrieval occurs. Untrusted metadata or document existence never leaks through prompts.
3. **Defense-in-Depth RAG**: Untrusted retrieved content is sanitized for indirect prompt injections, reranked via cross-encoders, assembled within bounded token windows, factually grounded, and post-verified for citation integrity.
4. **Governed Deterministic Workflows**: Business actions operate through a mandatory 9-stage pipeline where sensitive writes require human approvals cryptographically bound to exact arguments with expiring single-use nonces.
5. **Reproducibility & Observability**: Every request is tagged with a correlation ID, recorded in an append-only cryptographic audit ledger, and tracked via Prometheus metrics without placing sensitive prompt strings in metric labels.
6. **Local-First Resilience**: Zero mandatory external cloud dependencies. Operates offline using high-performance local providers or deterministic mocks with standard Ollama compatibility.

---

## 2. End-to-End Component Interaction

```
[ HTTP Request ]
       │
       ▼
[ FastAPI App ] ──► [ Correlation Middleware ] ──► [ Auth & Identity Dependency ]
                                                             │
                                                             ▼
                                                    [ Trusted UserContext ]
                                                             │
       ┌─────────────────────────────────────────────────────┼──────────────────────────────────┐
       │                                                     │                                  │
       ▼                                                     ▼                                  ▼
[ ETL Pipeline ]                                   [ Zero-Trust RAG ]                 [ Agent Orchestrator ]
  │                                                  │                                  │
  ├─► PDF/CSV/MD Parsers                             ├─► Prompt Injection Check         ├─► Schema Validation
  ├─► Structure-Aware Chunker                        ├─► Pre-Retrieval ACL Boundary     ├─► Policy Evaluation (PDP)
  ├─► SHA-256 Deduplication                          ├─► Dense Search (ChromaDB)        ├─► Approval Gate (HMAC Nonce)
  └─► ChromaDB Cosine Indexer                        ├─► BM25 Lexical Search            ├─► Idempotent Tool Execution
                                                     ├─► Reciprocal Rank Fusion         ├─► Exponential Backoff Retries
                                                     ├─► Cross-Encoder Reranker         ├─► Postcondition Check
                                                     ├─► Bounded Context Assembler      └─► Transaction Ledger
                                                     ├─► Grounded Generation
                                                     └─► Citation Verifier
```

---

## 3. Trust Boundaries & Threat Isolation

| Zone | Components | Trust Level | Security Boundary Controls |
| :--- | :--- | :--- | :--- |
| **Zone 0: Client Perimeter** | Web browsers, external REST clients | **Untrusted** | TLS termination, API key / Bearer token validation, rate limiting, request size limits. |
| **Zone 1: API Runtime** | FastAPI server, middlewares, routers | **Trusted** | Identity extraction, correlation ID injection, non-root execution context. |
| **Zone 2: Retrieval Engine** | ChromaDB, BM25 retriever, RRF engine | **Hardened** | Multi-tenant `$and` query filtering, clearance hierarchy checks, zero document existence leakage. |
| **Zone 3: Generation & LLM** | Ollama, Local Adapters, Prompts | **Semi-Trusted** | Prompt injection sanitization, bounded token budget, strict evidence grounding, citation verification. |
| **Zone 4: Business Workflows** | Sandboxed ERP/CRM services | **Protected** | Per-tool RBAC allowlists, human-in-the-loop approval ledger, single-use anti-replay tokens, idempotency verification. |
| **Zone 5: Data Stores** | SQLite database, ChromaDB disk files, Audit log | **High Security** | Local filesystem file permissions (0600), non-root container ownership, immutable hash-chained JSONL logs. |

---

## 4. Multi-Tenant Data Isolation Model

Every stored passage and document catalog record contains mandatory isolation attributes:
- `tenant_id`: Mandatory alphanumeric tenant identifier.
- `department`: Sub-organizational unit (e.g. `finance`, `hr`, `operations`, `security`).
- `access_tier`: Integer clearance level (1=Public, 2=Internal, 3=Confidential, 4=Restricted).

During search and retrieval, the query vector is executed with an immutable pre-retrieval where filter:
```json
{
  "$and": [
    { "tenant_id": { "$eq": "<user.tenant_id>" } },
    { "access_tier": { "$lte": "<user.clearance_level>" } },
    { "department": { "$in": ["<user.department>", "general"] } }
  ]
}
```
Cross-tenant requests or requests exceeding user clearance are dropped at the vector storage level, eliminating information leakage through LLM prompts.
