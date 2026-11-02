# Stario app guide

How to build a Stario app, unless the developer asks for something else.

Stario is Python hypermedia. A handler writes HTML. Datastar morphs it into the page. One open SSE response keeps a page live. State lives on the server. Docs: https://stario.dev/docs.

`## This app` at the end holds the notes of this app, under 4 KB: what it is, its workflow, its commands, its traps. A deep note on one topic goes in its own file, named by a line such as "Read `EDITOR.md` before you change the editor."

## Which skill

The skills are in `.agents/skills/`. Load `stario-api` before you write a handler, a view, or a test. `stario-create add <kit>` writes tested files. Then load the skill for the task:

- A static page (no command): no skill. Write `urls.py`, `views.py`, and a page class with one `show` (Code shape).
- A page that every tab sees change, in SQLite: `stario-feature` and `stario-litewriter`.
- State in memory, a message to one tab, an edit dialog: `stario-relay`.
- A sort, a filter, paging, a search as you type: `stario-view`.
- Work that takes seconds: `stario-jobs`.
- Login and accounts: `stario-auth`. Styles: `stario-tailwind-daisyui`. JavaScript: `stario-client`.
- Before a browser or a screenshot: `stario-browser-check`.

## Layout

```text
app/
  main.py           bootstrap: config, shared objects, Page(...).register(app)
  config.py         frozen Config dataclass, from_env(); every setting and secret
  assets.py         ASSETS, STYLE_CSS, DATASTAR_JS, SCRIPTS (files in static/)
  common/shell.py   page(title, body): the <html> document, @baked
  features/<page>/
    urls.py         Route values and the View of the query; imports only stario
    views.py        render(state, view, ...) -> the full document
    handlers.py     the page class: dependencies, register(app), one method per route
    data.py         schema, reads, and writes for the tables this page owns
  <name>/           code with no URL (an engine, a parser, an API client); never imports features/
tests/test_<page>.py
```

- A page is one resource: a path and its query. One folder, named after the URL noun: `/rooms/{room_id}` → `room`. Delete the folder with the page.
- A feature may import the `urls.py` and `data.py` of another feature, never its views or handlers.
- JavaScript lives in `static/js/<name>.js` as `app.<name>`, never in a Python string (skill `stario-client`).

## Stario rules

- Not ASGI: no Uvicorn, FastAPI, or response objects. `python -m app.main` runs `asyncio.run(serve(bootstrap))`.
- `bootstrap(app, span)` is an async generator with one `yield`: build shared objects, register pages, `yield`, clean up. Keep `app.use("/", same_origin(), security_headers())`.
- A handler is `async def (c: Context, w: Writer) -> None`. It answers once: `w.html`, `w.text`, `w.empty`, `w.redirect`, or `SSE(w)`.
- `Route("GET /rooms/{room_id}")` is one method on one path. `app.add(ROUTE, handler)`; `ROUTE.href(room_id, query={...})` builds the link. No `url_for`, no `app.get`.
- A stream loop iterates `c.alive(source)`. Background work is `c.app.create_task(coro)`, never bare `asyncio.create_task`.
- Shared state is an object built in `bootstrap`. No module-level state. No `os.environ` outside `config.py`. JSON goes through `stario.json`.

## A page is a resource

Sort every user action:

- **Go somewhere**, including a new sort, filter, or page: `<a href>`. The query holds the view (skill `stario-view`).
- **A result only this tab needs** (search as you type, a preview): a `GET` that answers `SSE(w).patch_elements(part)`. It changes no state.
- **Change state** (add, edit, delete, start a job): a command, `POST`.

A page whose state cannot change while it is open is static: `w.html(render(...))`. A page on shared state that can change is live:

```text
GET  /board        the first document; its top element has data.init(at.get(BOARD_LIVE.href(), retry="always"))
GET  /board/live   the stream: subscribe, send render(...), send it again after each change
POST /board/...    a command: read, validate, reply, execute
```

The stream is the only thing that sends HTML. A command never answers with HTML: other tabs would not see it. The stream follows one source: `db.watch(query)` for rows in SQLite (skill `stario-litewriter`), or `relay.subscribe(CHANGED, latest=True)` for state in memory (skill `stario-relay`).

