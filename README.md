# Analyst Desk — Verifiable Equity Research Platform
**IIT Bombay Agentic AI Capstone Project**

Analyst Desk bridges LLM reasoning with deterministic SEC EDGAR XBRL ingestion, Python sandbox arithmetic verification, and multi-agent LangGraph orchestration with Human-in-the-Loop approval gates.

---

## 🚀 Quick Start (Under 1 Minute)

### Option 1: 1-Click Launch (Windows)
Double-click `start.bat`.  
It automatically detects Python, configures `.venv`, installs dependencies if needed, starts the FastAPI server, and opens `http://localhost:8000`.

### Option 2: 1-Click Launch (Mac / Linux)
```bash
chmod +x start.sh
./start.sh
```

### Option 3: Manual Terminal Setup
```bash
python -m venv .venv

# On Windows:
.\.venv\Scripts\activate
# On Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```
Open **`http://localhost:8000`** in your browser.

### Option 4: Docker Compose (App + Prometheus + Grafana Stack)
```bash
docker compose up --build -d
```
Access all live services:
- **Application:** `http://localhost:8000`
- **Prometheus Targets:** `http://localhost:9090/targets`
- **Grafana Live Dashboard:** `http://localhost:3000` (Login: `admin` / `admin`)
- **Raw Prometheus Metrics:** `http://localhost:8000/metrics`

---

## 📈 Real-Time Monitoring & Observability Stack

The platform includes an enterprise **Prometheus & Grafana** observability stack:
- **Throughput (`app_requests_total`):** Tracks requests per second across all endpoints with HTTP status codes.
- **Latency Histogram (`app_processing_seconds`):** Monitors task durations for financial report generation, XBRL evaluations, and Red-Team audits.
- **Active Workload (`app_active_jobs`):** Real-time gauge of concurrent LangGraph research jobs executing in the Python sandbox.

To view:
1. Run `docker compose up --build -d`
2. Open `http://localhost:3000` -> Dashboards -> **Application Live Metrics Dashboard**.

---

## 📊 Live Viva Walkthrough Guide (5 Tabs)

1. **Tab 1 — Research Desk (Live Multi-Agent Workflow):**
   - Click any preset chip (e.g. `V vs MA`, `MSFT vs GOOGL`, `WMT vs AMZN`).
   - Click **Draft Research Plan →** to see the planner decompose the request.
   - Click **Approve Plan & Execute Parallel Workers** to trigger concurrent company research and sandbox calculations.
   - Click any inline **`FACT:TAG`** or **`PASSAGE:TAG`** badge in the draft table to inspect the underlying SEC accession metadata or 10-K excerpt.
   - Click **Sign & Publish to Research Portal** with a SHA-256 cryptographic attestation.

2. **Tab 2 — Research Portal:**
   - View the immutable ledger of published research notes and download JSON/Markdown reports.

3. **Tab 3 — Eval Suite (Ground-Truth & Red-Team):**
   - **XBRL Ground-Truth Benchmark:** Run the 12-case test suite (`100% pass rate`).
   - **Multi-Agent vs Single-Agent Benchmark:** Compares verifiable Fact-ID grounding against monolithic LLM hallucinations.
   - **Red-Team Security Audit:** Tests instruction overrides, unverified claims, and FINRA-prohibited rating language (`100% defense rate`).

4. **Tab 4 — Coverage Memory:**
   - Query longitudinal historical coverage across published research notes.

5. **Tab 0 — Overview & Architecture:**
   - Complete system architectural breakdown and verifiability criteria table.

---

## 🏛️ System Architecture
- **Orchestration:** LangGraph `StateGraph` with parallel fan-out and dual HITL `interrupt()` gates.
- **Arithmetic Verification:** Isolated Python subprocess sandbox (`-I` mode) for IEEE-compliant margin and basis point calculations.
- **Data Coverage:** 14 companies across Tech and Banking/Payments with 3–4 consecutive years of audited US-GAAP XBRL data.
