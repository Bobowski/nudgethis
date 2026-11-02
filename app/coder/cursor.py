"""Cursor Cloud Agents, API v1: a run on a repo pushes to main; poll it to the end."""

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


@dataclass(frozen=True, slots=True)
class Cursor:
    http: httpx.AsyncClient
    key: str
    model: str = ""

    async def call(self, method: str, path: str, body: dict | None = None) -> Any:
        try:
            r = await self.http.request(
                method, API + path, json=body, headers={"Authorization": f"Bearer {self.key}"}
            )
        except httpx.HTTPError as exc:
            raise CoderError(f"Cursor did not answer: {exc}") from exc
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
            "workOnCurrentBranch": True,
            "name": name[:100],
        }
        if self.model:
            body["model"] = {"id": self.model}
        out = await self.call("POST", "/agents", body)
        return out["agent"]["id"], out["run"]["id"]

    async def follow_up(self, agent_id: str, text: str) -> tuple[str, str]:
        """A new run of the same agent, which remembers what it pushed."""
        out = await self.call("POST", f"/agents/{agent_id}/runs", {"prompt": {"text": text}})
        return agent_id, out["run"]["id"]

    async def wait(self, agent_id: str, run_id: str) -> Run:
        while True:
            run = await self.call("GET", f"/agents/{agent_id}/runs/{run_id}")
            if run["status"] in DONE:
                break
            await asyncio.sleep(POLL)
        return Run(status=run["status"], result=str(run.get("result") or "").strip())
