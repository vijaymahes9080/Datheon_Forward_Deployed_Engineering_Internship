# Aegis Corporate Security Incident Response Playbook

Document ID: SEC-IR-2026 | Department: Security | Clearance: Confidential (Tier 3)

## Phase 1: Triage and Severity Classification
When an alert is triggered by the SIEM, the on-call Security Operations Center (SOC) engineer must classify the incident:
- Severity 1 (Critical): Active data exfiltration, root compromise of production clusters, or ransomware. Initial triage SLA: 15 minutes.
- Severity 2 (High): Unauthorized privilege escalation, lateral movement detected, or critical vulnerability exploitation. Initial triage SLA: 30 minutes.
- Severity 3 (Medium): Isolated endpoint malware, unpatched non-critical server, policy violations. Initial triage SLA: 4 hours.

## Phase 2: Containment and Isolation Protocols
For any confirmed Severity 1 or 2 incident:
1. Revoke all active session tokens for affected identities immediately.
2. Isolate compromised workloads using Kubernetes NetworkPolicies and quarantine security groups.
3. Preserve ephemeral memory and system disk snapshots before terminating instances.
4. Notify the Chief Information Security Officer (CISO) and Legal counsel within 60 minutes.

## Phase 3: Eradication and Recovery Verification
- Scan all container registries and redeploy base images from verified immutable digests.
- Rotate all administrative database credentials, API secrets, and TLS certificates involved in the compromise path.
- Conduct continuous post-containment forensic analysis for a minimum of 72 hours before restoring production traffic.
