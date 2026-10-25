# AegisAI Enterprise Gateway — Zero-Trust Enterprise AI Integration Engine

[![Python 3.12](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Cosine-red.svg)](https://www.trychroma.com/)
[![License: Enterprise Proprietary](https://img.shields.io/badge/License-Enterprise-purple.svg)]()

**AegisAI Enterprise Gateway** is a zero-trust enterprise integration engine that connects unstructured corporate documents (PDF, CSV, Markdown) to mission-critical ERP/CRM business workflows with pre-retrieval authorization, citation-grounded RAG, and human-in-the-loop governance.

---

## Architecture at a Glance

```
                         [ Enterprise Client / User ]
                                      │ (TLS / JWT / API-Key)
                                      ▼
                        ┌───────────────────────────┐
                        │ FastAPI Gateway (Non-Root)│
                        │ • Correlation Middleware  │
                        │ • Identity & Context (RBAC│
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

## Core Engineering Modules

1. **Module 1 — Intelligent Legacy Data ETL**:
   - Structure-aware parsers for PDF (page-level provenance via `pypdf`), CSV (row-level identifier tracking), and Markdown (hierarchical heading breadcrumbs).
   - SHA-256 content-hash deduplication (reprocessing unchanged documents produces 0 duplicate records).
   - Explicit cosine distance vector indexing into ChromaDB.
   - Batch ingestion job tracking with structured manifest reports.

2. **Module 2 — Zero-Trust Enterprise RAG**:
   - Pre-retrieval authorization boundary enforcing multi-tenant isolation, department segregation, and clearance hierarchy before search execution.
   - Hybrid search combining dense embeddings with lexical Okapi BM25 through Reciprocal Rank Fusion (RRF).
   - Semantic cross-encoder reranker and token-bounded context assembler.
   - Real-time prompt injection defense neutralizing direct and indirect attacks.
   - Strict citation grounding validating citations against actual source pages/rows with automatic abstention (`INSUFFICIENT_AUTHORIZED_EVIDENCE`).

3. **Module 3 — Policy-Governed ERP/CRM Agent**:
   - Sandboxed enterprise tools (inventory lookup, customer lookup, lead status update, ticket creation, transaction reconciliation).
   - Strict 9-stage execution pipeline:
     `REQUEST → INTENT → SCHEMA → IDENTITY → POLICY → APPROVAL → EXECUTION → POSTCONDITION → AUDIT`.
   - Cryptographic argument-bound approval ledger with single-use anti-replay tokens and expiring TTLs.
   - Idempotency key tracking and bounded exponential backoff retries.

4. **Module 4 — Secure Runtime & Client Deployment**:
   - Hardened asynchronous FastAPI service with Prometheus observability (`/metrics`).
   - Liveness (`/health/live`) and readiness (`/health/ready`) probes.
   - Dedicated unprivileged non-root container user (`appuser:10001`).
   - Reproducible Docker Compose environment with persistent storage volumes.

---

## Quickstart & Local Setup

### Prerequisites
- Python 3.12+
- Git

### 1. Installation
```powershell
# Clone and enter workspace
git clone git@github.com:vijaymahes9080/Datheon_Forward_Deployed_Engineering_Internship.git
cd Datheon_Forward_Deployed_Engineering_Internship/vj

# Install in editable mode
pip install -e .
```

### 2. Environment Configuration
```powershell
cp .env.example .env
```

### 3. Generate Enterprise Corpus & Run Benchmarks
```powershell
python benchmarks/generate_corpus.py
python benchmarks/run_benchmark.py
```

### 4. Run the Full Test Suite
```powershell
pytest tests -v --cov=src/aegis
```

### 5. Launch the Server
```powershell
python -m uvicorn aegis.api.server:app --host 0.0.0.0 --port 8000
```
- Interactive API Docs: `http://localhost:8000/docs`
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

## Documentation Index

- [Architecture & Design Deep Dive](file:///ARCHITECTURE.md)
- [Security Architecture & Defense-in-Depth](file:///SECURITY.md)
- [Threat Model & Attack Trees](file:///THREAT_MODEL.md)
- [API Reference & Curl Examples](file:///API_GUIDE.md)
- [Client Deployment & VPC Integration Guide](file:///CLIENT_DEPLOYMENT_GUIDE.md)
- [Operations Runbook & Disaster Recovery](file:///OPERATIONS_RUNBOOK.md)
- [Empirical Benchmark Report](file:///BENCHMARK_REPORT.md)
- [Automated Test Report & Evidence Matrix](file:///TEST_REPORT.md)
