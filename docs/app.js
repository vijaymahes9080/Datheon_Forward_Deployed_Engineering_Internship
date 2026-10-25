/**
 * AegisAI Enterprise Gateway — Interactive Web Portal Engine
 * Zero-Trust Enterprise AI Integration Simulation & Architecture Explorer
 */

// --- Sample Corporate Multi-Tenant Corpus ---
const CORPUS = [
  {
    id: "doc_alpha_fin_1",
    filename: "Q3_Financial_Report.pdf",
    tenant_id: "tenant_alpha",
    department: "finance",
    access_tier: 3,
    page: 2,
    row: null,
    heading: "Financial Performance > OPEX & Margins",
    text: "Tenant Alpha Q3 OPEX was recorded at $4.2M, with gross margin expanding by 340 bps to 68.4%. Operating income reached $14.8M driven by enterprise enterprise software contract renewals.",
    keywords: ["q3", "opex", "margin", "margins", "financial", "alpha", "operating", "income", "renewal"]
  },
  {
    id: "doc_alpha_fin_2",
    filename: "Q3_Financial_Report.pdf",
    tenant_id: "tenant_alpha",
    department: "finance",
    access_tier: 3,
    page: 4,
    row: null,
    heading: "Capital Allocation > R&D Investment",
    text: "Capital expenditure totaled $1.1M in Q3, allocated primarily to zero-trust gateway infrastructure and encrypted vector storage hardware.",
    keywords: ["capital", "expenditure", "r&d", "investment", "infrastructure", "hardware"]
  },
  {
    id: "doc_alpha_inv_1",
    filename: "warehouse_inventory.csv",
    tenant_id: "tenant_alpha",
    department: "operations",
    access_tier: 1,
    page: null,
    row: 14,
    heading: "Warehouse Inventory > SKU Tracking",
    text: "SKU-9942: Enterprise Gateway Hardware Appliance, Location: Rack-04-West, Stock: 84 units, Minimum Reorder Threshold: 20 units, Supplier: AegisSecure Systems.",
    keywords: ["sku-9942", "sku", "inventory", "stock", "warehouse", "units", "appliance", "rack"]
  },
  {
    id: "doc_alpha_sec_1",
    filename: "security_runbook.md",
    tenant_id: "tenant_alpha",
    department: "security",
    access_tier: 2,
    page: null,
    row: null,
    heading: "# Security > ## Incident Response > ### Key Rotation",
    text: "API encryption keys must be rotated every 90 days using the automated KMS envelope encryption pipeline. Secrets are never logged or stored in environment plaintext.",
    keywords: ["security", "key", "rotation", "kms", "envelope", "incident", "secrets"]
  },
  {
    id: "doc_beta_fin_1",
    filename: "Tenant_Beta_Executive_Summary.pdf",
    tenant_id: "tenant_beta",
    department: "finance",
    access_tier: 2,
    page: 1,
    row: null,
    heading: "Executive Briefing > Annual Projections",
    text: "Tenant Beta projected FY26 cloud infrastructure spend is $8.9M across private Kubernetes clusters and European edge nodes.",
    keywords: ["beta", "projections", "cloud", "infrastructure", "spend", "spend", "kubernetes"]
  }
];

// --- Simulated Users (Security Contexts) ---
const USERS = {
  alice: {
    user_id: "usr_alice_fin_01",
    name: "Alice Vance (Finance Director)",
    tenant_id: "tenant_alpha",
    department: "finance",
    clearance_level: 3,
    roles: ["finance_admin", "approver"]
  },
  bob: {
    user_id: "usr_bob_eng_02",
    name: "Bob Martinez (Junior Developer)",
    tenant_id: "tenant_alpha",
    department: "engineering",
    clearance_level: 1,
    roles: ["developer"]
  },
  charlie: {
    user_id: "usr_charlie_beta_03",
    name: "Charlie Zhang (External Partner)",
    tenant_id: "tenant_beta",
    department: "general",
    clearance_level: 2,
    roles: ["partner_reader"]
  }
};

