from app.features.frame.urls import FRAME, SAY
from app.features.home.urls import HOME
from app.features.signin.urls import SIGNIN, SIGNOUT
from tests.conftest import signin


async def test_signed_out_pages_go_to_signin(anonymous):
    for url in (HOME.href(), FRAME.href("alpha"), "/shots/abc.png"):
        r = await anonymous.get(url, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers.get("location") == SIGNIN.href()


async def test_a_signed_out_command_navigates_to_signin(anonymous):
    r = await anonymous.post(
        SAY.href("alpha"), json={"tab": "t1", "text": "hi"}, headers={"datastar-request": "true"}
    )
    assert "window.location" in r.text


async def test_signin_sends_to_google_with_a_state(anonymous):
    r = await anonymous.get(SIGNIN.href(), follow_redirects=False)
    assert str(r.headers.get("location")).startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?"
    )
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Fsignin%2Fgoogle" in str(
        r.headers.get("location")
    )


async def test_an_allowed_account_signs_in(anonymous):
    r = await signin(anonymous)
    assert r.status_code == 303
    assert (await anonymous.get(HOME.href())).status_code == 200


async def test_another_account_is_refused(anonymous):
    r = await signin(anonymous, email="eve@example.com")
    assert r.status_code == 403
    assert "eve@example.com cannot use nudgethis." in r.text
    assert (await anonymous.get(HOME.href(), follow_redirects=False)).status_code == 303


async def test_a_wrong_state_is_400(anonymous):
    await anonymous.get(SIGNIN.href(), follow_redirects=False)
    r = await anonymous.get("/signin/google", params={"code": "x", "state": "forged"})
    assert r.status_code == 400


async def test_signout_ends_the_session(client):
    r = await client.post(SIGNOUT.href(), headers={"datastar-request": "true"})
    assert "window.location" in r.text
    assert (await client.get(HOME.href(), follow_redirects=False)).status_code == 303
