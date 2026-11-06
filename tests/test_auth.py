import base64
import sqlite3
import time
from http.cookies import SimpleCookie
from types import SimpleNamespace
from typing import Any, cast

import pytest
from litewriter import LiteWriter, Tx
from stario import Writer, json
from stario.cookies import SignedCookie
from stario.testing import TestClient

from app.common.providers import Flow, Http, LoginFailed
from app.common.providers.google import GOOGLE, Google
from app.common.session import local_path
from app.features.auth.urls import LOGIN, LOGIN_CALLBACK, LOGOUT
from app.features.frame import data as frame_data
from app.features.frame.urls import FRAME, SAY
from app.features.home import data as home_data
from app.features.home.urls import HOME
from app.features.settings import data as settings_data
from app.main import bootstrap
from tests.conftest import ADAM, FakeProviders, _env, login, start

DB = "nudgethis.sqlite3"


def counts(tmp_path) -> tuple[int, int]:
    with sqlite3.connect(tmp_path / DB) as db:
        users = db.execute("SELECT count(*) FROM users").fetchone()[0]
        return users, db.execute("SELECT count(*) FROM identities").fetchone()[0]


async def test_signed_out_pages_go_to_sign_in_and_back(anonymous):
    for url in (HOME.href(), FRAME.href("alpha"), "/shots/abc.png", "/settings"):
        r = await anonymous.get(url, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers.get("location") == LOGIN.href(query={"next": url})
    r = await login(anonymous, next_url=FRAME.href("alpha"))
    assert r.headers.get("location") == FRAME.href("alpha")


async def test_a_signed_out_command_navigates_to_sign_in(anonymous):
    r = await anonymous.post(
        SAY.href("alpha"), json={"tab": "t1", "text": "hi"}, headers={"datastar-request": "true"}
    )
    assert "window.location" in r.text


async def test_the_start_sends_state_nonce_and_pkce_to_the_old_callback(anonymous):
    query = await start(anonymous)
    assert query["code_challenge_method"] == "S256"
    assert query["state"] and query["nonce"] and query["code_challenge"]
    assert query["prompt"] == "select_account"
    # The redirect URI registered at Google: NUDGE_PUBLIC_URL + /auth/google/callback.
    assert query["redirect_uri"] == "http://127.0.0.1:8000/auth/google/callback"


async def test_an_allowed_account_signs_in(anonymous):
    r = await login(anonymous)
    assert r.status_code == 303
    assert r.headers.get("location") == HOME.href()
    assert "session" in r.cookies
    assert (await anonymous.get(HOME.href())).status_code == 200


async def test_a_tampered_session_is_signed_out(anonymous):
    await login(anonymous)
    value = anonymous.cookies["session"]
    anonymous.cookies["session"] = value[:-2] + ("AA" if value[-2:] != "AA" else "BB")
    r = await anonymous.get(HOME.href(), follow_redirects=False)
    assert r.status_code == 303


async def test_an_old_hand_signed_session_is_signed_out(anonymous):
    anonymous.cookies["session"] = f"{ADAM}.9999999999.c2lnbmF0dXJl"
    r = await anonymous.get(HOME.href(), follow_redirects=False)
    assert r.status_code == 303


async def test_a_session_from_before_accounts_signs_in_again(anonymous):
    # The cookie of the old sign-in: the same secret, the email as the user.
    headers = SimpleNamespace(lines=[])
    headers.add = lambda _name, value: headers.lines.append(value)
    w = cast(Writer, SimpleNamespace(headers=headers))
    SignedCookie("session", keys=["test-secret-of-at-least-thirty-two-chars"]).set(
        w, {"user": ADAM}
    )
    anonymous.cookies["session"] = SimpleCookie(headers.lines[0])["session"].value
    r = await anonymous.get(HOME.href(), follow_redirects=False)
    assert r.status_code == 303


async def test_https_uses_host_only_secure_cookies(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    monkeypatch.setenv("NUDGE_PUBLIC_URL", "https://nudge.example.com")
    async with TestClient(bootstrap, request_timeout=5) as c:
        query = await start(c)
        assert query["redirect_uri"] == "https://nudge.example.com/auth/google/callback"
        r = await login(c)
        assert r.cookies.keys() >= {"__Host-session"}
        assert "session" not in r.cookies
        set_cookie = " ".join(r.headers.getlist("set-cookie"))
        assert "Secure" in set_cookie and "Path=/" in set_cookie
        assert (await c.get(HOME.href())).status_code == 200


async def test_another_account_is_refused(anonymous):
    r = await login(anonymous, email="eve@example.com")
    assert r.headers.get("location") == LOGIN.href(query={"error": "not_allowed"})
    assert "cannot use nudgethis" in (await anonymous.get(r.headers.get("location"))).text
    assert (await anonymous.get(HOME.href(), follow_redirects=False)).status_code == 303


async def test_an_unverified_allowed_email_is_refused(anonymous):
    r = await login(anonymous, email=f"unverified+{ADAM}")
    assert r.headers.get("location") == LOGIN.href(query={"error": "not_allowed"})


async def test_a_callback_without_the_start_signs_nobody_in(anonymous):
    r = await anonymous.get(
        LOGIN_CALLBACK.href("google"),
        params={"code": f"{ADAM} x y z", "state": "forged"},
        follow_redirects=False,
    )
    assert r.headers.get("location") == LOGIN.href(query={"error": "expired"})
    assert (await anonymous.get(HOME.href(), follow_redirects=False)).status_code == 303


async def test_an_unknown_provider_is_404(anonymous):
    r = await anonymous.get(LOGIN_CALLBACK.href("github"), params={"state": "x"})
    assert r.status_code == 404


async def test_a_wrong_nonce_signs_nobody_in(anonymous):
    query = await start(anonymous)
    code = f"{ADAM} other {query['code_challenge']} {query['redirect_uri']}"
    r = await anonymous.get(
        LOGIN_CALLBACK.href("google"),
        params={"code": code, "state": query["state"]},
        follow_redirects=False,
    )
    assert r.headers.get("location") == LOGIN.href(query={"error": "failed"})
    assert (await anonymous.get(HOME.href(), follow_redirects=False)).status_code == 303


class OldToken(FakeProviders):
    """The ID token the old sign-in took: aud and a verified email, but no iss,
    no nonce, and an exp an hour ago."""

    async def post_form(self, url: str, form: dict[str, str], headers: dict[str, str]) -> Any:
        email = form["code"].split(" ")[0]
        claims: dict[str, Any] = {"aud": "google-id", "sub": "1", "email": email}
        claims |= {"email_verified": True, "exp": time.time() - 3600}
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        return {"id_token": f"h.{payload}.s"}


async def test_a_token_the_old_sign_in_took_now_fails(tmp_path, monkeypatch):
    # Before: this callback answered 303 to / with a session. Now: 303 to the error.
    _env(monkeypatch, tmp_path)
    monkeypatch.setattr("app.main.Http", OldToken)
    async with TestClient(bootstrap, request_timeout=5) as c:
        r = await login(c)
        assert r.headers.get("location") == LOGIN.href(query={"error": "failed"})
        assert "session" not in r.cookies
        assert (await c.get(HOME.href(), follow_redirects=False)).status_code == 303


async def test_a_cancel_at_google_says_so(anonymous):
    query = await start(anonymous)
    r = await anonymous.get(
        LOGIN_CALLBACK.href("google"),
        params={"error": "access_denied", "state": query["state"]},
        follow_redirects=False,
    )
    assert r.headers.get("location") == LOGIN.href(query={"error": "denied"})
    assert "cancelled" in (await anonymous.get(r.headers.get("location"))).text


async def test_an_outside_or_broken_next_goes_home(anonymous):
    assert (await login(anonymous, next_url="//evil.example")).headers.get("location") == "/"
    assert (await login(anonymous, next_url="/a\r\nb")).headers.get("location") == "/"
    r = await anonymous.get(LOGIN.href(query={"next": "//evil.example"}), follow_redirects=False)
    assert r.headers.get("location") == "/"


@pytest.mark.parametrize(
    "url", ["//evil.example", "/\\evil.example", "/a\r\nSet-Cookie: x", "a", 3]
)
def test_local_path_keeps_only_a_clean_path_on_this_site(url):
    assert local_path(url, "/home") == "/home"
    assert local_path("/a/alpha?x=1") == "/a/alpha?x=1"


async def test_logout_ends_the_session(client):
    r = await client.post(LOGOUT.href(), headers={"datastar-request": "true"})
    assert "window.location" in r.text
    assert (await client.get(HOME.href(), follow_redirects=False)).status_code == 303


async def test_one_account_stays_one_user(anonymous, tmp_path):
    await login(anonymous)
    await login(anonymous)
    assert counts(tmp_path) == (1, 1)


def old_schema(tx: Tx) -> None:
    """The tables before accounts: no users, no identities."""
    frame_data.schema(tx)
    home_data.schema(tx)
    settings_data.schema(tx)


async def test_the_data_from_before_accounts_stays(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    async with LiteWriter(tmp_path / DB, schema=old_schema) as db:
        await db.write(frame_data.add_request, "alpha", "make the title bold", [])
        await db.write(settings_data.set_setting, "model", "gpt-from-before")
    async with TestClient(bootstrap, request_timeout=5) as c:
        assert (await login(c)).headers.get("location") == HOME.href()
        assert "make the title bold" in (await c.get(FRAME.href("alpha"))).text
        assert "gpt-from-before" in (await c.get("/settings")).text
    with sqlite3.connect(tmp_path / DB) as raw:
        first = raw.execute("SELECT user_id FROM identities").fetchall()
    async with TestClient(bootstrap, request_timeout=5) as c:
        await login(c)
    with sqlite3.connect(tmp_path / DB) as raw:
        assert raw.execute("SELECT user_id FROM identities").fetchall() == first
        assert raw.execute("SELECT data->>'email' FROM users").fetchall() == [(ADAM,)]


class Answers(Http):
    def __init__(self, claims: dict[str, Any]) -> None:
        self.claims = claims

    async def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        return {
            "issuer": GOOGLE,
            "authorization_endpoint": f"{GOOGLE}/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
        }

    async def post_form(self, url: str, form: dict[str, str], headers: dict[str, str]) -> Any:
        body = base64.urlsafe_b64encode(json.dumps(self.claims).encode()).decode()
        return {"id_token": f"h.{body}.s"}


GOOD = {"iss": GOOGLE, "aud": "cid", "sub": "1", "exp": time.time() + 60, "nonce": "n"}


@pytest.mark.parametrize(
    ("claims", "reason"),
    [
        (GOOD | {"iss": "https://evil.example"}, "iss is"),
        (GOOD | {"aud": "another"}, "aud is"),
        (GOOD | {"aud": ["cid", "another"]}, "azp is"),
        (GOOD | {"exp": time.time() - 1}, "expired"),
        (GOOD | {"nonce": "other"}, "nonce"),
        (GOOD | {"sub": ""}, "no sub"),
    ],
)
async def test_google_checks_the_id_token(claims, reason):
    with pytest.raises(LoginFailed, match=reason):
        await Google("cid", "secret", Answers(claims)).identity(
            "code", "https://app.example/cb", Flow("s", "n", "v")
        )


async def test_google_accepts_its_issuer_without_the_scheme():
    google = Google("cid", "secret", Answers(GOOD | {"iss": "accounts.google.com"}))
    who = await google.identity("code", "https://app.example/cb", Flow("s", "n", "v"))
    assert who.issuer == GOOGLE
