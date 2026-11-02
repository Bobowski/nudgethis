"""Yard: make repos and apps, and wait for the deploy that a push to main starts."""

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from app.coder import CoderError

POLL = 3.0


@dataclass(frozen=True, slots=True)
class Yard:
    http: httpx.AsyncClient
    url: str
    token: str

    async def call(
        self, method: str, path: str, body: dict | bytes | None = None, *, missing_ok: bool = False
    ) -> Any:
        r = await self.http.request(
            method,
            f"{self.url}/api/v1{path}",
            json=body if isinstance(body, dict) else None,
            content=body if isinstance(body, bytes) else None,
            headers={"Authorization": f"Bearer {self.token}"}
            | ({"content-type": "text/caddyfile"} if isinstance(body, bytes) else {}),
        )
        if r.status_code == 404 and missing_ok:
            return {}
        if r.status_code >= 400:
            raise CoderError(f"Yard answered {r.status_code}: {r.text[:200]}")
        return r.json()

    async def last_deploy(self, app: str) -> dict[str, Any]:
        """The newest deploy of the app: status (running, ok, failed, reverted), started, error."""
        return (await self.call("GET", f"/apps/{app}/deploy", missing_ok=True)).get("deploy", {})

    async def create_repo(self, name: str) -> str:
        """A private repo on the forge; its https URL."""
        return (await self.call("POST", "/repos", {"name": name}))["repo"]

    async def repo_token(self, repo: str) -> str:
        """A token that reads and writes one repo for an hour."""
        return (await self.call("POST", "/repos/token", {"repo": repo}))["token"]

    async def create_app(self, name: str, repo: str, site: str) -> None:
        """An app that follows main, its Caddy site, and its first deploy."""
        await self.call("POST", "/apps", {"name": name, "repo": repo, "ref": "main"})
        await self.call("PUT", f"/apps/{name}/caddy", site.encode())
        await self.call("POST", f"/apps/{name}/deploy", {})

    async def next_deploy(self, app: str, after: str) -> dict[str, Any]:
        """The first deploy that started after `after` (a `started` value) and has ended."""
        while True:
            deploy = await self.last_deploy(app)
            if deploy and deploy.get("started") != after and deploy.get("status") != "running":
                return deploy
            await asyncio.sleep(POLL)
