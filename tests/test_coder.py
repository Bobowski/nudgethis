import json
import sqlite3

import httpx
import pytest
from stario.testing import TestClient

from app.features.frame.urls import CODER, CODER_LIVE, FRAME, SAY, UNDO
from app.main import bootstrap
from tests.conftest import _env, signed_in, use_transport
from tests.test_frame import PNG

YARD = "https://yard.example"
REPO = "https://github.com/someone/alpha"


def variant(context: str, effort: str, fast: str, **flags) -> dict:
    params = [("context", context), ("reasoning_effort", effort), ("fast", fast)]
    return {"params": [{"id": k, "value": v} for k, v in params], **flags}


MODELS = [
    {"id": "default", "displayName": "Auto", "variants": [{"params": [], "isDefault": True}]},
    {
        "id": "grok-4.7",
        "displayName": "Grok 4.7",
        "parameters": [
            {
                "id": "context",
                "displayName": "Context",
                "values": [{"value": "256k"}, {"value": "500k"}],
            },
            {
                "id": "reasoning_effort",
                "displayName": "Effort",
                "values": [
                    {"value": "low", "displayName": "Low"},
                    {"value": "high", "displayName": "High"},
                ],
            },
            {
                "id": "fast",
                "displayName": "Fast",
                "values": [{"value": "false"}, {"value": "true", "displayName": "Fast\u200b"}],
            },
        ],
        "variants": [
            variant("256k", "high", "false"),
            variant("256k", "low", "false"),
            variant("500k", "high", "true", isDefault=True, isMaxMode=True),
        ],
    },
    {
        "id": "composer-2.5",
        "displayName": "Composer 2.5",
        "parameters": [
            {"id": "fast", "displayName": "Fast", "values": [{"value": "false"}, {"value": "true"}]}
        ],
        "variants": [{"params": [{"id": "fast", "value": "true"}], "isDefault": True}],
    },
]


class Remote:
    """Cursor and Yard, as one mock transport. Each finished run is a push; Yard deploys it."""

    def __init__(self, run="FINISHED", deploy="ok", start=200):
        self.run, self.deploy, self.start = run, deploy, start
        self.polls: dict[str, int] = {}
        self.pushes = 0
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        url = str(request.url)
        self.calls.append((request.method, url, body))
        if url == "https://api.cursor.com/v1/agents":
            if self.start != 200:
                error = {
                    "code": "usage_limit_exceeded",
                    "message": "Your prepaid balance is used up.",
                }
                return httpx.Response(self.start, json={"error": error})
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
        if url == "https://api.cursor.com/v1/models":
            return httpx.Response(200, json={"items": MODELS})
        if url == f"{YARD}/api/v1/apps/alpha":
            return httpx.Response(200, json={"app": {"name": "alpha", "repo": REPO}})
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
        assert "Took 0 s: Nudge 0 s, coding 0 s, going live 0 s" in page
    assert statuses(tmp_path) == ["live"]
    (launch,) = remote.sent("POST", "https://api.cursor.com/v1/agents")
    assert launch["repos"] == [{"url": REPO, "startingRef": "main"}]
    assert launch["workOnCurrentBranch"] is True
    assert "autoCreatePR" not in launch
    assert launch["prompt"]["text"].startswith("make the title red")
    assert "Do not use computer use" in launch["prompt"]["text"]
    assert "may not be technical" in launch["prompt"]["text"]
    assert "Work fast: test only what the change touches" in launch["prompt"]["text"]
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
    assert "Do not use computer use" in follow_up["prompt"]["text"]


async def test_a_failed_run_drops_the_change(cursor, tmp_path):
    async with cursor(Remote(run="ERROR")) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert "make that change this time" in page
        assert "Did run-1." not in page
    assert statuses(tmp_path) == ["dropped"]


async def test_an_app_yard_does_not_run_takes_its_repo_from_the_base(cursor, monkeypatch):
    class Elsewhere(Remote):
        def __call__(self, request):
            if str(request.url) == f"{YARD}/api/v1/apps/alpha":
                return httpx.Response(404)
            return super().__call__(request)

    monkeypatch.setenv("NUDGE_REPO_BASE", "https://github.com/base/")
    remote = Elsewhere()
    async with cursor(remote) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
    (launch,) = remote.sent("POST", "https://api.cursor.com/v1/agents")
    assert launch["repos"] == [{"url": "https://github.com/base/alpha", "startingRef": "main"}]