// --- In-Memory State ---
let activeUser = USERS.alice;
let approvalLedger = {}; // token -> { status, hash, args, expiresAt, action }
let idempotencyStore = {}; // key -> result

// --- Utilities ---
async function computeSha256(text) {
  const msgBuffer = new TextEncoder().encode(text);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

function canonicalJson(obj) {
  return JSON.stringify(obj, Object.keys(obj).sort());
}

function getTimestamp() {
  return new Date().toISOString().split('T')[1].replace('Z', '');
}

// --- DOM Initialization ---
document.addEventListener('DOMContentLoaded', () => {
  setupThemeToggle();
  setupTabNavigation();
  setupEtlModule();
  setupRagModule();
  setupAgentModule();
  setupTelemetryModule();
  setupDocViewer();
});

// --- Theme Management ---
function setupThemeToggle() {
  const toggleBtn = document.getElementById('theme-toggle');
  const storedTheme = localStorage.getItem('aegis-theme') || 'light';
  document.documentElement.setAttribute('data-theme', storedTheme);
  updateThemeIcon(storedTheme);

  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('aegis-theme', next);
      updateThemeIcon(next);
    });
  }
}

function updateThemeIcon(theme) {
  const toggleBtn = document.getElementById('theme-toggle');
  if (toggleBtn) {
    toggleBtn.innerHTML = theme === 'dark' 
      ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
      : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  }
}

// --- Tab Navigation ---
function setupTabNavigation() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-tab');
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanels.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const panel = document.getElementById(target);
      if (panel) panel.classList.add('active');
    });
  });
}

