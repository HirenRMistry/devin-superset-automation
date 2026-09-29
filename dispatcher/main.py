"""Devin dispatcher: event-driven remediation service.

Triggers:
  - GitHub `issues` webhook (opened/labeled with the dispatch label)
  - Poll-based watcher for the dispatch label (no public webhook needed)
  - Manual `POST /dispatch/{issue_number}`

For each triggered issue it creates a Devin session, polls it until done,
then records the resulting PR and reports back to the GitHub issue.
"""

import asyncio
import hashlib
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from .config import load
from .devin_client import DevinClient, SimulatedDevinClient
from .github_client import GitHubClient
from .prompts import build_prompt
from .store import Store, as_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dispatcher")

cfg = load()
store = Store(cfg.db_path)
gh = GitHubClient(cfg.github_token, cfg.target_repo)
devin = SimulatedDevinClient() if cfg.simulate else DevinClient(
    cfg.devin_base_url, cfg.devin_api_key, cfg.devin_org_id
)

TERMINAL_SESSION_STATES = {"exit", "error"}


def dispatch_issue(issue: dict, force: bool = False) -> dict:
    """Create a run + Devin session for a GitHub issue. Idempotent per issue:
    skips closed issues and issues that already have a non-failed run, unless
    force=True (manual retry)."""
    number = issue["number"]
    if issue.get("state") == "closed":
        return {"skipped": True, "issue": number, "reason": "closed"}
    if not force and store.has_nonfailed_run(number):
        log.info("issue #%s already dispatched — skipping", number)
        return {"skipped": True, "issue": number}

    run_id = store.create_run(number, issue["title"], issue["html_url"])
    store.event(run_id, f"dispatched from issue #{number}")

    prompt = build_prompt(cfg.target_repo, issue)
    try:
        session = devin.create_session(
            prompt=prompt,
            repos=[cfg.target_repo],
            title=f"Issue #{number}: {issue['title']}",
            tags=["superset-automation", f"issue-{number}"],
            max_acu_limit=cfg.max_acu_limit,
        )
    except Exception as e:
        store.update_run(run_id, status="error", error=str(e))
        store.event(run_id, f"devin session creation failed: {e}")
        raise

    session_id = session.get("session_id") or session.get("devin_id")
    session_url = session.get("url") or f"https://app.devin.ai/sessions/{session_id}"
    store.attach_session(run_id, session_id, session_url)
    store.event(run_id, f"devin session created: {session_url}")

    try:
        gh.comment(
            number,
            f"Devin session started: {session_url}\n\n"
            f"_(dispatched by devin-superset-automation run #{run_id})_",
        )
    except Exception as e:
        log.warning("github comment failed for #%s: %s", number, e)

    return {"run_id": run_id, "session_id": session_id, "session_url": session_url}


def poll_once() -> list[dict]:
    """Check active runs' Devin sessions; finalize those that finished."""
    updates = []
    for run in store.active_runs():
        sid = run["devin_session_id"]
        try:
            sess = devin.get_session(sid)
        except Exception as e:
            store.event(run["id"], f"poll error: {e}")
            continue

        status = sess.get("status")
        detail = sess.get("status_detail")
        if sess.get("acus_consumed") is not None:
            store.update_run(run["id"], acus_consumed=sess["acus_consumed"])

        if status == "running":
            if run["status"] != f"running:{detail}":
                store.update_run(run["id"], status=f"running:{detail}")
                store.event(run["id"], f"session running ({detail})")
            if cfg.auto_nudge and detail in {"waiting_for_approval", "waiting_for_user"}:
                try:
                    devin.send_message(
                        sid,
                        f"Approved — proceed. The change is in scope for issue "
                        f"#{run['issue_number']} on {cfg.target_repo}; open the PR when done.",
                    )
                    store.event(run["id"], f"auto-nudged session ({detail})")
                except Exception as e:
                    store.event(run["id"], f"auto-nudge failed: {e}")
            continue

        if status not in TERMINAL_SESSION_STATES:
            continue

        prs = sess.get("pull_requests") or []
        so = sess.get("structured_output") or {}
        pr_url = (prs[0]["pr_url"] if prs else None) or so.get("pr_url")

        if status == "error" or detail in {"error", "usage_limit_exceeded", "out_of_credits"}:
            store.update_run(run["id"], status="failed", error=detail,
                             structured_output=as_json(so) or None)
            store.event(run["id"], f"session failed: {detail}")
            try:
                gh.comment(run["issue_number"], f"Devin session ended in `{detail}` — needs a human look.")
            except Exception:
                pass
        else:
            new_status = "pr_opened" if pr_url else "finished"
            store.update_run(run["id"], status=new_status, pr_url=pr_url,
                             structured_output=as_json(so) or None)
            store.event(run["id"], f"session finished; pr={pr_url}")
            try:
                gh.comment(
                    run["issue_number"],
                    f"Devin session complete.\n\n"
                    f"- PR: {pr_url or 'none opened'}\n"
                    f"- Summary: {so.get('summary', 'n/a')}\n"
                    f"- Checks passed: {so.get('checks_passed')}\n"
                    f"- ACUs consumed: {sess.get('acus_consumed')}",
                )
            except Exception:
                pass
        updates.append({"run_id": run["id"], "status": status, "pr_url": pr_url})
    return updates


async def watcher_loop():
    """Poll-based trigger: pick up newly labeled issues + advance active runs."""
    while True:
        try:
            poll_once()
        except Exception:
            log.exception("poll_once failed")
        try:
            for issue in gh.list_labeled_issues(cfg.dispatch_label):
                dispatch_issue(issue)
        except Exception:
            log.exception("label watcher failed")
        await asyncio.sleep(cfg.poll_interval_s)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(watcher_loop())
    yield
    task.cancel()


app = FastAPI(title="devin-superset-automation", lifespan=lifespan)


def _verify_signature(raw: bytes, header: str | None):
    if not cfg.webhook_secret:
        return
    if not header or not header.startswith("sha256="):
        raise HTTPException(401, "missing signature")
    digest = hmac.new(cfg.webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(f"sha256={digest}", header):
        raise HTTPException(401, "bad signature")


@app.post("/webhooks/github")
async def github_webhook(request: Request):
    raw = await request.body()
    _verify_signature(raw, request.headers.get("X-Hub-Signature-256"))
    event = request.headers.get("X-GitHub-Event")
    payload = await request.json()
    if event != "issues" or payload.get("action") not in {"opened", "labeled", "reopened"}:
        return {"ignored": True}
    issue = payload["issue"]
    labels = {l["name"] for l in issue.get("labels", [])}
    if cfg.dispatch_label not in labels:
        return {"ignored": True, "reason": "no dispatch label"}
    return dispatch_issue(issue)


@app.post("/dispatch/{issue_number}")
def manual_dispatch(issue_number: int, force: bool = False):
    issue = gh.get_issue(issue_number)
    return dispatch_issue(issue, force=force)


@app.post("/poll")
def manual_poll():
    return {"updates": poll_once()}


@app.get("/api/runs")
def api_runs():
    return store.all_runs()


@app.get("/api/runs/{run_id}/events")
def api_run_events(run_id: int):
    return store.run_events(run_id)


@app.get("/api/metrics")
def api_metrics():
    return store.metrics()


@app.get("/healthz")
def healthz():
    return {"ok": True, "simulate": cfg.simulate, "repo": cfg.target_repo}


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse("static/dashboard.html")
