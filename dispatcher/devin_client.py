"""Thin client for the Devin API (v3). Supports a simulated mode for dry runs."""

import random
import time
import uuid

import requests

STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "pr_url": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "files_changed": {"type": "integer"},
        "checks_passed": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": ["summary", "checks_passed"],
}


class DevinClient:
    def __init__(self, base_url: str, api_key: str, org_id: str):
        self._base = base_url.rstrip("/")
        self._org = org_id
        self._http = requests.Session()
        self._http.headers.update({"Authorization": f"Bearer {api_key}"})

    def _url(self, path: str) -> str:
        return f"{self._base}/v3/organizations/{self._org}{path}"

    def create_session(
        self,
        prompt: str,
        repos: list[str],
        title: str,
        tags: list[str],
        max_acu_limit: int | None = None,
    ) -> dict:
        body = {
            "prompt": prompt,
            "repos": repos,
            "title": title,
            "tags": tags,
            "structured_output_schema": STRUCTURED_OUTPUT_SCHEMA,
            "structured_output_required": False,
            "resumable": False,
        }
        if max_acu_limit:
            body["max_acu_limit"] = max_acu_limit
        r = self._http.post(self._url("/sessions"), json=body, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_session(self, session_id: str) -> dict:
        r = self._http.get(self._url(f"/sessions/{session_id}"), timeout=30)
        r.raise_for_status()
        return r.json()

    def send_message(self, session_id: str, message: str) -> dict:
        r = self._http.post(
            self._url(f"/sessions/{session_id}/messages"),
            json={"message": message},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()


class SimulatedDevinClient:
    """Stands in for the Devin API so the full pipeline can be demoed without
    consuming ACUs. Sessions transition to 'exit'/'finished' after ~90s and
    report a fake PR."""

    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def create_session(self, prompt, repos, title, tags, max_acu_limit=None):
        sid = f"devin-sim-{uuid.uuid4().hex[:12]}"
        self._sessions[sid] = {
            "created": time.time(),
            "session_id": sid,
            "title": title,
        }
        return {
            "session_id": sid,
            "status": "new",
            "url": f"https://app.devin.ai/sessions/{sid}",
        }

    def get_session(self, session_id: str) -> dict:
        s = self._sessions[session_id]
        age = time.time() - s["created"]
        if age < 30:
            return {"session_id": session_id, "status": "running", "status_detail": "working"}
        if age < 90:
            return {
                "session_id": session_id,
                "status": "running",
                "status_detail": "working",
                "acus_consumed": round(age / 30, 1),
            }
        return {
            "session_id": session_id,
            "status": "exit",
            "status_detail": "finished",
            "acus_consumed": 3.0,
            "pull_requests": [
                {
                    "pr_url": "https://github.com/example/pull/0",
                    "pr_state": "open",
                }
            ],
            "structured_output": {
                "pr_url": "https://github.com/example/pull/0",
                "summary": f"[SIMULATED] Completed: {s['title']}",
                "files_changed": random.randint(2, 12),
                "checks_passed": True,
                "notes": "Simulated session — set SIMULATE=false with DEVIN_API_KEY to run for real.",
            },
        }

    def send_message(self, session_id: str, message: str) -> dict:
        return {"ok": True}
