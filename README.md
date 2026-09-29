# devin-superset-automation

Event-driven remediation pipeline for a fork of [Apache Superset](https://github.com/apache/superset), powered by the [Devin API](https://docs.devin.ai/api-reference/overview).

A scanner finds security vulnerabilities and code-quality/type-safety debt in the target repo and files GitHub issues. A dispatcher watches for issues labeled `devin-fix` and spins up Devin sessions — in parallel — that open pull requests back on the repo. A dashboard reports run status, success rate, cycle time, and ACU consumption.

## Architecture

```
┌────────────────────────────┐     ┌─────────────────────────────┐
│ GitHub Actions (scanner)   │     │ Dispatcher (this repo)       │
│  cron → scanner/scan.py    │     │  FastAPI + SQLite            │
│  → upserts issues labeled  │────▶│  • POST /webhooks/github     │
│    `devin-fix`             │     │  • label watcher (polling)   │
└────────────────────────────┘     │  • POST /dispatch/{n}        │
            │                      │       │                      │
            │                      │       ▼                      │
            │                      │  Devin API v3                │
            │                      │  POST /v3/organizations/     │
            │                      │    {org}/sessions            │
            │                      │       │                      │
            │                      │       ▼                      │
            ▼                      │  Devin session → opens PR    │
   GitHub issues on          ◀─────│  poll status → comment on    │
   HirenRMistry/superset           │  issue, record PR + ACUs     │
                                   └──────────┬──────────────────┘
                                              ▼
                                   Dashboard `/` + `/api/metrics`
```

**Why the Devin API and not a linter/codemod:** the findings are real code changes — inferring precise TypeScript types, mapping `antd` components to their `@superset-ui/core` wrapper equivalents, and making `react-hooks` dependency arrays correct without breaking behavior. The scanner can locate the debt; only an agent that reads the codebase, runs `tsc`/`eslint`/`jest`, and iterates can fix it.

## Components

| Path | What it does |
|---|---|
| `scanner/scan.py` | Scans a Superset checkout for `: any` hotspots, direct `antd` imports, `eslint-disable` suppressions, `npm audit` vulns, and `pip-audit` CVEs against `requirements/base.txt`. Emits `findings.json`; with `--create-issues` upserts labeled GitHub issues. Stdlib + optional scanner binaries. |
| `dispatcher/` | FastAPI service. Receives GitHub `issues` webhooks (HMAC-verified) **or** polls the repo for `devin-fix` issues. Creates Devin sessions with a structured-output schema, polls them, records PRs/ACUs in SQLite, comments progress back on each issue. Optional `AUTO_NUDGE` replies to sessions stuck in `waiting_for_approval` so the loop stays autonomous. |
| `scripts/demo.sh` | One-command demo: scan the fork → build & start the dispatcher → watcher auto-dispatches → dashboard live at `:8000`. |
| `.github/workflows/scan.yml` | Scheduled scan (every 6h) → creates new issues → dispatcher picks them up. `workflow_dispatch` for manual runs. |
| `static/dashboard.html` | Auto-refreshing ops dashboard: active/completed runs, PRs opened, success rate, ACU spend, per-run event log. |

## Devin session contract

Each dispatched issue becomes a session with:

- `repos: ["HirenRMistry/superset"]`
- prompt = issue title + body + requirements (branch `devin/issue-N`, run the issue's verification commands, open a PR with `Closes #N`)
- `tags`: `superset-automation`, `issue-N`
- a **structured output schema** (`pr_url`, `summary`, `files_changed`, `checks_passed`, `notes`) so results are machine-readable for reporting
- optional `max_acu_limit` spend cap

Session states (`new → claimed → running → exit`) are polled; `pull_requests[]` and `structured_output` drive the dashboard and the issue comment. When `AUTO_NUDGE=true`, sessions reporting `waiting_for_approval`/`waiting_for_user` get an in-scope approval message so unattended runs complete.

## Quick start (dry-run demo — no Devin key needed)

```bash
./scripts/demo.sh          # scans ../superset, starts the dispatcher in SIMULATE mode
open http://localhost:8000 # watch the dashboard
```

Or manually:

```bash
cp .env.example .env
# edit .env: set GH_TOKEN and TARGET_REPO, set SIMULATE=true
docker compose up --build
curl -X POST http://localhost:8000/dispatch/1     # dispatch issue #1
```

Simulated sessions finish in ~90s and record a fake PR so you can see the whole loop: issue → session → PR → metrics.

## Real run

1. Create a Devin **service user** API key (`cog_…`) and note your `org-…` id — see the [Teams quickstart](https://docs.devin.ai/api-reference/getting-started/teams-quickstart).
2. Set `DEVIN_API_KEY`, `DEVIN_ORG_ID`, `SIMULATE=false` in `.env`.
3. Give Devin's GitHub integration access to the target repo (or provide `session_secrets` for git auth).
4. `docker compose up --build`, then label any issue `devin-fix` — the watcher picks it up within `POLL_INTERVAL_S` seconds. Or expose the service and point a GitHub webhook at `POST /webhooks/github`.
5. Optional: `AUTO_NUDGE=true` auto-approves sessions that pause in `waiting_for_approval`.

**Trigger paths** (all three work simultaneously): the scheduled scanner files `devin-fix` issues → watcher auto-dispatches (fully autonomous, no human step — the label is routing, not a manual trigger); a real GitHub webhook for instant dispatch; and `POST /dispatch/{n}` for manual runs.

## Scanner

```bash
python scanner/scan.py --repo ../superset            # print findings
python scanner/scan.py --repo ../superset --create-issues   # upsert issues (needs GH_TOKEN)
```

The GH Action runs this on a schedule; new findings become `devin-fix` issues, which the dispatcher turns into Devin sessions. That's the full closed loop: **scan → issue → session → PR → report**.

## Observability

- `GET /api/metrics` — totals, active/completed/failed, PRs opened, success rate, total ACUs, avg time-to-done
- `GET /api/runs` — every run with status (`dispatched`, `running:working`, `pr_opened`, `failed`, …)
- `GET /api/runs/{id}/events` — per-run event log
- Issue comments mirror the lifecycle so humans see progress where they already work

## Extending this in a real engagement

- Swap the scanner for real signals: Sentry rollups, Dependabot/npm-audit findings, Devin code-scan results, Linear/Jira ticket creation
- Per-repo Devin **playbooks** + **knowledge** entries instead of inline prompt templates
- Approval gates: only auto-dispatch issues under a size threshold; require a human label for the rest
- Feedback loop: failed session → auto-comment with structured `notes` → nudge session with a follow-up message
