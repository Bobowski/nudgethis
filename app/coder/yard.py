"""Yard: wait for the deploy that a push to main starts."""

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

    async def last_deploy(self, app: str) -> dict[str, Any]:
        """The newest deploy of the app: status (running, ok, failed, reverted), started, error."""
        r = await self.http.get(
            f"{self.url}/api/v1/apps/{app}/deploy",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        if r.status_code == 404:
            return {}
        if r.status_code >= 400:
            raise CoderError(f"Yard answered {r.status_code}: {r.text[:200]}")
        return r.json()["deploy"]

    async def next_deploy(self, app: str, after: str) -> dict[str, Any]:
        """The first deploy that started after `after` (a `started` value) and has ended."""
        while True:
            deploy = await self.last_deploy(app)
            if deploy and deploy.get("started") != after and deploy.get("status") != "running":
                return deploy
            await asyncio.sleep(POLL)