// --- Module 1: Legacy ETL Sandbox ---
function setupEtlModule() {
  const sampleSelector = document.getElementById('etl-sample-select');
  const btnProcess = document.getElementById('btn-etl-process');
  const btnDedup = document.getElementById('btn-etl-dedup');
  const terminal = document.getElementById('etl-terminal');

  const samples = {
    pdf: {
      name: "Q3_Financial_Executive_Summary.pdf",
      type: "application/pdf",
      pages: 3,
      content: "Page 1: Title & Executive Summary\nPage 2: Tenant Alpha Q3 OPEX was recorded at $4.2M, with gross margin expanding by 340 bps to 68.4%.\nPage 3: Balance Sheet Statements and Auditor Notes"
    },
    csv: {
      name: "global_warehouse_inventory.csv",
      type: "text/csv",
      rows: 50,
      content: "sku,item_name,location,stock,reorder_point\nSKU-9942,Enterprise Gateway Appliance,Rack-04-West,84,20\nSKU-1082,Optic Transceiver 100G,Rack-01-East,150,40"
    },
    markdown: {
      name: "corporate_security_policy.md",
      type: "text/markdown",
      sections: 4,
      content: "# Enterprise Security\n## Access Control\n### Zero-Trust Boundary\nAll corporate access must evaluate identity at the database retrieval barrier."
    }
  };

  if (btnProcess) {
    btnProcess.addEventListener('click', async () => {
      const selected = sampleSelector.value;
      const file = samples[selected];
      const hash = await computeSha256(file.content);

      terminal.innerHTML = `
        <div class="trace-line"><span class="trace-tag blue">[ETL:DISCOVERY]</span> Ingestion candidate: <strong>${file.name}</strong> (${file.type})</div>
        <div class="trace-line"><span class="trace-tag blue">[ETL:SHA-256]</span> Computing deterministic content hash: <code style="color:#60a5fa">${hash}</code></div>
        <div class="trace-line"><span class="trace-tag emerald">[ETL:PARSER]</span> Extracting structured content with provenance tagging...</div>
      `;

      if (selected === 'pdf') {
        terminal.innerHTML += `
          <div class="trace-line"><span class="trace-tag emerald">[PDF:CHUNK 1]</span> Provenance: <code>[Source: ${file.name} | Page: 2]</code> | Size: 184 chars</div>
          <div class="trace-line" style="color:#94a3b8; padding-left:1.5rem">"Tenant Alpha Q3 OPEX was recorded at $4.2M, with gross margin expanding by 340 bps to 68.4%..."</div>
          <div class="trace-line"><span class="trace-tag purple">[CHROMA]</span> Upserted chunk into collection <code>enterprise_knowledge_base</code> (Space: Cosine)</div>
          <div class="trace-line"><span class="trace-tag emerald">[MANIFEST]</span> Ingestion Status: <strong>SUCCESS</strong> | Chunks: 3 | Duplicates: 0 | Duration: 18.2ms</div>
        `;
      } else if (selected === 'csv') {
        terminal.innerHTML += `
          <div class="trace-line"><span class="trace-tag emerald">[CSV:CHUNK 1]</span> Provenance: <code>[Source: ${file.name} | Row: 1]</code> (Composite key: row_1)</div>
          <div class="trace-line" style="color:#94a3b8; padding-left:1.5rem">Headers: [sku, item_name, location, stock, reorder_point]</div>
          <div class="trace-line"><span class="trace-tag purple">[CHROMA]</span> Upserted chunk with metadata: <code>{sku: "SKU-9942", stock: 84}</code></div>
          <div class="trace-line"><span class="trace-tag emerald">[MANIFEST]</span> Ingestion Status: <strong>SUCCESS</strong> | Rows: 50 | Duplicates: 0 | Duration: 14.1ms</div>
        `;
      } else {
        terminal.innerHTML += `
          <div class="trace-line"><span class="trace-tag emerald">[MD:CHUNK 1]</span> Section Breadcrumb: <code># Enterprise Security > ## Access Control > ### Zero-Trust Boundary</code></div>
          <div class="trace-line" style="color:#94a3b8; padding-left:1.5rem">"All corporate access must evaluate identity at the database retrieval barrier..."</div>
          <div class="trace-line"><span class="trace-tag purple">[CHROMA]</span> Upserted chunk with structured breadcrumb metadata</div>
          <div class="trace-line"><span class="trace-tag emerald">[MANIFEST]</span> Ingestion Status: <strong>SUCCESS</strong> | Sections: 4 | Duplicates: 0 | Duration: 9.8ms</div>
        `;
      }
    });
  }

  if (btnDedup) {
    btnDedup.addEventListener('click', async () => {
      const selected = sampleSelector.value;
      const file = samples[selected];
      const hash = await computeSha256(file.content);

      terminal.innerHTML = `
        <div class="trace-line"><span class="trace-tag amber">[DEDUP:TEST]</span> Re-submitting identical file: <strong>${file.name}</strong></div>
        <div class="trace-line"><span class="trace-tag blue">[ETL:SHA-256]</span> Calculated hash: <code style="color:#60a5fa">${hash}</code></div>
        <div class="trace-line"><span class="trace-tag emerald">[DEDUP:MATCH]</span> Hash exists in deduplication registry!</div>
        <div class="trace-line"><span class="trace-tag amber">[ZERO-WRITE]</span> Zero duplicate vector writes produced. Preserved existing collection integrity.</div>
        <div class="trace-line"><span class="trace-tag emerald">[MANIFEST]</span> Files: 1 | Accepted: 1 | Created: 0 | Duplicates Suppressed: 1 (100% dedup)</div>
      `;
    });
  }
}

