import base64
import contextlib
import hashlib
import time
from functools import partial
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from stario import json
from stario.testing import TestClient

from app.common.providers import Http
from app.common.providers.google import GOOGLE
from app.features.auth.urls import LOGIN_CALLBACK, LOGIN_START
from app.main import bootstrap

ADAM = "adam@example.com"


class FakeProviders(Http):
    """Google, with the checks it makes. The code carries what Google remembers
    from the redirect: "<email> <nonce> <challenge> <redirect_uri>". An email
    that starts with "unverified+" comes back unverified."""

    async def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        assert url == f"{GOOGLE}/.well-known/openid-configuration"
        return {
            "issuer": GOOGLE,
            "authorization_endpoint": f"{GOOGLE}/o/oauth2/v2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
        }

    async def post_form(self, url: str, form: dict[str, str], headers: dict[str, str]) -> Any:
        raw, nonce, challenge, redirect_uri = form["code"].split(" ")
        digest = hashlib.sha256(form["code_verifier"].encode()).digest()
        assert base64.urlsafe_b64encode(digest).decode().rstrip("=") == challenge
        assert form["redirect_uri"] == redirect_uri
        assert url == "https://oauth2.googleapis.com/token"
        basic = base64.b64encode(b"google-id:google-secret").decode()
        assert headers["Authorization"] == f"Basic {basic}"
        email = raw.removeprefix("unverified+")
        claims = {
            "iss": GOOGLE,
            "aud": "google-id",
            "sub": f"sub-{raw}",
            "email": email,
            "email_verified": raw == email,
            "exp": time.time() + 60,
            "nonce": nonce,
        }
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        return {"id_token": f"header.{payload}.signature", "access_token": "token"}


def use_transport(monkeypatch, handler=None):
    """Every outside call of the app but the sign-in goes to `handler`."""

    def answer(request: httpx.Request) -> httpx.Response:
        return handler(request) if handler else httpx.Response(404)

    transport = httpx.MockTransport(answer)
    monkeypatch.setattr("app.main.AsyncClient", partial(httpx.AsyncClient, transport=transport))


async def start(client, provider="google", next_url="/") -> dict[str, str]:
    """POST the sign-in button; return the query of the redirect to the provider."""
    r = await client.post(
        LOGIN_START.href(provider), data={"next": next_url}, follow_redirects=False
    )
    assert r.status_code == 303
    return {k: v[0] for k, v in parse_qs(urlsplit(str(r.headers.get("location"))).query).items()}


async def login(client, email=ADAM, provider="google", next_url="/"):
    """Sign in as Google would: the start, then the callback with a code."""
    query = await start(client, provider, next_url)
    parts = [email, query.get("nonce", "-"), query["code_challenge"], query["redirect_uri"]]
    return await client.get(
        LOGIN_CALLBACK.href(provider),
        params={"code": " ".join(parts), "state": query["state"]},
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
    monkeypatch.setattr("app.main.Http", FakeProviders)


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
