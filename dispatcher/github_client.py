"""Minimal GitHub REST client for issues and comments."""

import requests


class GitHubClient:
    def __init__(self, token: str, repo: str):
        self._repo = repo
        self._http = requests.Session()
        self._http.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _url(self, path: str) -> str:
        return f"https://api.github.com/repos/{self._repo}{path}"

    def get_issue(self, number: int) -> dict:
        r = self._http.get(self._url(f"/issues/{number}"), timeout=30)
        r.raise_for_status()
        return r.json()

    def list_labeled_issues(self, label: str, state: str = "open") -> list[dict]:
        r = self._http.get(
            self._url("/issues"),
            params={"labels": label, "state": state, "per_page": 100},
            timeout=30,
        )
        r.raise_for_status()
        return [i for i in r.json() if "pull_request" not in i]

    def comment(self, issue_number: int, body: str):
        r = self._http.post(
            self._url(f"/issues/{issue_number}/comments"), json={"body": body}, timeout=30
        )
        r.raise_for_status()

    def set_labels(self, issue_number: int, labels: list[str]):
        r = self._http.post(
            self._url(f"/issues/{issue_number}/labels"), json={"labels": labels}, timeout=30
        )
        r.raise_for_status()

    def remove_label(self, issue_number: int, label: str):
        self._http.delete(self._url(f"/issues/{issue_number}/labels/{label}"), timeout=30)