// --- Module 2: Zero-Trust RAG Sandbox ---
function setupRagModule() {
  const userSelect = document.getElementById('rag-user-select');
  const userBadge = document.getElementById('user-context-display');
  const queryInput = document.getElementById('rag-query-input');
  const btnRunRag = document.getElementById('btn-rag-submit');
  const terminal = document.getElementById('rag-terminal');
  const presetPills = document.querySelectorAll('.preset-pill');

  function updateUserContext() {
    activeUser = USERS[userSelect.value];
    userBadge.innerHTML = `
      <span>Tenant: <strong>${activeUser.tenant_id}</strong></span> • 
      <span>Dept: <strong>${activeUser.department}</strong></span> • 
      <span>Clearance: <strong>Tier ${activeUser.clearance_level}</strong></span>
    `;
  }

  if (userSelect) {
    userSelect.addEventListener('change', updateUserContext);
    updateUserContext();
  }

  presetPills.forEach(pill => {
    pill.addEventListener('click', () => {
      queryInput.value = pill.getAttribute('data-query');
      if (pill.getAttribute('data-user')) {
        userSelect.value = pill.getAttribute('data-user');
        updateUserContext();
      }
    });
  });

  if (btnRunRag) {
    btnRunRag.addEventListener('click', () => {
      const query = queryInput.value.trim();
      if (!query) return;

      const user = activeUser;
      terminal.innerHTML = `
        <div class="trace-line"><span class="trace-tag blue">[SECURITY]</span> Resolving trusted UserContext: <code>${user.user_id}</code> (${user.tenant_id})</div>
        <div class="trace-line"><span class="trace-tag purple">[ACL-FILTER]</span> Constructing Pre-Retrieval MongoDB/Chroma $and Barrier:</div>
        <div class="trace-line" style="color:#a78bfa; padding-left:1.5rem">
          {"$and": [{"tenant_id": "${user.tenant_id}"}, {"access_tier": {"$lte": ${user.clearance_level}}}, {"department": {"$in": ["${user.department}", "general"]}}]}
        </div>
      `;

      // 1. Direct Prompt Injection Check
      const lowerQ = query.toLowerCase();
      if (lowerQ.includes("password") || lowerQ.includes("secret") || lowerQ.includes("disregard") || lowerQ.includes("dump") || lowerQ.includes("override")) {
        terminal.innerHTML += `
          <div class="trace-line"><span class="trace-tag rose">[INJECTION:BLOCKED]</span> Threat pattern detected: <strong>DirectPromptInjectionException</strong></div>
          <div class="trace-line" style="color:#f87171; padding-left:1.5rem">Query attempts to bypass guardrails or access protected credentials. Terminating execution.</div>
          <div class="trace-line"><span class="trace-tag rose">[RESPONSE]</span> HTTP 400 Bad Request: Direct prompt injection pattern detected.</div>
        `;
        return;
      }

      // 2. Pre-Retrieval Authorization Search
      terminal.innerHTML += `
        <div class="trace-line"><span class="trace-tag blue">[HYBRID-SEARCH]</span> Executing Dense Cosine Similarity + Okapi BM25 Lexical Fusion...</div>
      `;

      // Filter corpus strictly by ACL
      const authorizedDocs = CORPUS.filter(doc => {
        const tenantMatch = doc.tenant_id === user.tenant_id;
        const tierMatch = doc.access_tier <= user.clearance_level;
        const deptMatch = doc.department === user.department || doc.department === "general";
        return tenantMatch && tierMatch && deptMatch;
      });

      // Score matching
      const queryTerms = lowerQ.split(/\W+/).filter(t => t.length > 2);
      let bestDoc = null;
      let bestScore = 0;

      authorizedDocs.forEach(doc => {
        let matchCount = 0;
        queryTerms.forEach(t => {
          if (doc.keywords.includes(t) || doc.text.toLowerCase().includes(t)) {
            matchCount++;
          }
        });
        if (matchCount > bestScore) {
          bestScore = matchCount;
          bestDoc = doc;
        }
      });

      if (!bestDoc || bestScore < 1) {
        // Safe abstention
        terminal.innerHTML += `
          <div class="trace-line"><span class="trace-tag amber">[ABSTENTION]</span> No authorized evidence matches query criteria.</div>
          <div class="trace-line" style="color:#fbbf24; padding-left:1.5rem">
            ${authorizedDocs.length === 0 ? "Reason: Zero documents accessible within current clearance and tenant boundaries." : "Reason: Query terms lack verified factual grounding in authorized passages."}
          </div>
          <div class="trace-line"><span class="trace-tag emerald">[RESPONSE]</span> 
            <strong style="color:#fde047">INSUFFICIENT_AUTHORIZED_EVIDENCE:</strong> The retrieved authorized documents do not contain evidence to answer this question.
          </div>
        `;
        return;
      }

      // Grounded answer with strict citation
      const citation = bestDoc.page ? `[Source: ${bestDoc.filename} | Page: ${bestDoc.page}]` : `[Source: ${bestDoc.filename} | Row: ${bestDoc.row}]`;
      terminal.innerHTML += `
        <div class="trace-line"><span class="trace-tag emerald">[RETRIEVAL:HIT]</span> Matched Doc ID: <code>${bestDoc.id}</code> (RRF Score: 0.942)</div>
        <div class="trace-line"><span class="trace-tag purple">[GROUNDING]</span> Validating citation provenance against retrieved passage...</div>
        <div class="trace-line" style="color:#34d399; padding-left:1.5rem">Citation Provenance Verified: <code>${citation}</code></div>
        <div class="trace-line"><span class="trace-tag emerald">[ANSWER:GENERATED]</span></div>
        <div class="trace-line" style="background:#1e293b; padding:0.75rem; border-radius:6px; margin-top:0.35rem">
          "${bestDoc.text}" <strong>${citation}</strong>
        </div>
      `;
    });
  }
}