## Commands: read, validate, reply, execute

1. Read: `await read_signals(c.req)`, `c.match.params`, `c.state["user"]`.
2. Validate. Bad, forged, or foreign input gets `w.text("why", status=400)` (or 403, 404) and `return`.
3. Reply: `w.empty()` (204), `SSE(w).patch_signals(...)`, or `SSE(w).navigate(url)`. A 303 to a Datastar request does not change the URL.
4. Execute: `await db.write(...)`. State in memory changes, then `relay.publish(CHANGED, {})`.

A message to one tab after the work goes to `tab.<id>` (skill `stario-relay`), never to shared state. Slow work is a job (skill `stario-jobs`). Blocking CPU work runs in `await asyncio.to_thread(fn, ...)`. A domain failure is `c.span.fail(...)`.

## Render and signals

- `render(...)` returns the whole document from state, and the view, the tab id, or the viewer. It does not fetch. Write the tree inline; a helper view is for a block in a loop.
- The element with `data.init(...)` and `data.signals({...}, if_missing=True)` keeps its tag, `id`, and attributes in every render.
- Signals carry what the user types or picks, the tab id, and client-only state. A leading `_` keeps a signal in the tab. The resource id is in the path, the view in the query, the user in a signed cookie (skill `stario-auth`).
- One signal per field and one `editing_id`, not one signal per row.
- A form shows it is busy: `data.indicator("_saving")` on the `<form>`, `data.attr("disabled", "$_saving")` on its button. `required` and `maxlength` stop empty input. The server checks again.
- A `<dialog>` or `<details>` keeps `data.preserve_attr("open")`.

## Storage

Choose with the developer. Do not add a database the app does not need. No persistence: an object built in `bootstrap`. SQLite: litewriter, a table of `id` plus `data` JSON (skill `stario-litewriter`). Files go in `config.data_dir`: `$PROJECT_DATA_DIR`, kept across deploys.

## Code shape

A page is one class in `handlers.py`. Its fields are its dependencies. `register(app)` adds its routes. Each route is one method that reads top to bottom.

```python
@dataclass(frozen=True, slots=True)
class BoardPage:
    db: LiteWriter
    relay: Relay[dict]

    def register(self, app: App) -> None:
        app.add(BOARD, self.show)

    async def show(self, c: Context, w: Writer) -> None:
        view = BoardView.from_query(c.req.query)
        w.html(render(list_tiles(self.db, view), view))
```

- Logic that one route needs stays in that method.
- A read or a write is a function in `data.py`: `list_*`, `get_*` (one or `None`), `add_*`, `set_*`, `remove_*`.
- A rule with no URL that several pages use is a plain function in `app/<name>/`.

Do not build: service classes, repositories, command objects, base pages, a `utils` module, a wrapper around `db`, a helper with one call site.

Read input with these lines, not with a helper:

```python
title = str(signals.get("title", "")).strip()  # text
done = signals.get("done") is True  # bool
editing_id = signals.get("editing_id")  # int: type(editing_id) is int, not isinstance
tile_id = c.match.params["tile_id"]  # path int: tile_id.isdecimal(), then int(tile_id)
tab = str(signals.get("tab", ""))  # tab id: tab.isalnum() and len(tab) <= 32
```

## Tests

Tests run the production `bootstrap` through `TestClient(bootstrap, request_timeout=5)`. Each page: it loads, a command repaints the stream, bad input gets 4xx. The next SSE event is the changed HTML; two streams are two tabs (skill `stario-feature`).

A `GET` sends signals in `params={"datastar": '{"q": "x"}'}`, a `POST` in `json=`.

## Checks

Check what you changed, at the cost the change needs. A handler, a query, or a stream gets a `TestClient` test. A style gets `just css`. Trust Stario, Datastar, litewriter, and Tailwind: pyright checks each call. Read their source only when pyright or a test fails. Run `just check` after a Python change and before a push.

`tests/test_pages.py` checks each linked page for an action with no route, an undefined `$signal`, a stream that changes its element, and a `<dialog>` that closes. A browser is only for client JS that holds state, or a bug that the HTML does not show. No computer use. When the user watches the app, the user is the browser: say what to look at. When it does not work: `curl` their server, then a failing test (skill `stario-browser-check`).

