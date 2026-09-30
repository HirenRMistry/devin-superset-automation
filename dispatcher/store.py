"""SQLite persistence for dispatch runs and their event log."""

import json
import sqlite3
import time
from contextlib import contextmanager


class Store:
    def __init__(self, path: str):
        self._path = path
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    issue_number INTEGER NOT NULL,
                    issue_title TEXT NOT NULL,
                    issue_url TEXT NOT NULL,
                    devin_session_id TEXT,
                    devin_session_url TEXT,
                    status TEXT NOT NULL DEFAULT 'dispatched',
                    pr_url TEXT,
                    acus_consumed REAL,
                    structured_output TEXT,
                    devin_messages INTEGER,
                    session_size TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    ts REAL NOT NULL,
                    message TEXT NOT NULL
                );
                """
            )
            cols = {r[1] for r in c.execute("PRAGMA table_info(runs)")}
            for col, typ in (("devin_messages", "INTEGER"), ("session_size", "TEXT")):
                if col not in cols:
                    c.execute(f"ALTER TABLE runs ADD COLUMN {col} {typ}")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def has_active_run(self, issue_number: int) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM runs WHERE issue_number=? AND status NOT IN "
                "('pr_opened','finished','failed','error','merged','suspended') LIMIT 1",
                (issue_number,),
            ).fetchone()
            return row is not None

    def has_nonfailed_run(self, issue_number: int) -> bool:
        """True if the issue already has a run that isn't a failure —
        prevents re-dispatching issues whose remediation already completed."""
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM runs WHERE issue_number=? AND status NOT IN "
                "('failed','error','suspended') LIMIT 1",
                (issue_number,),
            ).fetchone()
            return row is not None

    def create_run(self, issue_number: int, issue_title: str, issue_url: str) -> int:
        now = time.time()
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO runs (issue_number, issue_title, issue_url, created_at, updated_at) "
                "VALUES (?,?,?,?,?)",
                (issue_number, issue_title, issue_url, now, now),
            )
            return cur.lastrowid

    def attach_session(self, run_id: int, session_id: str, session_url: str):
        with self._conn() as c:
            c.execute(
                "UPDATE runs SET devin_session_id=?, devin_session_url=?, status='dispatched', "
                "updated_at=? WHERE id=?",
                (session_id, session_url, time.time(), run_id),
            )

    def update_run(self, run_id: int, **fields):
        if not fields:
            return
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._conn() as c:
            c.execute(f"UPDATE runs SET {cols} WHERE id=?", (*fields.values(), run_id))

    def event(self, run_id: int, message: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO events (run_id, ts, message) VALUES (?,?,?)",
                (run_id, time.time(), message),
            )

    def active_runs(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM runs WHERE status NOT IN "
                "('pr_opened','finished','failed','error','merged','suspended') AND devin_session_id IS NOT NULL"
            ).fetchall()
            return [dict(r) for r in rows]

    def pr_open_runs(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM runs WHERE status='pr_opened' AND devin_session_id IS NOT NULL"
            ).fetchall()
            return [dict(r) for r in rows]

    def all_runs(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def run_events(self, run_id: int) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM events WHERE run_id=? ORDER BY ts", (run_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def metrics(self) -> dict:
        with self._conn() as c:
            rows = c.execute(
                "SELECT status, COUNT(*) n, COALESCE(SUM(acus_consumed),0) acus "
                "FROM runs GROUP BY status"
            ).fetchall()
            total_acus = c.execute(
                "SELECT COALESCE(SUM(acus_consumed),0) FROM runs"
            ).fetchone()[0]
            total_msgs = c.execute(
                "SELECT COALESCE(SUM(devin_messages),0) FROM runs"
            ).fetchone()[0]
            prs = c.execute(
                "SELECT COUNT(*) FROM runs WHERE pr_url IS NOT NULL"
            ).fetchone()[0]
            merged = c.execute(
                "SELECT COUNT(*) FROM runs WHERE status='merged'"
            ).fetchone()[0]
            done = sum(r["n"] for r in rows if r["status"] in ("pr_opened", "finished", "merged"))
            failed = sum(r["n"] for r in rows if r["status"] in ("failed", "error", "suspended"))
            active = sum(r["n"] for r in rows if r["status"] not in ("pr_opened", "finished", "failed", "error", "merged", "suspended"))
            avg_secs = c.execute(
                "SELECT AVG(updated_at - created_at) FROM runs "
                "WHERE status IN ('pr_opened','finished')"
            ).fetchone()[0]
            return {
                "total_runs": sum(r["n"] for r in rows),
                "active": active,
                "completed": done,
                "failed": failed,
                "prs_opened": prs,
                "prs_merged": merged,
                "total_acus": round(total_acus, 2),
                "total_devin_messages": total_msgs,
                "success_rate": round(done / (done + failed), 3) if (done + failed) else None,
                "avg_time_to_done_s": round(avg_secs, 1) if avg_secs else None,
                "by_status": {r["status"]: r["n"] for r in rows},
            }


def as_json(v) -> str | None:
    return json.dumps(v) if v is not None else None
