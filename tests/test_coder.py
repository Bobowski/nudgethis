import json
import subprocess
from functools import partial

import httpx
import pytest
from stario.testing import TestClient

from app.features.frame.urls import ACT, FRAME, SAY
from app.main import bootstrap
from tests.conftest import _env
from tests.test_frame import PNG

PR = "https://github.com/Bobowski/alpha/pull/7"


class Remote:
    """Cursor, GitHub, and the framed app, as one mock transport."""

    def __init__(self, result="FINISHED"):
        self.result = result
        self.polls = 0
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.calls.append((request.method, str(request.url), body))
        url = str(request.url)
        if url == "https://api.cursor.com/v1/agents":
            return httpx.Response(200, json={"agent": {"id": "bc-1"}, "run": {"id": "run-1"}})
        if url.endswith("/agents/bc-1/runs/run-1"):
            self.polls += 1
            if self.polls < 2:
                return httpx.Response(200, json={"status": "RUNNING"})
            return httpx.Response(
                200,
                json={
                    "status": self.result,
                    "result": "Made the title red.",
                    "git": {"branches": [{"branch": "cursor/red", "prUrl": PR}]},
                },
            )
        if url.startswith("https://api.github.com/"):
            return httpx.Response(200, json={})
        return httpx.Response(200, text="ok")

    def sent(self, method: str, prefix: str) -> list[dict]:
        return [b for m, u, b in self.calls if m == method and u.startswith(prefix)]


@pytest.fixture
def cursor(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    monkeypatch.setenv("CURSOR_API_KEY", "key")
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr("app.coder.cursor.POLL", 0)
    monkeypatch.setattr("app.coder.checkout.RESTART", 0)

    def make(remote: Remote):
        transport = httpx.MockTransport(remote)
        monkeypatch.setattr("app.main.AsyncClient", partial(httpx.AsyncClient, transport=transport))
        return TestClient(bootstrap, request_timeout=5)

    return make


async def ready_message_id(client) -> int:
    page = (await client.get(FRAME.href("alpha"))).text
    start = page.index("$message_id = ") + len("$message_id = ")
    return int(page[start : page.index(";", start)])


async def test_a_change_runs_on_cursor_and_ship_merges_the_pr(cursor):
    remote = Remote()
    async with cursor(remote) as client:
        await client.post(
            SAY.href("alpha"), json={"tab": "t1", "text": "make the title red", "shots": [PNG]}
        )
        await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert "Made the title red." in page
        assert 'data-state="ready"' in page
        mid = await ready_message_id(client)
        r = await client.post(
            ACT.href("alpha"), json={"tab": "t1", "message_id": mid, "action": "ship"}
        )
        assert r.status_code == 204
        assert "Live." in (await client.get(FRAME.href("alpha"))).text
    (launch,) = remote.sent("POST", "https://api.cursor.com/v1/agents")
    assert launch["repos"] == [{"url": "https://github.com/Bobowski/alpha", "startingRef": "main"}]
    assert launch["autoCreatePR"] is True
    assert launch["prompt"]["text"].startswith("make the title red")
    assert [i["mimeType"] for i in launch["prompt"]["images"]] == ["image/png"]
    assert remote.sent("PUT", "https://api.github.com/repos/Bobowski/alpha/pulls/7/merge") == [
        {"merge_method": "squash"}
    ]


async def test_a_failed_run_drops_the_change(cursor):
    async with cursor(Remote(result="ERROR")) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert "No change: Made the title red." in page
        assert 'data-state="idle"' in page


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


async def test_the_local_clone_shows_the_branch_then_goes_back_to_main(
    cursor, tmp_path, monkeypatch
):
    origin, clones = tmp_path / "origin.git", tmp_path / "clones"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(clones / "alpha"))
    clone = clones / "alpha"
    for args in (
        ("config", "user.email", "t@t"),
        ("config", "user.name", "t"),
        ("commit", "-q", "--allow-empty", "-m", "first"),
        ("push", "-q", "origin", "main"),
        ("switch", "-q", "-c", "cursor/red"),
        ("commit", "-q", "--allow-empty", "-m", "red"),
        ("push", "-q", "origin", "cursor/red"),
        ("switch", "-q", "main"),
        ("branch", "-q", "-D", "cursor/red"),
    ):
        git(clone, *args)
    monkeypatch.setenv("NUDGE_CHECKOUTS", str(clones))

    def head():
        out = subprocess.run(
            ["git", "log", "-1", "--format=%s"], cwd=clone, capture_output=True, text=True
        )
        return out.stdout.strip()

    async with cursor(Remote()) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
        assert head() == "red"
        mid = await ready_message_id(client)
        await client.post(
            ACT.href("alpha"), json={"tab": "t1", "message_id": mid, "action": "not_yet"}
        )
        assert head() == "first"