## Cursor Cloud specific instructions

Install is `.cursor/cloud-install.sh`.

## This app

nudgethis is a frame around a live web app. The app runs full-size in an iframe. Beside it is the pod: one conversation with an agent called Nudge. The user snaps a screenshot of the iframe, draws on it (arrow, circle, box, text), writes one sentence, and Nudge changes the app's code; the iframe reloads when the change is live.

Nudge is a real model now: OpenAI through pydantic-ai (Responses API) in `app/nudge/agent.py`. The coder is a Cursor Cloud Agent (`app/coder/cursor.py`, API v1): `start_change` launches a run on `<NUDGE_REPO_BASE>/<app>` with the shots, and the run pushes straight to `main` (`workOnCurrentBranch`). The `nudge.code` task polls the run, then waits for Yard's next deploy (`app/coder/yard.py`, needs `YARD_TOKEN`). A change goes working → deploying → live (or dropped). Undo (`FramePage.start_undo`, the button and the `undo` tool) marks the change undone and starts a follow-up run on the same agent that pushes a revert. Without `CURSOR_API_KEY` the coder is fake and makes a change live after `NUDGE_FAKE_DELAY`. A run or deploy wait that was going at a restart is followed again from bootstrap. A `POST /a/{app}/say` writes the "you" message and a thinking placeholder, then a `nudge.turn` task runs `agent.run` and fills the placeholder. Tools: `start_change`, `undo`, `remember`. The instructions live in `app/nudge/instructions.md` — the lead owns that text; the turn appends a dynamic block (open app, remembered notes, open changes). With no `OPENAI_API_KEY` the bootstrap builds a scripted `FunctionModel` ("fake mode", `nudge.model=fake`); tests always run in fake mode.

Config (`app/config.py`, all optional): `NUDGE_APPS` is a comma list of `name=url` (names `[a-z0-9-]+`, urls http(s); default `stario-site=https://stario.dev`). `NUDGE_FAKE_DELAY` seconds, default 4 (tests set 0). `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `NUDGE_MODEL` (default `gpt-6.1-terra`), `NUDGE_EFFORT` (default `low`), `NUDGE_HISTORY` (default 30), `NUDGE_TIMEOUT` (default 60), `CURSOR_API_KEY`, `CURSOR_MODEL`, `NUDGE_REPO_BASE` (default `https://github.com/Bobowski`), `YARD_URL`, `YARD_TOKEN`. `PROJECT_DATA_DIR` holds `nudgethis.sqlite3` and `shots/` for the saved snaps. `just smoke` runs `scripts/smoke_nudge.py` against the real model (just loads `.env`).

Sign-in: every page but `/auth` and `/static` needs a Google sign-in (`app/oauth/google.py`, `features/auth`, the same routes as honorata); the session cookie holds the email, and only `NUDGE_ALLOWED_EMAILS` get one. `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`, and `NUDGE_ALLOWED_EMAILS` are required; `NUDGE_PUBLIC_URL` builds the redirect URI. Tests sign in through a mocked Google (`tests/conftest.py`). The framed apps stay open.

The pill turns into the composer (`#composer`). A swipe left on the pill opens `#history`, a full-screen panel with a Chat tab (its own composer, `#chatbox`, and a status line) and a Timeline tab (every change, Undo on a live one). The snap needs `isolation: isolate` on the iframe: Element Capture sends no frames otherwise.

Features: `home` (`/`, the app list), `frame` (`/a/{app}` plus `live`, `say`, `undo`; owns the `messages`, `changes`, and `notes` tables through `data.py`), and `shots` (`/shots/{name}`, serves a saved snap). The frame stream follows `db.watch` on the messages-join-changes query and also patches `_rev`, the newest live change id; `app.frame.rev` in `static/js/frame.js` reloads the iframe and plays the ink check when it changes. Snap and the ink editor are `app.snap` and `app.ink` in `static/js/`. Styling is plain CSS in `static/css/style.css` (oklch custom properties, light and dark), with the self-hosted Instrument Sans variable font in `static/fonts/`.

The framed app must not send `x-frame-options: DENY` or a `frame-ancestors` rule that excludes nudgethis.
