import json
import sqlite3

from pydantic_ai.messages import (
    BinaryContent,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from app.features.frame.urls import FRAME, SAY

PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAD"
    "UlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def answered(messages):
    last = messages[-1]
    return isinstance(last, ModelRequest) and any(isinstance(p, ToolReturnPart) for p in last.parts)


def script(captured, undo_id=1, note_app_only=False):
    def fn(messages, info):
        captured.append((messages, info))
        if answered(messages):
            return ModelResponse(parts=[TextPart("done replying")])
        for part in getattr(messages[-1], "parts", []):
            if isinstance(part, UserPromptPart):
                content = part.content
                text = (
                    content
                    if isinstance(content, str)
                    else " ".join(c for c in content if isinstance(c, str))
                )
                if "undo it" in text:
                    return ModelResponse(parts=[ToolCallPart("undo", {"change_id": undo_id})])
                if "note" in text:
                    return ModelResponse(
                        parts=[
                            ToolCallPart(
                                "remember",
                                {"note": "totals stay bold", "app_only": note_app_only},
                            )
                        ]
                    )
        return ModelResponse(parts=[ToolCallPart("start_change", {"brief": "b"})])

    return fn


def db_rows(path, sql):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = con.execute(sql).fetchall()
    con.close()
    return rows


async def say(client, app, text, shots=None):
    return await client.post(SAY.href(app), json={"tab": "t1", "text": text, "shots": shots or []})


async def test_current_message_carries_the_images(spawn, tmp_path):
    captured = []
    async with spawn(script(captured)) as client:
        await say(client, "alpha", "look", [PNG])
        await client.drain_tasks()
        await say(client, "alpha", "and again")
        await client.drain_tasks()
    first = captured[0][0][-1]
    shots = [
        c
        for part in first.parts
        for c in (part.content if isinstance(part.content, list) else [part.content])
        if isinstance(c, BinaryContent)
    ]
    assert len(shots) == 1
    later = [m for m in captured[-1][0][:-1]]
    assert not any(
        isinstance(c, BinaryContent)
        for m in later
        for part in getattr(m, "parts", [])
        for c in (part.content if isinstance(getattr(part, "content", None), list) else [])
    )


async def test_undo_tool_reverts_a_live_change(spawn, tmp_path):
    captured = []
    async with spawn(script(captured)) as client:
        await say(client, "alpha", "change it")
        await client.drain_tasks()
        await say(client, "alpha", "undo it")
        await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert "done replying" in page
        assert "Undone. (fake)" in page
    rows = db_rows(tmp_path / "nudgethis.sqlite3", "SELECT data FROM changes ORDER BY id")
    first, undo = (json.loads(r[0]) for r in rows)
    assert first["status"] == "undone"
    assert undo["status"] == "live"
    assert undo["undoes"] == 1


async def test_undo_tool_refuses_a_missing_change(spawn, tmp_path):
    captured = []
    async with spawn(script(captured, undo_id=99)) as client:
        await say(client, "alpha", "change it")
        await client.drain_tasks()
        await say(client, "alpha", "undo it")
        await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert "done replying" in page
        assert 'class="act undo"' in page
    rows = db_rows(tmp_path / "nudgethis.sqlite3", "SELECT data FROM changes")
    assert [json.loads(r[0])["status"] for r in rows] == ["live"]


async def test_remember_and_the_context_block(spawn, tmp_path):
    captured = []
    async with spawn(script(captured)) as client:
        await say(client, "alpha", "take a note")
        await client.drain_tasks()
        await say(client, "alpha", "change it again")
        await client.drain_tasks()
        await say(client, "alpha", "one more")
        await client.drain_tasks()
    rows = db_rows(tmp_path / "nudgethis.sqlite3", "SELECT data FROM notes")
    assert json.loads(rows[0][0]) == {
        "app": "",
        "text": "totals stay bold",
        "at": json.loads(rows[0][0])["at"],
    }
    info = captured[-1][1]
    instructions = info.instructions
    text = instructions if isinstance(instructions, str) else " ".join(instructions)
    assert "totals stay bold" in text
    assert "#1 alpha" in text


async def test_a_model_error_answers_with_the_fallback(spawn, tmp_path):
    def bad(messages, info):
        raise RuntimeError("boom")

    async with spawn(bad) as client:
        await say(client, "alpha", "change it")
        await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert "I could not reach the model. Try again." in page
        span = client.tracer.find_span("nudge.turn", root_id=None)
        assert span is not None and not span.ok


async def test_a_dead_placeholder_admits_it(spawn, tmp_path):
    path = tmp_path / "nudgethis.sqlite3"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
    con.execute(
        "INSERT INTO messages (data) VALUES (?)",
        [
            json.dumps(
                {
                    "at": "2026-01-01T00:00:00+00:00",
                    "role": "nudge",
                    "app": "alpha",
                    "text": "",
                    "shots": [],
                    "actions": [],
                    "change_id": None,
                    "thinking": True,
                }
            )
        ],
    )
    con.commit()
    con.close()
    async with spawn() as client:
        page = (await client.get(FRAME.href("alpha"))).text
        assert "I lost that one. Say it again." in page


async def test_each_app_has_its_own_conversation(spawn):
    captured = []
    async with spawn(script(captured)) as client:
        await say(client, "alpha", "alpha secret")
        await client.drain_tasks()
        await say(client, "beta", "hello beta")
        await client.drain_tasks()
    beta_turn = captured[-1]
    text = repr(beta_turn[0]) + repr(beta_turn[1].instructions)
    assert "hello beta" in text
    assert "alpha secret" not in text


async def test_a_phone_drawing_without_the_app_offers_the_fix_once(spawn):
    captured = []
    async with spawn(script(captured)) as client:
        for _ in range(2):
            r = await client.post(
                SAY.href("alpha"),
                json={"tab": "t1", "text": "this", "shots": [PNG], "snap": "none"},
            )
            assert r.status_code == 200
            await client.drain_tasks()
        page = (await client.get(FRAME.href("alpha"))).text
        assert (
            page.count("can&#x27;t send me a picture") + page.count("can't send me a picture") == 1
        )
        # Nudge knows how to fix it when the user says yes.
        await say(client, "alpha", "yes please")
        await client.drain_tasks()
        assert "nudge.js" in repr(captured[-1][1].instructions)
        # A drawing that comes with the app's picture clears it.
        await client.post(
            SAY.href("alpha"), json={"tab": "t1", "text": "ok", "shots": [PNG], "snap": "ok"}
        )
        await client.drain_tasks()
        await say(client, "alpha", "and now")
        await client.drain_tasks()
        assert "nudge.js" not in repr(captured[-1][1].instructions)
