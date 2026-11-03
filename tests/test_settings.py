import sqlite3

from app.features.frame.urls import FRAME, SAY
from app.features.home.urls import HOME
from app.features.settings.urls import SAVE_SETTINGS, SETTINGS


def rows(tmp_path, sql):
    with sqlite3.connect(tmp_path / "nudgethis.sqlite3") as db:
        return db.execute(sql).fetchall()


async def test_settings_need_a_sign_in(anonymous):
    r = await anonymous.get(SETTINGS.href(), follow_redirects=False)
    assert r.status_code in (302, 303)


async def test_the_page_says_what_each_part_runs_on(client):
    page = (await client.get(SETTINGS.href())).text
    assert "Nudge" in page and "Coder" in page and "Hosting" in page and "Usage" in page
    assert "No API key" in page  # tests run on the stand-in model
    assert "No token: new apps cannot be made." in page


async def test_a_saved_token_is_sealed_and_takes_effect_without_a_restart(client, tmp_path):
    assert "Set YARD_TOKEN to make apps." in (await client.get(HOME.href())).text
    r = await client.post(
        SAVE_SETTINGS.href(), json={"s_yard_token": "yard-secret-1234", "clear": ""}
    )
    assert r.status_code == 200
    assert "datastar-patch-elements" in r.text or "navigate" in r.text or "location" in r.text
    stored = rows(tmp_path, "SELECT data FROM settings")
    assert stored and "yard-secret-1234" not in stored[0][0]  # sealed at rest
    assert "Set YARD_TOKEN to make apps." not in (await client.get(HOME.href())).text
    page = (await client.get(SETTINGS.href())).text
    assert "•••• 1234" in page and "yard-secret-1234" not in page
    assert "saved here" in page
    # Back to the environment's.
    await client.post(SAVE_SETTINGS.href(), json={"clear": "yard_token"})
    assert "Set YARD_TOKEN to make apps." in (await client.get(HOME.href())).text


async def test_an_empty_secret_field_keeps_the_saved_one(client, tmp_path):
    await client.post(SAVE_SETTINGS.href(), json={"s_yard_token": "keep-me-9999", "clear": ""})
    await client.post(SAVE_SETTINGS.href(), json={"s_yard_token": "", "s_domain": "example.org"})
    page = (await client.get(SETTINGS.href())).text
    assert "•••• 9999" in page
    assert "example.org" in page


async def test_a_bad_value_gets_a_toast(client, tmp_path):
    r = await client.post(SAVE_SETTINGS.href(), json={"s_effort": "maximum"})
    assert "Effort is one of" in r.text
    r = await client.post(SAVE_SETTINGS.href(), json={"s_template": "https://gitlab.com/a/b"})
    assert "github.com" in r.text
    r = await client.post(SAVE_SETTINGS.href(), json={"clear": "nope"})
    assert r.status_code == 400
    assert rows(tmp_path, "SELECT count(*) FROM settings") == [(0,)]


async def test_each_turn_of_nudge_is_counted(client, tmp_path):
    await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red", "shots": []})
    await client.drain_tasks()
    assert rows(tmp_path, "SELECT data->>'app' FROM usage") == [("alpha",)]
    page = (await client.get(SETTINGS.href())).text
    assert ">alpha<" in page  # the app's row in the usage table
    assert (await client.get(FRAME.href("alpha"))).status_code == 200


def test_a_secret_sealed_with_another_session_secret_is_not_set():
    from app.builder import Vault

    sealed = Vault(b"one-secret").seal("token")
    assert Vault(b"one-secret").open(sealed) == "token"
    assert Vault(b"another-secret").open(sealed) is None
