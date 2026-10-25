# AegisAI Enterprise Gateway — Zero-Trust Enterprise AI Integration Engine

<div align="center">

![AegisAI Hero Banner](docs/assets/aegis_hero_banner.png)

[![Python 3.12](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Cosine_Vector_Store-FF6F61?style=for-the-badge)](https://www.trychroma.com/)
[![Docker](https://img.shields.io/badge/Docker-Non--Root_Hardened-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=for-the-badge)](LICENSE)

**A production-grade, zero-trust AI integration engine connecting unstructured corporate knowledge (PDF, CSV, Markdown) to business ERP/CRM workflows with pre-retrieval authorization, citation-grounded RAG, and human-in-the-loop approvals.**

[Architecture Deep Dive](ARCHITECTURE.md) • [Security Controls](SECURITY.md) • [Threat Model](THREAT_MODEL.md) • [API Guide](API_GUIDE.md) • [Operations Runbook](OPERATIONS_RUNBOOK.md)

</div>

---

## Executive Overview

Enterprise AI implementations frequently fail in production due to four critical vulnerabilities:
1. **Context Boundary Violations**: Models retrieve cross-tenant or cross-department documents because permissions are evaluated only *inside* the prompt rather than at the database retrieval barrier.
2. **Hallucinated Factual Claims**: Answers cite non-existent sources, fake page numbers, or fabricate information when facts are absent.
3. **Uncontrolled Business Mutations**: Autonomous agents execute destructive ERP/CRM writes without human oversight, idempotency protection, or replay prevention.
4. **Adversarial Document Injections**: Malicious instructions embedded in uploaded files override system guardrails.

**AegisAI Enterprise Gateway** resolves these vulnerabilities through a modular monolith architecture that enforces identity, access control, and transaction governance **independently of the LLM**.

---

## System Architecture

```
                          [ Enterprise Client / User ]
                                       │
                                       ▼ (TLS 1.3 / API-Key / Bearer Token)
                         ┌───────────────────────────┐
                         │ FastAPI Gateway (Non-Root)│
                         │ • Correlation Middleware  │
                         │ • Trusted Identity (RBAC) │
                         │ • Prometheus Metrics      │
                         └─────────────┬─────────────┘
                                       │
          ┌────────────────────────────┼───────────────────────────┐
          ▼                            ▼                           ▼
 ┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
 │   Module 1: ETL  │        │  Module 2: RAG   │        │ Module 3: Agent  │
 │ • PDF Page Proven│        │ • Pre-Retrieval  │        │ • 9-Stage Exec   │
 │ • CSV Row Proven │        │   ACL Boundary   │        │ • PDP Policy     │
 │ • MD Breadcrumb  │        │ • BM25 + Dense   │        │ • Anti-Replay    │
 │ • SHA-256 Dedup  │        │   Fusion (RRF)   │        │   Approval TTL   │
 │ • Chroma Cosine  │        │ • Grounded Gen   │        │ • Idempotent Tx  │
 │ • Batch Manifest │        │ • Citation Check │        │ • Audit Ledger   │
 └────────┬─────────┘        └────────┬─────────┘        └────────┬─────────┘
          │                           │                           │
          └───────────────────────────┼───────────────────────────┘
                                      ▼
                       ┌──────────────────────────────┐
                       │ Storage & Persistence Layer  │
                       │ • ChromaDB Vector Store      │
                       │ • SQLite/PostgreSQL State    │
                       │ • Immutable Audit JSONL Log  │
                       └──────────────────────────────┘
```

---

## The Four Core Engineering Modules

### Module 1 — Intelligent Legacy Data ETL
- **Structure-Aware Extraction**:
  - **PDF**: Preserves 1-indexed page provenance and metadata using `pypdf`. Gracefully captures password warnings and empty page indicators.
  - **CSV**: Parses tabular data retaining headers, typed columns, and deterministic composite row identifiers (`row_1`, `row_2`).
  - **Markdown**: Extracts hierarchical heading stacks (`# > ## > ###`) into structured section breadcrumbs.
- **SHA-256 Content Deduplication**: Reprocessing identical documents produces zero duplicate vector entries.
- **Explicit Cosine Distance**: ChromaDB collection configured explicitly with `{"hnsw:space": "cosine"}`.
- **Batch Processing & Ingestion Manifest**: Tracks files discovered, accepted, rejected, chunks created, warnings, and processing duration.

---

### Module 2 — Zero-Trust Enterprise RAG

<div align="center">

![Zero-Trust RAG Pipeline](docs/assets/aegis_rag_pipeline.png)

</div>

- **Pre-Retrieval Authorization Boundary**:
  - Permissions are resolved server-side into a trusted `UserContext` (`user_id`, `tenant_id`, `department`, `clearance_level`).
  - ChromaDB queries enforce multi-tenant isolation and department boundaries using strict pre-retrieval `$and` filters:
    ```json
    {
      "$and": [
        { "tenant_id": { "$eq": "tenant_alpha" } },
        { "access_tier": { "$lte": 3 } },
        { "department": { "$in": ["finance", "general"] } }
      ]
    }
    ```
  - Low-clearance users receive zero metadata snippets, filenames, or existence confirmations for restricted corporate documents.
- **Hybrid Retrieval (Dense + BM25)**: Dense semantic vectors combined with exact keyword/SKU matching via Okapi BM25 and Reciprocal Rank Fusion (RRF with $k=60$).
- **Cross-Encoder Reranker**: Top candidate passages rescored using semantic cross-attention proxies and term proximity.
- **Prompt Injection Defense**: Direct injection queries (system overrides, jailbreaks) are rejected at the boundary; indirect document injections are sanitized with `[REDACTED_ADVERSARIAL_INSTRUCTION]`.
- **Proof-of-Evidence Grounding**: Model generates strict citations (`[Source: filename | Page: X]`); citations are verified against actual retrieved text passages. If evidence is missing, conflicting, or unverified, the system safely abstains with `INSUFFICIENT_AUTHORIZED_EVIDENCE`.

---

### Module 3 — Policy-Governed ERP/CRM Agent

<div align="center">

![Governed Agent Architecture](docs/assets/aegis_agent_workflow.png)

</div>

- **Sandboxed Tool Registry**:
  - Read tools: `inventory_lookup`, `customer_lookup`, `ticket_status_lookup`, `transaction_status_verify` (Auto-approved).
  - Sensitive write tools: `lead_status_update`, `support_ticket_create` (Human approval required).
- **Mandatory 9-Stage Execution Pipeline**:
  `REQUEST → INTENT PARSING → SCHEMA VALIDATION → IDENTITY CHECK → POLICY DECISION → APPROVAL GATE → EXECUTION → POSTCONDITION VERIFICATION → AUDIT`.
- **Approval Ledger & Anti-Replay Nonces**:
  - Pending actions generate an approval token bound to `SHA-256(canonical_json(arguments))`.
  - Enforces a 15-minute expiring TTL (`AEGIS_APPROVAL_TTL_SECONDS=900`).
  - Tokens are strictly single-use; replaying consumed tokens returns `403 Forbidden`. Modifying argument values invalidates the token.
- **Idempotency & Reconciliation**:
  - All write operations require an `idempotency_key`. Duplicate submissions return cached transaction results without re-executing side effects.
  - Transient failures retry with exponential backoff (0.05s, 0.1s, 0.2s) or transition to an explicit `RECONCILING` state.

---

### Module 4 — Secure Runtime & Telemetry
- **FastAPI Asynchronous Gateway**: Clean route modularization (`/health`, `/api/v1/ingest`, `/api/v1/search`, `/api/v1/rag`, `/api/v1/agent`).
- **Prometheus Telemetry**: Real-time request counts, latency histograms, and failure metrics without placing sensitive prompts or tokens in metric labels.
- **Request Correlation**: Automatic `X-Correlation-ID` extraction and tracing across structured JSON logs.
- **Hardened Deployment**: Dedicated non-root user `appuser:10001` with `no-new-privileges: true` and persistent Docker volumes.

---

## Empirical Benchmark Performance

<div align="center">

![LinkedIn Showcase](image.png)

</div>

The platform underwent automated benchmark evaluation against multi-tenant financial reports, HR policies, warehouse inventories, incident response playbooks, and adversarial injection vectors.

| Metric | Measured Outcome | Target SLA | Compliance Verdict |
| :--- | :---: | :---: | :---: |
| **Ingestion Throughput** | **29.56 docs/sec** | > 5.0 docs/sec | **EXCEEDED** |
| **Retrieval Recall@5** | **100.0%** | > 85.0% | **EXCEEDED** |
| **Citation Grounding Rate** | **100.0%** | > 90.0% | **EXCEEDED** |
| **Abstention Accuracy** | **100.0%** | 100.0% | **EXCEEDED** |
| **Unauthorized Access Denial** | **100.0%** | 100.0% | **EXCEEDED** |
| **RAG Latency (p50)** | **8.2 ms** | < 150.0 ms | **EXCEEDED** |
| **RAG Latency (p95)** | **10.7 ms** | < 300.0 ms | **EXCEEDED** |
| **RAG Latency (p99)** | **67.6 ms** | < 500.0 ms | **EXCEEDED** |
| **Agent Action Latency (p50)** | **9.23 ms** | < 100.0 ms | **EXCEEDED** |
| **Automated Test Suite** | **20 / 20 PASS** | 100.0% | **EXCEEDED** |

*See full details in [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md) and [TEST_REPORT.md](TEST_REPORT.md).*

---

## Quickstart & Setup Guide

### 1. Installation
```powershell
# Clone repository
git clone git@github.com:vijaymahes9080/Datheon_Forward_Deployed_Engineering_Internship.git
cd Datheon_Forward_Deployed_Engineering_Internship/vj

# Install in editable mode
pip install -e .
```

### 2. Environment Configuration
```powershell
cp .env.example .env
```

### 3. Generate Enterprise Corpus & Execute Benchmarks
```powershell
python benchmarks/generate_corpus.py
python benchmarks/run_benchmark.py
```

### 4. Run Complete Automated Test Suite
```powershell
pytest tests -v
```

### 5. Launch Local Server
```powershell
python -m uvicorn aegis.api.server:app --host 0.0.0.0 --port 8000
```
- Swagger Interactive Docs: `http://localhost:8000/docs`
- Prometheus Metrics: `http://localhost:8000/metrics`
- Liveness Probe: `http://localhost:8000/health/live`
- Readiness Probe: `http://localhost:8000/health/ready`

---

## Docker Deployment

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f aegis-gateway
```

---

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
