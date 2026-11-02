import json
import sqlite3

import httpx
import pytest
from stario.testing import TestClient

from app.features.frame.urls import FRAME, SAY, UNDO
from app.main import bootstrap
from tests.conftest import _env, signed_in, use_transport
from tests.test_frame import PNG

YARD = "https://yard.example"


class Remote:
    """Cursor and Yard, as one mock transport. Each finished run is a push; Yard deploys it."""

    def __init__(self, run="FINISHED", deploy="ok"):
        self.run, self.deploy = run, deploy
        self.polls: dict[str, int] = {}
        self.pushes = 0
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        url = str(request.url)
        self.calls.append((request.method, url, body))
        if url == "https://api.cursor.com/v1/agents":
            return httpx.Response(200, json={"agent": {"id": "bc-1"}, "run": {"id": "run-1"}})
        if url == "https://api.cursor.com/v1/agents/bc-1/runs":
            return httpx.Response(200, json={"run": {"id": "run-2"}})
        if url.startswith("https://api.cursor.com/v1/agents/bc-1/runs/"):
            run_id = url.rsplit("/", 1)[1]
            self.polls[run_id] = self.polls.get(run_id, 0) + 1
            if self.polls[run_id] < 2:
                return httpx.Response(200, json={"status": "RUNNING"})
            if self.polls[run_id] == 2 and self.run == "FINISHED":
                self.pushes += 1
            return httpx.Response(200, json={"status": self.run, "result": f"Did {run_id}."})
        if url == f"{YARD}/api/v1/apps/alpha/deploy":
            assert request.headers["authorization"] == "Bearer yard-token"
            status = "ok" if self.pushes == 0 else self.deploy
            deploy = {"started": f"t{self.pushes}", "status": status, "error": "boom"}
            return httpx.Response(200, json={"deploy": deploy})
        return httpx.Response(404)

    def sent(self, method: str, url: str) -> list[dict]:
        return [b for m, u, b in self.calls if m == method and u == url]


@pytest.fixture
def cursor(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    monkeypatch.setenv("CURSOR_API_KEY", "key")
    monkeypatch.setenv("YARD_URL", YARD)
    monkeypatch.setenv("YARD_TOKEN", "yard-token")
    monkeypatch.setattr("app.coder.cursor.POLL", 0)
    monkeypatch.setattr("app.coder.yard.POLL", 0)

    def make(remote: Remote):
        use_transport(monkeypatch, remote)
        return signed_in(TestClient(bootstrap, request_timeout=5))

    return make


def statuses(tmp_path) -> list[str]:
    con = sqlite3.connect(f"file:{tmp_path / 'nudgethis.sqlite3'}?mode=ro", uri=True)
    rows = con.execute("SELECT data->>'status' FROM changes ORDER BY id").fetchall()
    con.close()
    return [r[0] for r in rows]


async def live_change_id(client) -> int:
    page = (await client.get(FRAME.href("alpha"))).text
    start = page.index("$change_id = ") + len("$change_id = ")
    return int(page[start : page.index(";", start)])


async def test_a_change_pushes_to_main_and_goes_live_after_the_deploy(cursor, tmp_path):
    remote = Remote()
    async with cursor(remote) as client:
        await client.post(
            SAY.href("alpha"), json={"tab": "t1", "text": "make the title red", "shots": [PNG]}
        )
        await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert "Did run-1." in page
        assert 'class="act undo"' in page
    assert statuses(tmp_path) == ["live"]
    (launch,) = remote.sent("POST", "https://api.cursor.com/v1/agents")
    assert launch["repos"] == [{"url": "https://github.com/Bobowski/alpha", "startingRef": "main"}]
    assert launch["workOnCurrentBranch"] is True
    assert "autoCreatePR" not in launch
    assert launch["prompt"]["text"].startswith("make the title red")
    assert [i["mimeType"] for i in launch["prompt"]["images"]] == ["image/png"]


async def test_undo_is_a_follow_up_run_that_goes_live(cursor, tmp_path):
    remote = Remote()
    async with cursor(remote) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
        cid = await live_change_id(client)
        r = await client.post(UNDO.href("alpha"), json={"tab": "t1", "change_id": cid})
        assert r.status_code == 204
        await client.drain_tasks()
        assert "Did run-2." in (await client.get(FRAME.href("alpha"))).text
    assert statuses(tmp_path) == ["undone", "live"]
    (follow_up,) = remote.sent("POST", "https://api.cursor.com/v1/agents/bc-1/runs")
    assert follow_up["prompt"]["text"].startswith("Revert the change you pushed to main")


async def test_a_failed_run_drops_the_change(cursor, tmp_path):
    async with cursor(Remote(run="ERROR")) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
        assert "No change: Did run-1." in (await client.get(FRAME.href("alpha"))).text
    assert statuses(tmp_path) == ["dropped"]


async def test_a_failed_deploy_drops_the_change(cursor, tmp_path):
    async with cursor(Remote(deploy="failed")) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert "Pushed, but the deploy did not go live: boom" in page
    assert statuses(tmp_path) == ["dropped"]
