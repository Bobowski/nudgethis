"""Cursor Cloud Agents, API v1: launch one run on a repo, then poll it to the end."""

import asyncio
import base64
from dataclasses import dataclass
from typing import Any

import httpx

from app.coder import CoderError

API = "https://api.cursor.com/v1"
POLL = 8.0
DONE = ("FINISHED", "ERROR", "CANCELLED", "EXPIRED")


@dataclass(frozen=True, slots=True)
class Run:
    status: str
    result: str
    branch: str
    pr_url: str


@dataclass(frozen=True, slots=True)
class Cursor:
    http: httpx.AsyncClient
    key: str
    model: str = ""

    async def call(self, method: str, path: str, body: dict | None = None) -> Any:
        r = await self.http.request(
            method, API + path, json=body, headers={"Authorization": f"Bearer {self.key}"}
        )
        if r.status_code >= 400:
            raise CoderError(f"Cursor answered {r.status_code}: {r.text[:200]}")
        return r.json()

    async def start(
        self, repo: str, text: str, images: list[tuple[bytes, str]], name: str
    ) -> tuple[str, str]:
        body: dict[str, Any] = {
            "prompt": {
                "text": text,
                "images": [
                    {"data": base64.b64encode(blob).decode(), "mimeType": mime}
                    for blob, mime in images[:5]
                ],
            },
            "repos": [{"url": repo, "startingRef": "main"}],
            "autoCreatePR": True,
            "skipReviewerRequest": True,
            "name": name[:100],
        }
        if self.model:
            body["model"] = {"id": self.model}
        out = await self.call("POST", "/agents", body)
        return out["agent"]["id"], out["run"]["id"]

    async def wait(self, agent_id: str, run_id: str) -> Run:
        while True:
            run = await self.call("GET", f"/agents/{agent_id}/runs/{run_id}")
            if run["status"] in DONE:
                break
            await asyncio.sleep(POLL)
        branches = (run.get("git") or {}).get("branches") or [{}]
        return Run(
            status=run["status"],
            result=str(run.get("result") or "").strip(),
            branch=str(branches[-1].get("branch") or ""),
            pr_url=str(branches[-1].get("prUrl") or ""),
        )
