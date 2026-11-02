import base64
import json

import httpx
import pytest
from stario.testing import TestClient

from app.features.frame.urls import FRAME
from app.features.home.urls import HOME, HOME_LIVE, NEW_APP
from app.main import bootstrap
from tests.conftest import _env, signed_in, use_transport

YARD = "https://yard.example"
REPO = "https://github.com/Bobowski/nudge-plants"
SRC = "https://api.github.com/repos/Bobowski/nudge-template"
DST = "https://api.github.com/repos/Bobowski/nudge-plants"


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class Remote:
    """Yard and GitHub, as one mock transport."""

    def __init__(self, deploy="ok"):
        self.deploy = deploy
        self.calls: list[tuple[str, str, object, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url, method = str(request.url), request.method
        raw = request.content.decode()
        body = json.loads(raw) if raw.startswith("{") else raw
        self.calls.append((method, url, body, request.headers.get("authorization", "")))
        answers = {
            ("POST", f"{YARD}/api/v1/repos"): {"repo": REPO},
            ("GET", f"{SRC}/git/trees/main?recursive=1"): {
                "tree": [
                    {"path": "README.md", "mode": "100644", "type": "blob", "sha": "r"},
                    {"path": "app", "mode": "040000", "type": "tree", "sha": "t"},
                    {"path": "pyproject.toml", "mode": "100644", "type": "blob", "sha": "p"},
                    {"path": ".claude/skills/x", "mode": "120000", "type": "blob", "sha": "l"},
                ]
            },
            ("GET", f"{SRC}/git/blobs/p"): {"content": b64('[project]\nname = "starter"\n')},
            ("GET", f"{SRC}/git/blobs/l"): {"content": b64("../../.agents/skills/x")},
            ("PUT", f"{DST}/contents/README.md"): {
                "content": {"sha": "readme"},
                "commit": {"sha": "c0"},
            },
            ("POST", f"{DST}/git/trees"): {"sha": "tree1"},
            ("POST", f"{DST}/git/commits"): {"sha": "c1"},
            ("PATCH", f"{DST}/git/refs/heads/main"): {},
            ("POST", f"{YARD}/api/v1/apps"): {"app": {}},
            ("PUT", f"{YARD}/api/v1/apps/nudge-plants/caddy"): {},
            ("POST", f"{YARD}/api/v1/apps/nudge-plants/deploy"): {"deploy": {}},
            ("GET", f"{YARD}/api/v1/apps/nudge-plants/deploy"): {
                "deploy": {"started": "t1", "status": self.deploy, "error": "boom"}
            },
        }
        if (method, url) == ("POST", f"{YARD}/api/v1/repos/token"):
            assert isinstance(body, dict)
            return httpx.Response(200, json={"token": "token-" + body["repo"].rsplit("/", 1)[1]})
        if (method, url) == ("POST", f"{DST}/git/blobs"):
            return httpx.Response(200, json={"sha": f"blob{len(self.sent('POST', url)) - 1}"})
        if (method, url) in answers:
            return httpx.Response(200, json=answers[(method, url)])
        return httpx.Response(404, text=f"{method} {url}")

    def sent(self, method: str, url: str) -> list:
        return [b for m, u, b, _ in self.calls if m == method and u == url]


@pytest.fixture
def yard(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    monkeypatch.setenv("YARD_URL", YARD)
    monkeypatch.setenv("YARD_TOKEN", "yard-token")
    monkeypatch.setattr("app.coder.yard.POLL", 0)

    def make(remote: Remote):
        use_transport(monkeypatch, remote)
        return signed_in(TestClient(bootstrap, request_timeout=5))

    return make


async def test_home_lists_the_apps(client):
    r = await client.get(HOME.href())
    assert r.status_code == 200
    assert 'href="/a/alpha"' in r.text
    assert 'href="/a/beta"' in r.text
    assert "alpha.example" in r.text
    assert "Set YARD_TOKEN to make apps." in r.text


async def test_new_app_makes_a_repo_copies_the_template_and_deploys(yard):
    remote = Remote()
    async with yard(remote) as client:
        r = await client.post(NEW_APP.href(), json={"new_name": "Plants"})
        assert r.status_code == 200
        await client.drain_tasks()
        home = (await client.get(HOME.href())).text
        assert 'href="/a/nudge-plants"' in home
        assert "https://plants.wrati.dev" in home
        frame = await client.get(FRAME.href("nudge-plants"))
        assert frame.status_code == 200
        assert 'src="https://plants.wrati.dev"' in frame.text
    blobs = remote.sent("POST", f"{DST}/git/blobs")
    assert base64.b64decode(blobs[0]["content"]) == b'[project]\nname = "nudge-plants"\n'
    (tree,) = remote.sent("POST", f"{DST}/git/trees")
    assert [(e["path"], e["mode"], e["sha"]) for e in tree["tree"]] == [
        ("pyproject.toml", "100644", "blob0"),
        (".claude/skills/x", "120000", "blob1"),
        ("README.md", "100644", "readme"),
    ]
    assert remote.sent("PATCH", f"{DST}/git/refs/heads/main") == [{"sha": "c1"}]
    writes = {a for m, u, _, a in remote.calls if u.startswith(DST)}
    assert writes == {"Bearer token-nudge-plants"}
    assert remote.sent("POST", f"{YARD}/api/v1/apps") == [
        {"name": "nudge-plants", "repo": REPO, "ref": "main"}
    ]
    (site,) = remote.sent("PUT", f"{YARD}/api/v1/apps/nudge-plants/caddy")
    assert site.startswith("plants.wrati.dev {")
    assert "header -X-Frame-Options" in site
    assert 'frame-ancestors http://127.0.0.1:8000"' in site
    assert "reverse_proxy nudge-plants-app-1:8000" in site


async def test_a_failed_first_deploy_marks_the_app_failed(yard, tmp_path):
    async with yard(Remote(deploy="failed")) as client:
        await client.post(NEW_APP.href(), json={"new_name": "plants"})
        await client.drain_tasks()
        home = (await client.get(HOME.href())).text
        assert "the first deploy did not go live: boom" in home
        assert 'href="/a/nudge-plants"' not in home
        assert (await client.get(FRAME.href("nudge-plants"))).status_code == 404


async def test_bad_or_taken_names_get_a_toast(yard):
    remote = Remote()
    async with yard(remote) as client:
        for name in ("a", "-x", "www", "x" * 31, "a_b"):
            r = await client.post(NEW_APP.href(), json={"new_name": name})
            assert "A name is 2 to 30" in r.text
        await client.post(NEW_APP.href(), json={"new_name": "plants"})
        await client.drain_tasks()
        r = await client.post(NEW_APP.href(), json={"new_name": "plants"})
        assert "plants exists." in r.text
    assert len(remote.sent("POST", f"{YARD}/api/v1/repos")) == 1


async def test_without_a_yard_token_new_app_says_so(client):
    r = await client.post(NEW_APP.href(), json={"new_name": "plants"})
    assert "Set YARD_TOKEN to make apps." in r.text


async def test_an_unreachable_yard_marks_the_app_failed(yard):
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed", request=request)

    async with yard(down) as client:
        await client.post(NEW_APP.href(), json={"new_name": "plants"})
        await client.drain_tasks()
        home = (await client.get(HOME.href())).text
        assert "Yard at https://yard.example did not answer" in home


async def test_a_failed_app_can_be_made_again(yard):
    async with yard(Remote(deploy="failed")) as client:
        await client.post(NEW_APP.href(), json={"new_name": "plants"})
        await client.drain_tasks()
    remote = Remote()
    async with yard(remote) as client:
        r = await client.post(NEW_APP.href(), json={"new_name": "plants"})
        assert "exists" not in r.text
        await client.drain_tasks()
        home = (await client.get(HOME.href())).text
        assert 'href="/a/nudge-plants"' in home
        assert "did not go live" not in home


async def test_the_home_stream_shows_each_step_and_the_ready_app(yard):
    async with yard(Remote()) as client:
        async with client.stream("GET", HOME_LIVE.href(), timeout=2) as live:
            events = live.iter_events()
            first = await anext(events)
            assert first["event"] == "datastar-patch-elements"
            await client.post(NEW_APP.href(), json={"new_name": "plants"})
            seen = ""
            try:
                for _ in range(12):
                    event = await anext(events)
                    seen += event["data"]
                    if 'href="/a/nudge-plants"' in seen:
                        break
            except TimeoutError:
                pass
            assert "Making the repo" in seen or "Waiting" in seen
            assert 'href="/a/nudge-plants"' in seen


async def test_a_restart_marks_an_unfinished_app_failed(yard):
    class Hang(Remote):
        def __call__(self, request):
            if str(request.url).endswith("/api/v1/repos"):
                raise httpx.ConnectTimeout("slow", request=request)
            return super().__call__(request)

    async with yard(Hang()) as client:
        await client.post(NEW_APP.href(), json={"new_name": "plants"})
    async with yard(Remote()) as client:
        home = (await client.get(HOME.href())).text
        assert "Making the repo" not in home


async def test_an_unexpected_error_marks_the_app_failed(yard):
    class Odd(Remote):
        def __call__(self, request):
            if str(request.url).endswith("/api/v1/repos"):
                return httpx.Response(200, json={"nothing": "here"})
            return super().__call__(request)

    async with yard(Odd()) as client:
        await client.post(NEW_APP.href(), json={"new_name": "plants"})
        await client.drain_tasks()
        home = (await client.get(HOME.href())).text
        assert "KeyError" in home
        assert "Making the repo" not in home