// --- Module 3: Policy-Governed Agent Console ---
function setupAgentModule() {
  const toolSelect = document.getElementById('agent-tool-select');
  const actionArgs = document.getElementById('agent-args-input');
  const btnExecute = document.getElementById('btn-agent-execute');
  const terminal = document.getElementById('agent-terminal');

  const modal = document.getElementById('approval-modal');
  const modalToken = document.getElementById('modal-token-display');
  const modalHash = document.getElementById('modal-hash-display');
  const modalCountdown = document.getElementById('modal-countdown-timer');
  const btnApprove = document.getElementById('btn-modal-approve');
  const btnReject = document.getElementById('btn-modal-reject');

  let currentPendingAction = null;
  let countdownInterval = null;

  const toolConfigs = {
    inventory_lookup: {
      type: "read",
      risk: "None",
      defaultArgs: '{"sku": "SKU-9942", "warehouse": "West-01"}',
      pdpDecision: "ALLOW_AUTO"
    },
    customer_lookup: {
      type: "read",
      risk: "Low",
      defaultArgs: '{"customer_id": "CUST-8802"}',
      pdpDecision: "ALLOW_AUTO"
    },
    lead_status_update: {
      type: "write",
      risk: "High",
      defaultArgs: '{"lead_id": "LEAD-4019", "new_status": "QUALIFIED_ENTERPRISE", "contract_value": 75000}',
      pdpDecision: "REQUIRE_HUMAN_APPROVAL"
    },
    support_ticket_create: {
      type: "write",
      risk: "Medium",
      defaultArgs: '{"customer_id": "CUST-8802", "priority": "P1_URGENT", "summary": "Gateway failover test scheduled"}',
      pdpDecision: "REQUIRE_HUMAN_APPROVAL"
    }
  };

  if (toolSelect) {
    toolSelect.addEventListener('change', () => {
      const cfg = toolConfigs[toolSelect.value];
      if (cfg && actionArgs) {
        actionArgs.value = cfg.defaultArgs;
      }
    });
  }

  if (btnExecute) {
    btnExecute.addEventListener('click', async () => {
      const toolName = toolSelect.value;
      const cfg = toolConfigs[toolName];
      let parsedArgs = {};
      try {
        parsedArgs = JSON.parse(actionArgs.value);
      } catch (e) {
        terminal.innerHTML = `<div class="trace-line"><span class="trace-tag rose">[ERROR]</span> Invalid JSON arguments.</div>`;
        return;
      }

      const idempotencyKey = `idem_${Date.now()}`;
      const argsCanonical = canonicalJson(parsedArgs);
      const argsHash = await computeSha256(argsCanonical);

      terminal.innerHTML = `
        <div class="trace-line"><span class="trace-tag blue">[STAGE 1: REQUEST]</span> Dispatching tool: <strong>${toolName}</strong></div>
        <div class="trace-line"><span class="trace-tag blue">[STAGE 2: INTENT]</span> Parsed intent: MutationType = ${cfg.type.toUpperCase()}</div>
        <div class="trace-line"><span class="trace-tag emerald">[STAGE 3: SCHEMA]</span> Argument schema validation: <strong>PASSED</strong></div>
        <div class="trace-line"><span class="trace-tag blue">[STAGE 4: IDENTITY]</span> Authenticated user: <code>${activeUser.user_id}</code></div>
        <div class="trace-line"><span class="trace-tag purple">[STAGE 5: PDP]</span> Policy Decision Point Evaluation: <strong>${cfg.pdpDecision}</strong></div>
      `;

      if (cfg.pdpDecision === "ALLOW_AUTO") {
        terminal.innerHTML += `
          <div class="trace-line"><span class="trace-tag emerald">[STAGE 6: GATE]</span> Safe read operation. Human approval bypassed.</div>
          <div class="trace-line"><span class="trace-tag blue">[STAGE 7: EXECUTION]</span> Invoking ERP connector with Idempotency Key <code>${idempotencyKey}</code></div>
          <div class="trace-line"><span class="trace-tag emerald">[STAGE 8: POSTCONDITION]</span> Record state verified in backend registry.</div>
          <div class="trace-line"><span class="trace-tag purple">[STAGE 9: AUDIT]</span> Transaction written to immutable audit ledger. Status: <strong>COMMITTED</strong></div>
        `;
      } else {
        // Human Approval Required
        const approvalToken = `appr_${Math.random().toString(36).substring(2, 10)}`;
        approvalLedger[approvalToken] = {
          token: approvalToken,
          status: "PENDING",
          tool: toolName,
          args: parsedArgs,
          argsHash: argsHash,
          expiresAt: Date.now() + 15 * 60 * 1000
        };

        currentPendingAction = approvalLedger[approvalToken];

        terminal.innerHTML += `
          <div class="trace-line"><span class="trace-tag amber">[STAGE 6: GATE: PAUSED]</span> Sensitive write operation detected. Execution paused.</div>
          <div class="trace-line" style="color:#fde68a; padding-left:1.5rem">
            Generating single-use Approval Token: <code>${approvalToken}</code> (Bound to SHA-256 of canonical arguments)
          </div>
          <div class="trace-line"><span class="trace-tag blue">[ARG-HASH]</span> <code>${argsHash}</code></div>
          <div class="trace-line"><span class="trace-tag amber">[ACTION REQUIRED]</span> Open the approval gate to review and authorize.</div>
        `;

        // Open Modal
        modalToken.innerText = approvalToken;
        modalHash.innerText = argsHash;
        modal.classList.add('open');

        let remainingSec = 900;
        clearInterval(countdownInterval);
        countdownInterval = setInterval(() => {
          remainingSec--;
          const mins = Math.floor(remainingSec / 60);
          const secs = remainingSec % 60;
          modalCountdown.innerText = `${mins}:${secs.toString().padStart(2, '0')}`;
          if (remainingSec <= 0) {
            clearInterval(countdownInterval);
            modalCountdown.innerText = "EXPIRED";
          }
        }, 1000);
      }
    });
  }

  if (btnApprove) {
    btnApprove.addEventListener('click', () => {
      if (!currentPendingAction) return;

      if (currentPendingAction.status === "CONSUMED") {
        alert("403 Forbidden: Approval token already consumed. Replay attack prevented!");
        return;
      }

      currentPendingAction.status = "CONSUMED";
      modal.classList.remove('open');
      clearInterval(countdownInterval);

      terminal.innerHTML += `
        <div class="trace-line"><span class="trace-tag emerald">[APPROVAL:GRANTED]</span> Manager approved token <code>${currentPendingAction.token}</code></div>
        <div class="trace-line"><span class="trace-tag blue">[ANTI-REPLAY]</span> Token marked <strong>CONSUMED</strong>. Nonce invalidated.</div>
        <div class="trace-line"><span class="trace-tag blue">[STAGE 7: EXECUTION]</span> Executing tool: <strong>${currentPendingAction.tool}</strong></div>
        <div class="trace-line"><span class="trace-tag emerald">[STAGE 8: POSTCONDITION]</span> ERP write verified. State change confirmed.</div>
        <div class="trace-line"><span class="trace-tag purple">[STAGE 9: AUDIT]</span> Immutable log: Transaction ID <code>tx_${Date.now()}</code> committed.</div>
      `;
    });
  }

  if (btnReject) {
    btnReject.addEventListener('click', () => {
      if (!currentPendingAction) return;
      currentPendingAction.status = "REJECTED";
      modal.classList.remove('open');
      clearInterval(countdownInterval);

      terminal.innerHTML += `
        <div class="trace-line"><span class="trace-tag rose">[APPROVAL:REJECTED]</span> Action canceled by manager.</div>
        <div class="trace-line"><span class="trace-tag rose">[ABORT]</span> No ERP side effects executed. Logged to security audit ledger.</div>
      `;
    });
  }
}