async def test_an_app_with_no_repo_drops_the_change(cursor, tmp_path):
    class Nowhere(Remote):
        def __call__(self, request):
            if str(request.url) == f"{YARD}/api/v1/apps/alpha":
                return httpx.Response(404)
            return super().__call__(request)

    remote = Nowhere()
    async with cursor(remote) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
        assert "start on that" in (await client.get(FRAME.href("alpha"))).text
    assert remote.sent("POST", "https://api.cursor.com/v1/agents") == []
    assert statuses(tmp_path) == ["dropped"]


async def test_a_failed_deploy_drops_the_change(cursor, tmp_path):
    async with cursor(Remote(deploy="failed")) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert "the app didn" in page and "boom" not in page
    assert statuses(tmp_path) == ["dropped"]


async def test_an_empty_balance_is_said_in_plain_words(cursor, tmp_path):
    async with cursor(Remote(start=400)) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert "run out of credit" in page
        assert "usage_limit" not in page and "answered 400" not in page
    assert statuses(tmp_path) == ["dropped"]


async def test_the_model_and_its_params_go_with_the_launch(cursor, monkeypatch):
    monkeypatch.setenv("CURSOR_MODEL", "grok-4.7:context=256k,reasoning_effort=high,fast=false")
    remote = Remote()
    async with cursor(remote) as client:
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
    (launch,) = remote.sent("POST", "https://api.cursor.com/v1/agents")
    assert launch["model"] == {
        "id": "grok-4.7",
        "params": [
            {"id": "context", "value": "256k"},
            {"id": "reasoning_effort", "value": "high"},
            {"id": "fast", "value": "false"},
        ],
    }


def test_a_bad_cursor_model_stops_the_config():
    from app.config import parse_cursor_model

    assert parse_cursor_model("") == ("", ())
    assert parse_cursor_model("composer-2.5") == ("composer-2.5", ())
    with pytest.raises(ValueError):
        parse_cursor_model("grok-4.7:context")


async def test_the_coder_tab_offers_cursors_models_and_the_default_params(cursor, monkeypatch):
    monkeypatch.setenv("CURSOR_MODEL", "grok-4.7")
    async with cursor(Remote()) as client:
        page = (await client.get(FRAME.href("alpha"))).text
    assert '<option value="grok-4.7" selected>Grok 4.7</option>' in page
    assert '<optgroup label="Cursor">' in page
    assert ">256k<" in page and ">On<" in page and ">Off<" in page
    # The default variant of Grok 4.7 is Max Mode; the tab starts on the normal one.
    assert "Max Mode" not in page


async def test_picking_a_model_and_a_param_changes_the_next_run(cursor):
    remote = Remote()
    async with cursor(remote) as client:
        for choice in ("model=grok-4.7", "reasoning_effort=low"):
            r = await client.post(CODER.href("alpha"), json={"tab": "t1", "coder_set": choice})
            assert r.status_code == 204
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        await client.drain_tasks()
    (launch,) = remote.sent("POST", "https://api.cursor.com/v1/agents")
    assert launch["model"] == {
        "id": "grok-4.7",
        "params": [
            {"id": "context", "value": "256k"},
            {"id": "reasoning_effort", "value": "low"},
            {"id": "fast", "value": "false"},
        ],
    }


async def test_a_max_mode_choice_says_so(cursor):
    async with cursor(Remote()) as client:
        for choice in ("model=grok-4.7", "context=500k", "fast=true"):
            await client.post(CODER.href("alpha"), json={"tab": "t1", "coder_set": choice})
        assert "Max Mode" in (await client.get(FRAME.href("alpha"))).text


async def test_bad_coder_choices_are_400(cursor):
    async with cursor(Remote()) as client:
        await client.post(
            CODER.href("alpha"), json={"tab": "t1", "coder_set": "model=composer-2.5"}
        )
        for choice in ("model=nope", "reasoning_effort=low", "fast=maybe", "junk"):
            r = await client.post(CODER.href("alpha"), json={"tab": "t1", "coder_set": choice})
            assert r.status_code == 400, choice


async def test_the_coder_stream_repaints_after_a_choice(cursor):
    async with cursor(Remote()) as client:
        async with client.stream("GET", CODER_LIVE.href("alpha"), timeout=2) as live:
            events = live.iter_events()
            await anext(events)
            await client.post(
                CODER.href("alpha"), json={"tab": "t1", "coder_set": "model=composer-2.5"}
            )
            event = await anext(events)
            assert '<option value="composer-2.5" selected>' in event["data"]
