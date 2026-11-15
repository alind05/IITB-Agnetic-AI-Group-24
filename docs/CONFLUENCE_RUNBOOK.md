# Analyst Desk: Engineering Architecture, Deployment & Operations Handbook

**Document Reference:** KB-ENG-ANALYSTDESK-001  
**Target Audience:** Software Engineers, Site Reliability Engineers (SRE), Production Support Analysts, and Technical Evaluators  
**Last Updated:** November 2026  
**System Status:** Production Ready (v1.0.0)  

---

## Table of Contents
1. [Executive Summary & Problem Statement](#1-executive-summary--problem-statement)
2. [Core Architecture & System Principles](#2-core-architecture--system-principles)
3. [End-to-End Execution Flow (Step-by-Step Lifecycle)](#3-end-to-end-execution-flow)
4. [Service Directory & Network Topology](#4-service-directory--network-topology)
5. [Environment Setup & Startup Runbooks](#5-environment-setup--startup-runbooks)
6. [Configuration Dictionary & Secrets Management](#6-configuration-dictionary--secrets-management)
7. [API Contract & Streaming Protocols](#7-api-contract--streaming-protocols)
8. [Observability, Telemetry & SLA Thresholds](#8-observability-telemetry--sla-thresholds)
9. [Platform Quirks, Edge Cases & Lessons Learned](#9-platform-quirks-edge-cases--lessons-learned)
10. [Production Incident Runbook (Troubleshooting SOP)](#10-production-incident-runbook)

---

## 1. Executive Summary & Problem Statement

### 1.1 The Business Need
In institutional finance, equity research analysts write detailed company notes before earnings calls, investment committee reviews, and portfolio allocation adjustments. A standard equity note requires:
- Reading hundreds of pages of annual reports (SEC Form 10-K).
- Extracting exact historical financials (Revenue, Operating Income).
- Calculating historical financial ratios (Operating Margins).
- Comparing numbers across fiscal years and peer companies.
- Tracking material shifts in disclosures (Item 1A Risk Factors).

### 1.2 The Risk of Unchecked Generative AI
Standard large language models (LLMs) are probabilistic next-token predictors. In financial contexts, they present severe operational risks:
1. **Arithmetic Hallucination:** LLMs often miscalculate percentages, mix up fiscal year alignments, or confuse thousands and millions.
2. **Citation Drift:** Figures are frequently attributed to the wrong filing year or an unrelated disclosure note.
3. **Regulatory Non-Compliance:** Unsupervised models risk outputting unauthorized investment advice or return guarantees.

### 1.3 How Analyst Desk Solves This
Our team built **Analyst Desk** around three foundational engineering guardrails:
- **Rule 1: The Model Proposes; Deterministic Code Decides.** Arithmetic is never performed inside an LLM prompt. Financial ratios are computed by pure Python code in an isolated sandbox.
- **Rule 2: Every Number Has a Fact ID.** Every figure must trace back to an exact SEC EDGAR XBRL fact. A Compliance Critic agent verifies 100% of figures against ground truth code before drafting completes.
- **Rule 3: Cryptographic Human Sign-Off.** Nothing publishes automatically. The analyst inspects the exact draft, and the system generates a cryptographic SHA-256 hash. The research portal only accepts publication if the signed hash matches the current draft state.

---

## 2. Core Architecture & System Principles

The application is structured into decoupled layers, ensuring clear separation of concerns between data ingestion, agentic orchestration, human control, and infrastructure serving:

```
[ Research UI (Browser) ]
           │
           │ HTTP POST /runs (NDJSON Stream)
           ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Ingress & Serving Layer (FastAPI)                        │
│    - Input Guardrails (L15): Scope & Prompt Injection Check  │
│    - Rate Limiting & Token Budget Hooks (L14)               │
│    - Prometheus Metrics Scraper Endpoint (/metrics)         │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Planning & State Orchestration (LangGraph)               │
│    - Supervisor splits request into structured sub-tasks     │
│    - SQLite Checkpointer maintains persistent state across   │
│      process restarts and network drops                     │
│    - INTERRUPT Gate 1: Human reviews & approves plan         │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Parallel Specialized Agents (LangGraph Fan-Out)          │
│    ├── Filings Researcher: Hybrid BM25 + Vector Search      │
│    ├── Quant Agent: Pulls XBRL Facts -> Python Math Sandbox │
│    └── Risk-Diff Agent: Semantic diff of Item 1A Risks      │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Verification & Reflection Loop                           │
│    ├── Writer: Assembles note using Fact Tags: {{F:id}}     │
│    └── Compliance Critic: Code verification of every digit  │
│        (Rejects and loops back if any digit is untagged)    │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Human Approval Gate & Persistence (L14)                  │
│    - INTERRUPT Gate 2: Analyst inspects draft & hash        │
│    - Stale Approval Guard: Edits immediately invalidate hash│
│    - Research Portal: Writes published note to SQLite DB   │
│    - Memory Store (L9): Updates analyst coverage watchlist  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. End-to-End Execution Flow

When an analyst requests: *"Compare Microsoft and Alphabet operating margins over the last three fiscal years, and tell me what changed in their risk factors."*

1. **Ingress & Guardrails:** The request hits FastAPI. Input guardrails confirm the query falls within financial research scope and sanitizes any untrusted input.
2. **Supervisor Planning:** The planner decomposes the prompt into concrete sub-questions for MSFT and GOOGL. It pauses at an interrupt gate, allowing the analyst to add or remove tickers.
3. **Plan Approval:** The user submits approval via `/resume`. LangGraph resumes execution and fans out tasks in parallel.
4. **Retrieval & Ground Truth Extraction:**
   - The *Filings Researcher* pulls relevant 10-K sections using hybrid search (BM25 keyword matching + vector embeddings).
   - The *Quant Agent* queries SEC EDGAR companyfacts JSON for exact XBRL reported figures (`OperatingIncomeLoss`, `Revenues`).
5. **Sandboxed Math Execution:** The Quant Agent passes the numbers to an isolated Python executor. Deterministic code calculates the margins (e.g., $Operating\ Income \div Revenues = 44.6\%$).
6. **Risk Factor Comparison:** The *Risk-Diff Agent* compares current vs. prior year Item 1A sections to identify added, modified, or removed risk disclosures.
7. **Drafting & Compliance Review:**
   - The *Writer* constructs the note using tags rather than raw digits (`{{F:US-GAAP/OperatingIncomeLoss/...}}`).
   - The *Compliance Critic* validates each tag against the XBRL fact registry. If any figure lacks ground truth or if unauthorized return promises exist, the critic rejects the draft (up to 2 revision loops).
8. **Final Human Gate:** Once the critic approves (`verified share 100%`), the system computes a SHA-256 payload hash and enters an interrupt state.
9. **Publication:** The analyst reviews the table and clicks *Approve this exact note*. The system verifies that the submitted hash matches the active draft and writes the record into the permanent research portal database (`note #1`).

---

## 4. Service Directory & Network Topology

The application is designed for deterministic execution across both developer workstations and containerized server infrastructure.

### 4.1 Multi-Container Docker Topology (`docker-compose.yml`)
To enforce strict security and prevent untrusted code execution from accessing the outside world, services are partitioned into two Docker networks:
- **`edge` (Public / Ingress):** Connected to the host network. Houses the Web UI, FastAPI server, Prometheus scraper, and Grafana.
- **`backend` (Internal / Air-Gapped):** An isolated network with **no default gateway and zero internet access** (`internal: true`). Houses the knowledge base, vector database, and the Python math execution sandbox.

```
                  [ Host Browser / Analyst ]
                              │
                              ▼
        ┌───────────────────────────────────────────┐
        │               edge Network                │
        │   ┌─────────────┐       ┌─────────────┐   │
        │   │ app:8000    │◄─────►│ prom:9090   │   │
        │   │ (FastAPI)   │       │ (Telemetry) │   │
        │   └──────┬──────┘       └──────┬──────┘   │
        └──────────┼─────────────────────┼──────────┘
                   │                     │
  ═════════════════╪═════════════════════╪══════════════════ (Network Isolation Barrier)
                   │                     │
        ┌──────────┼─────────────────────┼──────────┐
        │          ▼                     ▼          │
        │   ┌─────────────┐       ┌─────────────┐   │
        │   │ mcp-kb:9002 │       │ mcp-box:9003│   │
        │   │ (Search/DB) │       │ (Air-Gapped)│   │
        │   └─────────────┘       └─────────────┘   │
        │              backend Network              │
        │            (No External Access)           │
        └───────────────────────────────────────────┘
```

### 4.2 Port Mapping & Component Directory
| Service Name | Port | Description | Network |
| :--- | :--- | :--- | :--- |
| **`app`** | `8000` | FastAPI application, SSE streaming routes, and web portal | `edge`, `backend` |
| **`prometheus`** | `9090` | OpenMetrics scraper polling `/metrics` on a 5s interval | `edge` |
| **`grafana`** | `3000` | Real-time monitoring dashboards for cost, latency, and verified ratio | `edge` |
| **`mcp-edgar`** | `9001` | SEC EDGAR API connector and local filing cache manager | `backend`, `edge` |
| **`mcp-kb`** | `9002` | Hybrid retriever (BM25 + Chroma vector search) | `backend` |
| **`mcp-sandbox`**| `9003` | Python math sandbox with AST validation and resource quotas | `backend` |
| **`mcp-portal`** | `9004` | Research portal repository for published company notes | `backend` |

---

## 5. Environment Setup & Startup Runbooks

### 5.1 Option A: Local Native Execution (Windows / macOS / Linux)
Ideal for local testing, demonstrations, and rapid feedback loops:

1. **Verify Python Installation:** Python 3.10, 3.11, 3.12, or 3.14.
2. **Execute Startup Script:**
   - **Windows:** Double-click `start.bat`
   - **Linux / macOS:** Run `./start.sh`
3. **What the Script Automates:**
   - Creates an isolated `.venv` virtual environment if not already present.
   - Installs minimal runtime dependencies from `requirements-web.txt`.
   - Generates local synthetic financial evaluation caches (`eval_private/golden_dev.json`).
   - Launches Uvicorn on `http://127.0.0.1:8000`.
   - Opens the system's default browser directly to the web portal.

### 5.2 Option B: Full-Stack Containerized Execution (Docker Compose)
Ideal for standard staging and production deployments:
```bash
# 1. Clone repository and navigate to workspace
cd analyst_desk

# 2. Configure environment keys (optional for synthetic mode)
cp .env.example .env

# 3. Build and launch all services in background
docker compose up --build -d

# 4. Confirm container health status
docker compose ps
```

---

## 6. Configuration Dictionary & Secrets Management

Configuration parameters are managed strictly through environment variables and local `.env` files (excluded from version control via `.gitignore`), adhering to 12-Factor Application principles.

| Environment Variable | Default Value | Description |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | *(Empty)* | Unified API key for LLM calls (Writer, Supervisor, and Judge). |
| `SEC_USER_AGENT` | *(Empty)* | Declares User-Agent string for SEC EDGAR live fetching. When left empty, the system automatically runs in **offline synthetic mode** using verified local fixtures. |
| `ALLOW_DEBUG` | `1` | Enables the `/debug/fault` endpoint to simulate critic rejections for demonstration and alert testing. Set to `0` in production. |
| `WRITER_MODEL` | `openai/gpt-4.1-mini` | Model assigned to research note drafting. |
| `SUPERVISOR_MODEL`| `openai/gpt-4.1-mini` | Model assigned to query decomposition and planning. |
| `JUDGE_MODEL` | `google/gemini-3.1-flash-lite` | Evaluation judge model (selected from a different model family for independent assessment). |
| `GATE_THRESHOLD` | `0.90` | Accuracy floor for CI/CD evaluation gate before merging code. |
| `CORS_ORIGIN_REGEX`| Localhost regex | Permitted cross-origin hosts for API consumers. |

---

## 7. API Contract & Streaming Protocols

### 7.1 Server-Sent Events (SSE) / NDJSON Stream
- **Endpoint:** `POST /runs`
- **Why Streaming?** Multi-agent coordination, document retrieval, and compliance verification require 15 to 30 seconds. A standard blocking REST API risks client-side timeouts (HTTP 504) and poor user experience. Streaming delivers updates as each agent completes its step.
- **Sample Request:**
  ```json
  {
    "request": "Compare Microsoft and Alphabet operating margins over the last three fiscal years.",
    "user": "analyst_1",
    "remember": false
  }
  ```
- **Stream Output Format:** Each event is streamed as a newline-delimited JSON (NDJSON) payload:
  ```json
  {"event": "start", "run_id": "run-9e6fa1ad3a"}
  {"event": "node", "node": "plan", "update": {"plan": {"tickers": ["MSFT", "GOOGL"]}}}
  {"event": "interrupt", "payload": {"type": "plan_approval"}}
  ```

### 7.2 Human Interrupt Resume
- **Endpoint:** `POST /runs/{run_id}/resume`
- **Request Payload:**
  ```json
  {
    "action": "approve",
    "hash": "a4c67159d073b547"
  }
  ```
- **Security Check:** If the submitted `hash` does not match the active draft's SHA-256 digest, the server returns an HTTP 409 conflict, rejecting the approval and preserving system state.

### 7.3 Health Check & Readiness Probes
- **Endpoint:** `GET /healthz`
- **Purpose:** Used by Docker native health checks, Kubernetes liveness probes, and load balancers.
- **Sample Response:**
  ```json
  {
    "ok": true,
    "mode": "offline-synthetic",
    "prompt_version": "v2"
  }
  ```

---

## 8. Observability, Telemetry & SLA Thresholds

Operational metrics are exposed via standard OpenMetrics format on `GET /metrics` and polled by Prometheus every 5 seconds.

```
                    ┌───────────────────────────────┐
                    │  FastAPI Application (:8000)  │
                    │      Exposes /metrics         │
                    └──────────────┬────────────────┘
                                   │
                     Scrapes every 5 seconds
                                   │
                                   ▼
                    ┌───────────────────────────────┐
                    │      Prometheus (:9090)       │
                    │   Evaluates Alert Rules       │
                    └──────────────┬────────────────┘
                                   │
                    ┌──────────────┴────────────────┐
                    │                               │
                    ▼                               ▼
       ┌────────────────────────┐      ┌────────────────────────┐
       │ Grafana Dashboard:3000 │      │  P1 Pager Alert        │
       │ (Verified %, Latency)  │      │ (Verified Share < 98%) │
       └────────────────────────┘      └────────────────────────┘
```

### 8.1 Key Golden Signals Tracked
1. **`analyst_verified_share` (Gauge):** Percentage of numbers in the draft verified by ground truth code.
2. **`analyst_critic_rejections_total` (Counter):** Number of drafts sent back for revision due to ungrounded claims or untagged numbers.
3. **`analyst_edgar_cache_requests_total` (Counter, labeled `result="hit"|"miss"`):** Cache efficiency tracking.
4. **`analyst_llm_cost_usd_total` (Counter):** Cumulative API token expenditure in USD.

### 8.2 Production Alert Rules (`docker/alerts.yml`)
- **Alert 1: `VerifiedNumberShareLow`**
  - **Condition:** `analyst_verified_share < 0.98` sustained for 30 seconds.
  - **Severity:** P1 / Page.
  - **Meaning:** The model is emitting unverified numbers, breaching our financial compliance SLA. Automated publishing is halted immediately.
- **Alert 2: `CriticRejectionsHigh`**
  - **Condition:** `increase(analyst_critic_rejections_total[5m]) > 5`.
  - **Severity:** Warning.
  - **Meaning:** Writers are repeatedly failing critic checks, indicating upstream prompt drift or model degradation.

---

## 9. Platform Quirks, Edge Cases & Lessons Learned

During cross-platform testing and deployment hardening, several critical environment quirks were diagnosed and remediated:

### 9.1 Cross-Platform Path Handling (`/tmp` vs. Windows)
- **Problem:** The calculation sandbox was initially configured with `cwd="/tmp"`, assuming a Unix environment. On native Windows hosts, this resulted in `NotADirectoryError: [WinError 267] The directory name is invalid`.
- **Remediation:** Refactored `sandbox.py` to leverage `tempfile.gettempdir()`, allowing the math sandbox to execute safely across Windows workstations, macOS, and Linux containers.

### 9.2 Silent Background Installation
- **Problem:** The original bootstrap script executed `pip install -q`, which runs silently with zero console output. Because package downloads take 1 to 2 minutes on initial setup, users assumed the terminal was frozen.
- **Remediation:** Removed the quiet flag and implemented explicit status banners in `start.bat` (`[*] Installing web packages...`, `[*] Starting Uvicorn...`).

### 9.3 Cryptographic Hash Invalidation (Feature, Not a Bug)
- **Behavior:** Clicking *Send stale approval (demo)* results in a red warning and refuses to publish.
- **Design Intent:** This demonstrates compliance control L14. Approval is cryptographically bound to the exact payload string. If an analyst modifies a single character or submits an outdated token, the server rejects the signature to prevent tampering.

---

## 10. Production Incident Runbook (Troubleshooting SOP)

### Incident 1: Web Interface Unreachable (`ERR_CONNECTION_REFUSED`)
1. **Verify Process Status:** Check if Uvicorn is active on port 8000:
   ```powershell
   netstat -ano | findstr :8000
   ```
2. **Execute Diagnostic Harness:** In the project root, run:
   ```bash
   python check.py
   ```
   Confirm that all 5 checks return `[OK]`.
3. **Inspect Dependency Integrity:** If an import error is logged, re-synchronize the virtual environment:
   ```bash
   .venv\Scripts\python.exe -m pip install -r requirements-web.txt
   ```

### Incident 2: High Rate of Critic Rejections
1. Check if the synthetic writer fault was inadvertently left active:
   ```bash
   curl -X POST http://localhost:8000/debug/fault?on=false
   ```
2. Inspect `data/trace.jsonl` to observe which specific agent node generated untagged numbers.
3. Validate that SEC EDGAR cache files in `data/fixtures/` have not been corrupted or emptied.

### Incident 3: Thread State Lock or Stale Checkpoints
1. Stop the active server process (`Ctrl + C`).
2. Clean up local SQLite checkpoint files:
   ```powershell
   Remove-Item "data\*.db" -Force
   ```
3. Relaunch `start.bat`.

---

## 6. CI/CD Pipelines, Quality Gates & Automated Deployment

To ensure production grade verifiability and prevent model drift, Analyst Desk enforces automated CI/CD pipelines via GitHub Actions:

### 6.1 Automated Test Execution & Quality Gates (`.github/workflows/ci.yml`)
* **Trigger:** Every commit push and pull request to `main`/`master`.
* **Stage 1: Automated Quality Gate:** Runs `flake8` syntax and complexity checks, followed by `bandit` AST security scanning.
* **Stage 2: Automated Test Execution:** Executes `pytest tests/ -v` covering input guardrails, SEC XBRL ingestion, broker-dealer advice filters, Python sandbox margin math, and `/metrics` telemetry endpoints.

### 6.2 Automated Deployment Pipeline (`.github/workflows/cd.yml`)
* **Trigger:** Automatic upon successful test completion on `main`/`master`.
* **Actions:** Builds the containerized Docker image (`equity-analyst-desk:latest`), runs live container healthcheck verification against `http://localhost:8000/`, and verifies staging deployment readiness.

---

**Handbook Maintenance:**  
Collaboratively authored by the Engineering Team  
Approved for Operations & Staging Deployment (L16 Compliance)
