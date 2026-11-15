#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "======================================================================"
echo "   Analyst Desk: Verifiable Equity Research Platform (IIT Bombay)    "
echo "   14 Companies | 3 Years Verified XBRL | Python Sandbox | Evals     "
echo "======================================================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found. Please install Python 3.11+."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

echo "[*] Starting Uvicorn server on port 8000..."
echo "[*] App URL:            http://localhost:8000"
echo "[*] Prometheus Metrics: http://localhost:8000/metrics"
echo "[*] Grafana Dashboard:  http://localhost:3000 (run: docker compose up -d)"

# Launch browser in background after 2-second startup buffer
(
    sleep 2
    if which xdg-open > /dev/null 2>&1; then
        xdg-open http://localhost:8000 >/dev/null 2>&1
    elif which open > /dev/null 2>&1; then
        open http://localhost:8000 >/dev/null 2>&1
    fi
) &

python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
