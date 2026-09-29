"""Builds the Devin session prompt from a GitHub issue."""

PROMPT_TEMPLATE = """You are working on the repository `{repo}` (a fork of apache/superset).

Resolve GitHub issue #{issue_number}: {issue_title}

Issue body:
---
{issue_body}
---

Requirements:
- Clone the repo, read `AGENTS.md` first, and follow its standards (no `any` types, use `@superset-ui/core/components` rather than direct `antd` imports, MyPy-compliant type hints for Python).
- Create a branch named `devin/issue-{issue_number}`.
- Make the minimal change that satisfies the acceptance criteria in the issue.
- Run the verification commands from the issue body (tsc/eslint/pytest/mypy as applicable) and iterate until they pass.
- Open a pull request against `{repo}` titled `<issue title>` (conventional-commit format), with `Closes #{issue_number}` in the body and a summary of what you changed and which checks you ran.
- Before finishing, report your result via structured output with: pr_url, summary, files_changed, checks_passed, notes.
"""


def build_prompt(repo: str, issue: dict) -> str:
    return PROMPT_TEMPLATE.format(
        repo=repo,
        issue_number=issue["number"],
        issue_title=issue["title"],
        issue_body=(issue.get("body") or "").strip()[:8000],
    )
