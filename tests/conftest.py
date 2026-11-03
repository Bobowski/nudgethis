import base64
import contextlib
import json
from functools import partial
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from stario.testing import TestClient

from app.features.auth.urls import AUTH_CALLBACK, AUTH_GOOGLE
from app.main import bootstrap

ADAM = "adam@example.com"


def google_token(request: httpx.Request) -> httpx.Response | None:
    """Google's token endpoint. In tests the code is the email that signs in."""
    if str(request.url) != "https://oauth2.googleapis.com/token":
        return None
    email = parse_qs(request.content.decode())["code"][0]
    claims = {"aud": "google-id", "email": email, "email_verified": True}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return httpx.Response(200, json={"id_token": f"h.{payload}.s"})


def use_transport(monkeypatch, handler=None):
    """Every outside call of the app goes to Google's mock, then to `handler`."""

    def answer(request: httpx.Request) -> httpx.Response:
        return google_token(request) or (handler(request) if handler else httpx.Response(404))

    transport = httpx.MockTransport(answer)
    monkeypatch.setattr("app.main.AsyncClient", partial(httpx.AsyncClient, transport=transport))


async def login(client, email=ADAM):
    r = await client.get(AUTH_GOOGLE.href(), follow_redirects=False)
    assert r.status_code == 303
    state = parse_qs(urlparse(str(r.headers.get("location"))).query)["state"][0]
    return await client.get(
        AUTH_CALLBACK.href(),
        params={"code": email, "state": state},
        follow_redirects=False,
    )


@contextlib.asynccontextmanager
async def signed_in(client: TestClient):
    async with client as c:
        await login(c)
        yield c


def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NUDGE_FAKE_DELAY", "0")
    monkeypatch.setenv("NUDGE_APPS", "alpha=https://alpha.example,beta=https://beta.example")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-of-at-least-thirty-two-chars")
    monkeypatch.setenv("NUDGE_ALLOWED_EMAILS", ADAM)
    # Tests never call the API: a developer's .env may hold a real key.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    use_transport(monkeypatch)


@pytest.fixture
async def client(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    async with signed_in(TestClient(bootstrap, request_timeout=5)) as c:
        yield c


@pytest.fixture
async def anonymous(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    async with TestClient(bootstrap, request_timeout=5) as c:
        yield c


@pytest.fixture
def spawn(tmp_path, monkeypatch):
    """Signed-in client factory; pass a FunctionModel function to script the model."""
    _env(monkeypatch, tmp_path)

    def make(fn=None):
        if fn is not None:
            from pydantic_ai.models.function import FunctionModel

            from app.nudge.agent import build_agent

            monkeypatch.setattr(
                "app.builder.build_agent",
                lambda config: build_agent(config, model=FunctionModel(fn)),
            )
        return signed_in(TestClient(bootstrap, request_timeout=5))

    return make
