# Demo script — 5-minute Loom

Screen cues in **[brackets]**, spoken lines in blockquotes. Roughly 5 minutes
at demo pace.

## 0:00–0:30 — The problem

**[Screen: GitHub issues tab on the Superset fork]**

> Every repo accumulates security debt and modernization debt — CVEs in
> pinned deps, `any` types, deprecated patterns. Fixing it is repetitive but
> not mechanical: it needs judgment about breaking changes, tests, and
> codebase conventions. I built an event-driven pipeline that detects this
> debt, files issues, and dispatches Devin sessions to remediate it
> autonomously — end to end, from scan to merged PR.

## 0:30–1:15 — Architecture

**[Screen: README architecture diagram, scroll slowly]**

> Three components. A **scanner** runs on a cron in GitHub Actions — it
> audits Python deps with pip-audit, npm deps with `npm audit`, and scans
> TypeScript for `any` hotspots, direct antd imports, and eslint
> suppressions. Findings become **GitHub issues** labeled `devin-fix` —
> deduplicated by title so re-scans don't spam.
>
> A **dispatcher** — a FastAPI service, Dockerized — watches for labeled
> issues via webhook or polling, creates a **Devin session** per issue with
> a structured-output schema, polls it, and comments progress back on the
> issue. Sessions run in parallel. The **dashboard** shows the queue, live
> runs, PRs, success rate, and cycle time.

## 1:15–2:45 — Live demo

**[Screen: dashboard at localhost:8000 — Queue section shows issues]**

> Here's the dispatcher live. The queue shows issues the scanner filed —
> real findings: urllib3 and pyjwt advisories in Superset's pinned
> requirements, plus type-safety hotspots.

**[Terminal: `curl -X POST localhost:8000/dispatch/37`]**

> I'll dispatch the urllib3 CVE. That one call creates a Devin session with
> the issue as prompt, the repo context, and instructions to bump the pin,
> run verification, and open a PR.

**[Screen: click the session link → Devin UI working]**

> This is Devin actually working — it clones the repo, edits
> `requirements/base.txt`, and runs `pip-audit` to verify the fix. I want
> to pause here: this is why Devin and not a script — a naive bump to
> `requests==latest` can break the build. In an earlier session, Devin
> chose pyjwt 2.15.0 over 2.15.1 specifically because 2.15.1 was only two
> days old — supply-chain caution you can't get from regex.

## 2:45–3:45 — The loop closes

**[Screen: GitHub — the new PR, then issue #38 history showing merged PR #41]**

> When the session exits, the dispatcher records the PR — and it doesn't
> stop at 'PR opened.' It keeps tracking `pull_requests[].pr_state` until
> **merged**, then comments 'remediation complete' and closes the issue.
> Issue 38 here went through the full loop: scan → issue → session → PR →
> merged → issue closed.

**[Screen: dashboard metrics]**

> The metrics answer 'how would an engineering leader know this works':
> PRs opened *and merged*, success rate, cycle time — this fix took ~15
> minutes end to end — and agent messages per session as an effort proxy.
> One honest note: per-session billing isn't exposed on my service-user
> plan's API — it shows in the Devin UI's usage tab — so the dashboard
> reports populated metrics instead of a misleading zero.

## 3:45–4:30 — What makes it not-a-script

**[Screen: dashboard or repo]**

> The hard parts this handles that a cron-plus-Dependabot can't:
> deduplication so a recurring scan doesn't refire; grouping advisories
> per package so two CVEs don't spawn conflicting PRs; auto-nudging
> sessions paused for approval; detecting when remediation is already
> done — one session opened an empty PR because another had fixed the pin
> first, and the system closed it cleanly; and structured output, so
> results are machine-readable, not prose.

## 4:30–5:00 — Close

> To recap: a scheduled scanner finds real vulnerabilities, issues route
> to parallel Devin sessions, PRs get tracked to merge, and the whole loop
> is observable on the dashboard. Everything's Dockerized —
> `docker compose up` plus one curl — and the repos are public. Thanks.

## Recording tips

- **Pre-record the session footage**: real sessions take 10–20 min.
  Record yourself dispatching live, then cut to the finished session's
  Devin replay — don't wait on screen.
- Lead with **#38 / pyjwt merged PR** as proof; dispatch **#37** live for
  the "watch it work" moment.
- Rehearse the dispatch curl before recording — have the terminal ready.