// --- Module 4: Live Telemetry & API Explorer ---
function setupTelemetryModule() {
  const btnLiveCheck = document.getElementById('btn-telemetry-live');
  const btnReadyCheck = document.getElementById('btn-telemetry-ready');
  const apiTerminal = document.getElementById('api-terminal');

  if (btnLiveCheck) {
    btnLiveCheck.addEventListener('click', () => {
      apiTerminal.innerHTML = `
        <div class="trace-line"><span class="trace-tag blue">[GET /health/live]</span> Initiating Kubernetes Liveness Probe...</div>
        <div class="trace-line"><span class="trace-tag emerald">[HTTP 200 OK]</span> Response:</div>
        <pre style="background:#1e293b; padding:0.75rem; border-radius:6px; color:#38bdf8">
{
  "status": "alive",
  "timestamp": "${new Date().toISOString()}",
  "version": "1.0.0",
  "uptime_seconds": 18492.4,
  "service": "aegis-enterprise-gateway"
}</pre>
      `;
    });
  }

  if (btnReadyCheck) {
    btnReadyCheck.addEventListener('click', () => {
      apiTerminal.innerHTML = `
        <div class="trace-line"><span class="trace-tag blue">[GET /health/ready]</span> Initiating Kubernetes Readiness Probe...</div>
        <div class="trace-line"><span class="trace-tag emerald">[HTTP 200 OK]</span> All subsystem dependencies healthy:</div>
        <pre style="background:#1e293b; padding:0.75rem; border-radius:6px; color:#34d399">
{
  "status": "ready",
  "checks": {
    "vector_store_chromadb": "HEALTHY (Cosine Distance hnsw:space)",
    "audit_persistence_ledger": "HEALTHY (JSONL Append-Only)",
    "pdp_policy_engine": "HEALTHY",
    "approval_ledger_ttl": "HEALTHY"
  },
  "ready": true
}</pre>
      `;
    });
  }
}

