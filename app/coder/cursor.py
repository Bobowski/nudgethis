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
class Param:
    id: str
    label: str
    values: tuple[tuple[str, str], ...]  # (value, label)


@dataclass(frozen=True, slots=True)
class Model:
    id: str
    label: str
    params: tuple[Param, ...]
    default: tuple[tuple[str, str], ...]
    max_mode: frozenset[frozenset[tuple[str, str]]]

    def settle(self, params: dict[str, str]) -> dict[str, str]:
        """The model's default params, with each valid one from `params` on top."""
        out = dict(self.default)
        for p in self.params:
            if params.get(p.id) in {value for value, _ in p.values}:
                out[p.id] = params[p.id]
        return out

    def is_max(self, params: dict[str, str]) -> bool:
        return frozenset(params.items()) in self.max_mode


def _label(text: str, value: str) -> str:
    text = text.replace("\u200b", "").strip()
    if value in ("true", "false"):
        return "On" if value == "true" else "Off"
    return text or value


def parse_models(items: list[dict[str, Any]]) -> tuple[Model, ...]:
    """GET /v1/models: each model, its params, and a default that avoids Max Mode."""
    models = []
    for item in items:
        params = tuple(
            Param(
                id=p["id"],
                label=p.get("displayName") or p["id"],
                values=tuple(
                    (str(v["value"]), _label(v.get("displayName", ""), str(v["value"])))
                    for v in p.get("values", [])
                ),
            )
            for p in item.get("parameters", [])
        )
        variants = [
            (tuple((v["id"], str(v["value"])) for v in var.get("params", [])), var)
            for var in item.get("variants", [])
        ]
        normal = [pair for pair, var in variants if not var.get("isMaxMode")]
        chosen = [pair for pair, var in variants if var.get("isDefault")]
        if chosen and chosen[0] not in normal and normal:
            chosen = normal
        models.append(
            Model(
                id=item["id"],
                label=item.get("displayName") or item["id"],
                params=params,
                default=(chosen or normal or [()])[0],
                max_mode=frozenset(
                    frozenset(pair) for pair, var in variants if var.get("isMaxMode")
                ),
            )
        )
    return tuple(models)


@dataclass(frozen=True, slots=True)
class Cursor:
    http: httpx.AsyncClient
    key: str

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

    async def models(self) -> tuple[Model, ...]:
        return parse_models((await self.call("GET", "/models"))["items"])

    async def start(
        self,
        repo: str,
        text: str,
        images: list[tuple[bytes, str]],
        name: str,
        model: str,
        params: dict[str, str],
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
        if model:
            body["model"] = {
                "id": model,
                "params": [{"id": key, "value": value} for key, value in params.items()],
            }
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
