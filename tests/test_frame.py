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
        assert "Ship" in html
        assert "Not yet" in html


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


async def test_ship_patches_rev_and_says_live(client):
    mid = await done_message_id(client)
    async with client.stream("GET", FRAME_LIVE.href("alpha"), params=TAB, timeout=2) as live:
        events = live.iter_events()
        await next_patch(events)
        r = await client.post(
            ACT.href("alpha"), json={"tab": "t1", "message_id": mid, "action": "ship"}
        )
        assert r.status_code == 204
        assert "Live." in await next_patch(events)
        event = await anext(events)
        assert event["event"] == "datastar-patch-signals"
        rev = re.search(r'"_rev":(\d+)', event["data"].replace(" ", ""))
        assert rev is not None and int(rev[1]) > 0


async def test_act_on_a_shipped_change_is_409(client):
    mid = await done_message_id(client)
    body = {"tab": "t1", "message_id": mid, "action": "ship"}
    assert (await client.post(ACT.href("alpha"), json=body)).status_code == 204
    assert (await client.post(ACT.href("alpha"), json=body)).status_code == 409


async def test_act_on_a_message_of_another_app_is_404(client):
    mid = await done_message_id(client, app="beta")
    r = await client.post(
        ACT.href("alpha"), json={"tab": "t1", "message_id": mid, "action": "ship"}
    )
    assert r.status_code == 404


async def test_unknown_action_is_400(client):
    mid = await done_message_id(client)
    r = await client.post(ACT.href("alpha"), json={"tab": "t1", "message_id": mid, "action": "fly"})
    assert r.status_code == 400


async def test_not_yet_drops_the_change(client):
    mid = await done_message_id(client)
    async with client.stream("GET", FRAME_LIVE.href("alpha"), params=TAB, timeout=2) as live:
        events = live.iter_events()
        await next_patch(events)
        r = await client.post(
            ACT.href("alpha"), json={"tab": "t1", "message_id": mid, "action": "not_yet"}
        )
        assert r.status_code == 204
        assert "Okay. Tell me what to change." in await next_patch(events)


async def test_a_ready_change_lights_the_pill(client):
    await done_message_id(client)
    page = (await client.get(FRAME.href("alpha"))).text
    assert 'data-state="ready"' in page
    assert 'data-pending="1"' in page
    assert "Ready to ship" in page


async def test_a_change_of_another_app_leaves_the_pill_idle(client):
    await done_message_id(client, app="beta")
    page = (await client.get(FRAME.href("alpha"))).text
    assert 'data-state="idle"' in page
    assert "data-pending" not in page
