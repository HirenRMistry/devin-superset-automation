#!/usr/bin/env bash
# End-to-end demo: scan the fork, dispatch the labeled issues, watch the dashboard.
#
#   ./scripts/demo.sh                 # simulate mode (no Devin key needed)
#   SIMULATE=false ./scripts/demo.sh  # real Devin sessions (needs .env filled in)
set -euo pipefail
cd "$(dirname "$0")/.."

SIMULATE="${SIMULATE:-true}"
REPO_DIR="${REPO_DIR:-../superset}"

echo "==> 1/4  Scanning $REPO_DIR for findings"
python3 scanner/scan.py --repo "$REPO_DIR" --out findings.json | tail -8

echo "==> 2/4  Starting dispatcher (SIMULATE=$SIMULATE) on :8000"
if docker info >/dev/null 2>&1; then
  docker build -q -t devin-automation .
  docker rm -f devin-auto-demo >/dev/null 2>&1 || true
  docker run -d --name devin-auto-demo -p 8000:8000 \
    -e SIMULATE="$SIMULATE" \
    -e TARGET_REPO="${TARGET_REPO:-HirenRMistry/superset}" \
    -e GH_TOKEN="${GH_TOKEN:-}" \
    -e DEVIN_API_KEY="${DEVIN_API_KEY:-}" \
    -e DEVIN_ORG_ID="${DEVIN_ORG_ID:-}" \
    -e POLL_INTERVAL_S=15 \
    devin-automation
else
  echo "    docker not running — falling back to local uvicorn"
  [ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
  SIMULATE="$SIMULATE" TARGET_REPO="${TARGET_REPO:-HirenRMistry/superset}" \
    POLL_INTERVAL_S=15 .venv/bin/uvicorn dispatcher.main:app --port 8000 &
  echo $! > /tmp/devin-auto-demo.pid
fi

sleep 4
echo "==> 3/4  Dispatcher is up — label watcher auto-dispatches all 'devin-fix' issues"
curl -s http://localhost:8000/healthz; echo

echo "==> 4/4  Dashboard: http://localhost:8000  (auto-refreshes; watch runs → sessions → PRs)"
echo "    Metrics snapshot:"
sleep 2
curl -s http://localhost:8000/api/metrics | python3 -m json.tool
echo
echo "Watch live: open http://localhost:8000"
echo "Stop: docker rm -f devin-auto-demo  (or kill \$(cat /tmp/devin-auto-demo.pid))"
