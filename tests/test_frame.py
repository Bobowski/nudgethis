import re

from app.features.frame.urls import COLOR, FRAME, FRAME_LIVE, SAY, UNDO

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
        assert 'class="doing"' in html
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


async def live_change_id(client, app="alpha"):
    await client.post(SAY.href(app), json={"tab": "t1", "text": "change it", "shots": []})
    await client.drain_tasks()
    page = (await client.get(FRAME.href(app))).text
    m = re.search(r"\$change_id\s*=\s*(\d+)", page)
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
    cid = await live_change_id(client)
    r = await client.post(UNDO.href("alpha"), json={"tab": "t1", "change_id": cid})
    assert r.status_code == 204
    await client.drain_tasks()
    page = (await client.get(FRAME.href("alpha"))).text
    assert "Undone. (fake)" in page
    assert re.search(r'id="step-1".*?Undone', page)
    assert re.search(r'id="step-2".*?Done', page)
    async with client.stream("GET", FRAME_LIVE.href("alpha"), params=TAB, timeout=2) as live:
        assert await next_rev(live.iter_events()) == 2


async def test_undo_twice_is_409(client):
    cid = await live_change_id(client)
    body = {"tab": "t1", "change_id": cid}
    assert (await client.post(UNDO.href("alpha"), json=body)).status_code == 204
    assert (await client.post(UNDO.href("alpha"), json=body)).status_code == 409


async def test_undo_of_another_app_is_404(client):
    cid = await live_change_id(client, app="beta")
    r = await client.post(UNDO.href("alpha"), json={"tab": "t1", "change_id": cid})
    assert r.status_code == 404


async def test_a_bad_change_id_is_400(client):
    await live_change_id(client)
    r = await client.post(UNDO.href("alpha"), json={"tab": "t1", "change_id": "1"})
    assert r.status_code == 400


async def test_a_live_change_leaves_the_pill_idle(client):
    await live_change_id(client)
    page = (await client.get(FRAME.href("alpha"))).text
    assert 'data-state="idle"' in page
    assert "Ready to ship" not in page


async def test_the_panel_has_a_chat_composer_and_a_timeline(client):
    await live_change_id(client)
    page = (await client.get(FRAME.href("alpha"))).text
    assert 'id="chatbox"' in page
    assert 'id="composer"' in page
    assert re.search(r'id="step-1".*?Done', page)
    assert 'class="doing"' not in page  # nothing is working now


async def test_the_chat_shows_only_the_open_app(client):
    await client.post(SAY.href("alpha"), json={"tab": "t1", "text": "alpha only", "shots": []})
    await client.drain_tasks()
    assert "alpha only" in (await client.get(FRAME.href("alpha"))).text
    assert "alpha only" not in (await client.get(FRAME.href("beta"))).text


async def test_the_apps_panel_lists_every_app_and_its_work(client):
    page = (await client.get(FRAME.href("alpha"))).text
    assert 'id="apps"' in page
    assert 'href="/a/alpha"' in page and 'href="/a/beta"' in page


async def test_a_colour_paints_the_app_and_repaints_the_stream(client):
    async with client.stream("GET", FRAME_LIVE.href("alpha"), params=TAB, timeout=2) as live:
        events = live.iter_events()
        await next_patch(events)
        r = await client.post(COLOR.href("alpha"), json={"color": "blue"})
        assert r.status_code == 204
        html = await next_patch(events)
        assert "--accent: oklch(0.55 0.19 262)" in html
    page = (await client.get(FRAME.href("beta"))).text
    assert "--accent: oklch(0.6 0.22 32)" in page  # beta keeps the default red


async def test_a_bad_colour_is_400(client):
    r = await client.post(COLOR.href("alpha"), json={"color": "#ff0000"})
    assert r.status_code == 400
    r = await client.post(COLOR.href("nope"), json={"color": "blue"})
    assert r.status_code == 404


async def test_the_chat_only_tells_and_links_to_the_timeline(client):
    await live_change_id(client)
    page = (await client.get(FRAME.href("alpha"))).text
    chat = page[page.index('id="msgs"') : page.index('class="timeline"')]
    assert 'class="act undo"' not in chat
    assert "app.frame.show(&#x27;step-1&#x27;)" in chat or "app.frame.show('step-1')" in chat
    timeline = page[page.index('class="timeline"') :]
    assert 'class="act undo"' in timeline
    assert "change it" in timeline  # the person's own words, not the coder's brief


def test_work_in_progress_shows_one_short_line_at_the_top_of_the_chat():
    from stario import h
    from stario.markup import render as html

    from app.features.frame.data import Pulse
    from app.features.frame.views import render

    row = (
        7,
        "Add a toggle in the header that flips the CSS custom properties...",
        "working",
        "2026-11-03T10:00:00+00:00",
        None,
        "2026-11-03T10:00:00+00:00",
        None,
        None,
        None,
        "can we have dark mode",
        "On it.",
        "Dark mode switch",
    )
    page = html(
        render(
            Pulse([], {"alpha": "working"}, {}, {}),
            "alpha",
            "https://a",
            [row],
            0,
            "t1",
            h.Div(),
            ["alpha"],
        )
    )
    top = page[page.index('class="inflight"') : page.index('id="msgs"')]
    assert "Dark mode switch" in top and "in progress" in top
    assert "CSS custom properties" not in top
