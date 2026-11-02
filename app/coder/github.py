"""Merge or close the pull request that the coder opened."""

import re
from dataclasses import dataclass

import httpx

from app.coder import CoderError

PR_URL = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")


@dataclass(frozen=True, slots=True)
class GitHub:
    http: httpx.AsyncClient
    token: str

    async def pull(self, method: str, pr_url: str, suffix: str, body: dict) -> None:
        m = PR_URL.match(pr_url)
        if m is None:
            raise CoderError(f"not a GitHub pull request: {pr_url}")
        if not self.token:
            raise CoderError("GITHUB_TOKEN is not set")
        owner, repo, number = m.groups()
        r = await self.http.request(
            method,
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}{suffix}",
            json=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if r.status_code >= 400:
            raise CoderError(f"GitHub answered {r.status_code}: {r.text[:200]}")

    async def merge(self, pr_url: str) -> None:
        await self.pull("PUT", pr_url, "/merge", {"merge_method": "squash"})

    async def close(self, pr_url: str) -> None:
        await self.pull("PATCH", pr_url, "", {"state": "closed"})