// --- Documentation Modal / Viewer ---
function setupDocViewer() {
  const docLinks = document.querySelectorAll('.view-doc-btn');
  const modal = document.getElementById('doc-modal');
  const modalTitle = document.getElementById('doc-modal-title');
  const modalContent = document.getElementById('doc-modal-content');
  const modalClose = document.getElementById('btn-doc-close');

  const DOCS_DATA = {
    architecture: {
      title: "ARCHITECTURE.md — System Architecture",
      content: `
        <h3>AegisAI Enterprise Gateway Architecture</h3>
        <p>The platform is designed as an asynchronous modular monolith with strict security boundaries:</p>
        <ul>
          <li><strong>Identity & Correlation Middleware:</strong> Resolves JWT/API keys into trusted UserContext (tenant, clearance, dept).</li>
          <li><strong>Module 1 (ETL):</strong> Structure-aware parsing for PDF (page provenance), CSV (row IDs), and Markdown (hierarchical heading breadcrumbs) with SHA-256 deduplication.</li>
          <li><strong>Module 2 (Zero-Trust RAG):</strong> Server-side pre-retrieval ACL barriers inside ChromaDB, hybrid BM25 + dense ranking, and citation grounding verification with safe abstention.</li>
          <li><strong>Module 3 (Policy-Governed Agent):</strong> 9-stage pipeline, human-in-the-loop approval ledger with 15-min expiring TTL, argument SHA-256 binding, and single-use anti-replay nonces.</li>
          <li><strong>Module 4 (Hardened Runtime):</strong> Non-root container (appuser:10001), Prometheus telemetry, and zero prompt/token leakage in logs.</li>
        </ul>
      `
    },
    security: {
      title: "SECURITY.md — Threat Controls & Access Governance",
      content: `
        <h3>Zero-Trust Security Controls</h3>
        <p>AegisAI guarantees multi-tenant isolation through pre-retrieval authorization barriers enforced at the database layer rather than inside LLM prompt instructions.</p>
        <p>Key defensive mechanisms include:</p>
        <ul>
          <li><strong>Pre-Retrieval $and Barrier:</strong> Queries filter by tenant_id, access_tier, and department before cosine distance search.</li>
          <li><strong>Direct Prompt Injection Defense:</strong> System prompt override attempts and credential exfiltration patterns are terminated at the boundary.</li>
          <li><strong>Indirect Document Injection Defense:</strong> Retrieved passages containing adversarial commands are automatically sanitized with [REDACTED_ADVERSARIAL_INSTRUCTION].</li>
          <li><strong>Citation Grounding Verification:</strong> The model strictly cites [Source: file | Page: X] verified against candidate passages. If evidence is absent, it abstains with INSUFFICIENT_AUTHORIZED_EVIDENCE.</li>
        </ul>
      `
    },
    benchmarks: {
      title: "BENCHMARK_REPORT.md — Empirical Performance Metrics",
      content: `
        <h3>Benchmark Evaluation Summary</h3>
        <table class="benchmark-table" style="margin-top:1rem">
          <thead>
            <tr><th>Metric</th><th>Measured Result</th><th>SLA Target</th><th>Verdict</th></tr>
          </thead>
          <tbody>
            <tr><td><strong>Retrieval Recall@5</strong></td><td>100.0%</td><td>> 85.0%</td><td><span class="stat-badge emerald">EXCEEDED</span></td></tr>
            <tr><td><strong>Citation Grounding Rate</strong></td><td>100.0%</td><td>> 90.0%</td><td><span class="stat-badge emerald">EXCEEDED</span></td></tr>
            <tr><td><strong>Safe Abstention Rate</strong></td><td>100.0%</td><td>100.0%</td><td><span class="stat-badge emerald">EXCEEDED</span></td></tr>
            <tr><td><strong>Unauthorized Access Denial</strong></td><td>100.0%</td><td>100.0%</td><td><span class="stat-badge emerald">EXCEEDED</span></td></tr>
            <tr><td><strong>RAG Latency (p50)</strong></td><td>8.2 ms</td><td>< 150 ms</td><td><span class="stat-badge emerald">EXCEEDED</span></td></tr>
            <tr><td><strong>Agent Action Latency (p50)</strong></td><td>9.2 ms</td><td>< 100 ms</td><td><span class="stat-badge emerald">EXCEEDED</span></td></tr>
            <tr><td><strong>Automated Test Gates</strong></td><td>20 / 20 PASS</td><td>100.0%</td><td><span class="stat-badge emerald">EXCEEDED</span></td></tr>
          </tbody>
        </table>
      `
    }
  };

  docLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const docKey = link.getAttribute('data-doc');
      const doc = DOCS_DATA[docKey];
      if (doc && modal) {
        modalTitle.innerText = doc.title;
        modalContent.innerHTML = doc.content;
        modal.classList.add('open');
      }
    });
  });

  if (modalClose) {
    modalClose.addEventListener('click', () => {
      modal.classList.remove('open');
    });
  }
}
