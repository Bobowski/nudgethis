import re

from app.features.frame.urls import ACT, FRAME, FRAME_LIVE, SAY

TAB = {"datastar": '{"tab": "t1"}'}
PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAD"
    "UlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def next_patch(events):
    event = await anext(events)
    while event["event"] != "datastar-patch-elements":
        event = await anext(events)
    return event["data"]


async def collect(events, limit=8):
    blob = ""
    try:
        for _ in range(limit):
            blob += await next_patch(events)
    except TimeoutError:
        pass
    return blob


async def test_unknown_app_is_404(client):
    r = await client.get(FRAME.href("nope"))
    assert r.status_code == 404


async def test_frame_loads_the_app_in_the_iframe(client):
    r = await client.get(FRAME.href("alpha"))
    assert r.status_code == 200
    assert 'src="https://alpha.example"' in r.text
    assert "data-ignore-morph" in r.text


async def test_say_repaints_the_stream(client):
    async with client.stream("GET", FRAME_LIVE.href("alpha"), params=TAB, timeout=2) as live:
        events = live.iter_events()
        assert 'id="frame"' in await next_patch(events)
        r = await client.post(
            SAY.href("alpha"), json={"tab": "t1", "text": "make it red", "shots": []}
        )
        assert r.status_code == 200
        html = await collect(events)
        assert "make it red" in html
        assert 'class="working"' in html
        assert "On it." in html
        assert "Done." in html
        assert 'class="act undo"' in html


async def test_empty_say_writes_nothing(client):
    before = (await client.get(FRAME.href("alpha"))).text.count('class="msg')
    r = await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "  "})
    assert r.status_code == 204
    after = (await client.get(FRAME.href("alpha"))).text.count('class="msg')
    assert after == before


async def test_bad_say_is_400(client):
    def post(body):
        return client.post(SAY.href("alpha"), json=body)

    assert (await post({"tab": "t1", "text": "x" * 2001})).status_code == 400
    assert (await post({"tab": "t1", "text": "x", "shots": "nope"})).status_code == 400
    assert (await post({"tab": "t1", "shots": [PNG, PNG, PNG]})).status_code == 400
    assert (await post({"tab": "t1", "shots": ["data:image/png;base64,AAAA"]})).status_code == 400
    assert (await post({"tab": "t1", "shots": ["hello"]})).status_code == 400


async def test_say_on_unknown_app_is_404(client):
    r = await client.post(SAY.href("nope"), json={"tab": "t1", "text": "hi"})
    assert r.status_code == 404


async def test_a_shot_is_saved_served_and_shown(client, tmp_path):
    async with client.stream("GET", FRAME_LIVE.href("alpha"), params=TAB, timeout=2) as live:
        events = live.iter_events()
        await next_patch(events)
        r = await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "look", "shots": [PNG]})
        assert r.status_code == 200
        assert "/shots/" in await next_patch(events)
    saved = list((tmp_path / "shots").glob("*.png"))
    assert len(saved) == 1
    r = await client.get(f"/shots/{saved[0].name}")
    assert r.status_code == 200
    assert r.headers.get("content-type") == "image/png"
    assert r.content == saved[0].read_bytes()


async def done_message_id(client, app="alpha"):
    await client.post(SAY.href(app), json={"tab": "t1", "text": "change it", "shots": []})
    await client.drain_tasks()
    page = (await client.get(FRAME.href(app))).text
    m = re.search(r"\$message_id\s*=\s*(\d+)", page)
    assert m is not None
    return int(m.group(1))


async def next_rev(events) -> int:
    event = await anext(events)
    while event["event"] != "datastar-patch-signals":
        event = await anext(events)
    m = re.search(r'"_rev":(\d+)', event["data"].replace(" ", ""))
    assert m is not None
    return int(m.group(1))


async def test_a_live_change_reloads_the_frame(client):
    async with client.stream("GET", FRAME_LIVE.href("alpha"), params=TAB, timeout=2) as live:
        events = live.iter_events()
        assert await next_rev(events) == 0
        await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "make it red"})
        rev = 0
        while rev == 0:
            rev = await next_rev(events)
        assert rev == 1


async def test_undo_reverts_the_change_and_reloads_again(client):
    mid = await done_message_id(client)
    r = await client.post(
        ACT.href("alpha"), json={"tab": "t1", "message_id": mid, "action": "undo"}
    )
    assert r.status_code == 204
    await client.drain_tasks()
    page = (await client.get(FRAME.href("alpha"))).text
    assert "Undone. (fake)" in page
    assert 'class="act undo"' not in page
    async with client.stream("GET", FRAME_LIVE.href("alpha"), params=TAB, timeout=2) as live:
        assert await next_rev(live.iter_events()) == 2


async def test_undo_twice_is_409(client):
    mid = await done_message_id(client)
    body = {"tab": "t1", "message_id": mid, "action": "undo"}
    assert (await client.post(ACT.href("alpha"), json=body)).status_code == 204
    assert (await client.post(ACT.href("alpha"), json=body)).status_code == 409


async def test_act_on_a_message_of_another_app_is_404(client):
    mid = await done_message_id(client, app="beta")
    r = await client.post(
        ACT.href("alpha"), json={"tab": "t1", "message_id": mid, "action": "undo"}
    )
    assert r.status_code == 404


async def test_unknown_action_is_400(client):
    mid = await done_message_id(client)
    r = await client.post(
        ACT.href("alpha"), json={"tab": "t1", "message_id": mid, "action": "ship"}
    )
    assert r.status_code == 400


async def test_a_live_change_leaves_the_pill_idle(client):
    await done_message_id(client)
    page = (await client.get(FRAME.href("alpha"))).text
    assert 'data-state="idle"' in page
    assert "Ready to ship" not in page
