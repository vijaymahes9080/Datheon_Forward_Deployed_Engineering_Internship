# AegisAI Enterprise Gateway — Client Deployment & Infrastructure Integration Guide

## 1. Overview & Scope

This guide provides instructions for deploying AegisAI Enterprise Gateway into client infrastructure, progressing from local container integration to production enterprise VPC environments.

---

## 2. Local Container Integration

The local deployment package consists of:
- `Dockerfile`: Multi-stage, non-root user `appuser:10001`
- `docker-compose.yml`: Local storage volumes, container health checks, and resource limits.

### Startup
```bash
docker compose up -d --build
docker compose ps
```

### Health Verification
```bash
curl -f http://localhost:8000/health/live
curl -f http://localhost:8000/health/ready
```

---

## 3. Production Enterprise VPC Requirements

The Docker Compose configuration is suitable for integration testing. For production VPC deployment, implement the following enterprise controls:

### 3.1 Network Topology & Microsegmentation
- **Private Subnets**: Deploy the Aegis Gateway pods in private application subnets with zero direct public ingress.
- **Application Load Balancer (ALB)**: Terminate TLS 1.3 at the external/internal ingress controller with WAF inspection.
- **Egress Restrictions**: Restrict outbound egress via NAT Gateway or VPC Endpoints; block unapproved external internet destinations.

### 3.2 Enterprise Identity & Single Sign-On (SSO)
- Replace static test tokens with **OIDC / OAuth 2.0 Identity Providers** (e.g. Okta, Azure Active Directory, Keycloak).
- Map enterprise claims:
  - `tenant_id` -> Identity provider org/tenant claim.
  - `groups` -> Map to Aegis roles (`viewer`, `analyst`, `operator`, `manager`, `admin`).
  - `security_clearance` -> Map to user clearance tier (1 to 4).

### 3.3 Managed Secret Vaults
- Do not store master secrets in `.env` files.
- Inject secrets dynamically using **HashiCorp Vault**, **AWS Secrets Manager**, or **GCP Secret Manager** via Kubernetes CSI Secret Store drivers.

### 3.4 Persistent Storage & Backup Architecture
- **Vector Storage**: For high-availability multi-node vector search, deploy a distributed vector cluster (e.g. **Qdrant Cloud / Self-Hosted Distributed Cluster** or Chroma with persistent EBS/PersistentVolumeClaims).
- **Metadata Database**: Migrate SQLite to a managed **PostgreSQL 16+** multi-AZ cluster with automated point-in-time recovery (PITR).
- **Backup Schedule**: Daily encrypted snapshots of vector indexes and PostgreSQL transaction ledgers.

### 3.5 Monitoring & Telemetry
- Configure enterprise Prometheus/Grafana or Datadog agents to scrape the `/metrics` endpoint.
- Export structured JSON logs to central SIEM (Splunk, Elastic, or CloudWatch) for real-time security auditing.
