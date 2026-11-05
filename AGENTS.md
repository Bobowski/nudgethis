# Stario app guide

How to build a Stario app, unless the developer asks for something else.

Stario is Python hypermedia. A handler writes HTML. Datastar morphs it into the page. One open SSE response keeps a page live. State lives on the server. Docs: https://stario.dev/docs.

The last section of this file holds the notes of this app, under 4 KB. A deep note on one topic goes in its own file, named by a line such as "Read `EDITOR.md` before you change the editor."

## Which skill

Read the one skill for the task in `.agents/skills/`, then write the code. `stario-create add <kit>` writes tested files.

- A static page (no command): no skill. Write `urls.py`, `views.py`, and a page class with one `show`.
- A page that every tab sees change, in SQLite: `stario-feature` and `stario-litewriter`.
- State in memory, a message to one tab, an edit dialog: `stario-relay`.
- A sort, a filter, paging, a search as you type: `stario-view`.
- Work that takes seconds, or a loop on a timer: `stario-jobs`.
- Login: `stario-auth`. Styles: `stario-tailwind-daisyui`. JavaScript: `stario-client`.
- Before a browser or a screenshot: `stario-browser-check`.
- `stario-api` lists every signature. Read it only for a name that the skill and the code do not show.

## Layout

```text
app/
  main.py           bootstrap: shared objects, one register line per page under `# pages`
  config.py         Config: one field with a default per setting; from_env reads it by name
  common/shell.py   page(title, body): the <html> document
  features/<page>/  urls.py (Routes, the View), views.py (render), handlers.py (the page class), data.py (SQL)
  <name>/           code with no URL; never imports features/
tests/test_<page>.py
```

- A page is one folder, named after the URL noun: `/rooms/{room_id}` → `room`. It gets one line in `LINKS` in `app/features/home/views.py`.
- A feature may import the `urls.py` and `data.py` of another feature, never its views or handlers.
- JavaScript lives in `static/js/<name>.js` as `app.<name>`, never in a Python string.

## Stario rules

- Not ASGI: no Uvicorn, FastAPI, or response objects.
- `bootstrap(app, span)` is an async generator with one `yield`. Keep `app.use("/", same_origin(), security_headers())`. `same_origin()` is the CSRF guard: add no CSRF tokens. It does not check GET, so a GET never changes state.
- A handler is `async def (c: Context, w: Writer) -> None`. It answers once: `w.html`, `w.text`, `w.empty`, `w.redirect`, or `SSE(w)`.
- `Route("GET /rooms/{room_id}")` is one method on one path; a GET route answers HEAD too. `app.add(ROUTE, handler)`; `ROUTE.href(room_id, query={...})`. No `url_for`.
- A stream loop iterates `c.alive(source)`. Background work is `c.app.create_task(coro)`. A timer loop waits on `app.shutdown`, never `asyncio.sleep`.
- No module-level state. No `os.environ` outside `config.py`. JSON goes through `stario.json`.
- A middleware with a dependency is a method of a class built in `bootstrap`: `app.use("/", session.attach)`, never a function that returns a middleware. Handlers read its state through a typed function such as `current_user(c)`, not `c.state[...]`.

## A page is a resource

- **Go somewhere** (a page, a sort, a filter): `<a href>`. The query holds the view.
- **A result only this tab needs** (search as you type): a `GET` that answers `SSE(w).patch_elements(part)`.
- **Change state**: a command, `POST`.

A page on state that cannot change while it is open is static: `w.html(render(...))`. A page on shared state is live:

```text
GET  /board        the document; its top element has data.init(at.get(BOARD_LIVE.href(), retry="always"))
GET  /board/live   the stream: send render(...), and again after each change
POST /board/...    a command
```

The stream is the only thing that sends HTML. It follows `db.watch(query)` (SQLite) or `relay.subscribe(CHANGED, latest=True)` (memory). A command never answers with HTML:

1. Read: `await read_signals(c.req)`, `c.match.params`. A plain HTML form or a file upload: `await read_form(c.req)` (`stario.forms`). A body over 10 MiB needs `max_size=`.
2. Validate: bad input gets `w.text("why", status=400)` and `return`.
3. Reply: `w.empty()`, `SSE(w).patch_signals(...)`, or `SSE(w).navigate(url)`.
4. Execute: `await db.write(...)`, or change memory, then `relay.publish(CHANGED, {})`.

## Render and signals

- `render(...)` returns the whole document from state. It does not fetch.
- The element with `data.init(...)` and `data.signals({...}, if_missing=True)` keeps its tag, `id`, and attributes in every render.
- Signals carry what the user types or picks. A leading `_` keeps a signal in the tab. One signal per field, not one per row.
- A busy form: `data.indicator("_saving")` on the `<form>`, `data.attr("disabled", "$_saving")` on its button.
- A `<dialog>` or `<details>` keeps `data.preserve_attr("open")`.

## Code shape

A page is one class in `handlers.py`. Its fields are its dependencies. A read or a write is a function in `data.py`: `list_*`, `get_*`, `add_*`, `set_*`, `remove_*`.

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

No service classes, repositories, base pages, `utils`, or helpers with one call site. Read input like this:

```python
title = str(signals.get("title", "")).strip()  # text
done = signals.get("done") is True  # bool
tile_id = c.match.params["tile_id"]  # path int: tile_id.isdecimal(), then int(tile_id)
```

## Tests

Tests run `TestClient(bootstrap, request_timeout=5)`. Each page: it loads, a command repaints the stream, bad input gets 4xx. The next SSE event is the changed HTML; two streams are two tabs. A `GET` sends signals in `params={"datastar": '{"q": "x"}'}`, a `POST` in `json=`. `tests/test_pages.py` finds and checks every page by itself.

A bug starts with a test that shows it. Run `just test -k <name>` and see it fail. Then fix, see it pass, and read `git diff`.

## Checks

Change a file with the Edit tool. Run Python as `uv run python`. Run `just check` after each change: it formats, fixes lint, checks types, runs the tests, and prints only problems. pyrefly checks each call, so trust Stario, Datastar, and litewriter.

A browser is only for client JS that holds state. No computer use. When the user watches the app, the user is the browser: say what to look at. When it does not work: `curl` their server, then a failing test (skill `stario-browser-check`).

## Cursor Cloud specific instructions

Install is `.cursor/cloud-install.sh`.

## This app

nudgethis is a frame around a live web app, full-size in an iframe, with a pill at the bottom. Two gestures: tap the pill for the sheet, hold it to draw on the app (`app.pill`). The sheet (`#sheet`) holds everything: a bottom sheet on a phone (swipe its header down to close, `app.swipe`), beside the app from 900px up (`/` opens it, Esc closes). Its header switches app (`#apps`: every app, its colour, whether its coder works, a new reply; + New app) and opens a menu (`#menu`: the app's colour, `colors` table, `POST /a/{app}/color`; the coder's model). Below: Chat or Changes (`$_view`). The chat only tells, like texting: one plain line per change in progress at the top (`.inflight`, Nudge's `title`), one dim status line while Nudge or the coder works (`.doing`, `app.frame.tick`), a short reply when done with a Details link (`app.frame.show`) into Changes, which holds the request, the result, the time it took, and Undo. One composer at the foot: the pencil draws, the microphone dictates (`app.dictate`, the browser's speech recognition), Enter sends. The pill hides while the sheet is open. Each app has its own chat, history, open changes, and seen mark (`seen.<app>`). Nudge changes the app's code; the iframe reloads when the change is live.

Nudge: OpenAI through pydantic-ai in `app/nudge/agent.py`; tools `start_change`, `undo`, `remember`. The lead owns `app/nudge/instructions.md`; each turn adds the open app, notes, and open changes. No `OPENAI_API_KEY` means a scripted fake model; tests always use it.

The coder: a Cursor Cloud Agent (`app/coder/cursor.py`, API v1) runs on the repo Yard deploys the app from (`GET /api/v1/apps/<app>`; `<NUDGE_REPO_BASE>/<app>` for an app Yard does not run) and pushes straight to `main`. The `nudge.code` task polls the run, then waits for Yard's next deploy (`app/coder/yard.py`). A change goes working → deploying → live, or dropped. Undo marks it undone and asks the same agent for a revert. No `CURSOR_API_KEY` means a fake coder; bootstrap follows runs that a restart cut off. The Coder tab of the panel picks the model and its params for each app (`coders` table, `POST /a/{app}/coder`, its own stream `coder/live`); bootstrap reads the model list from `GET /v1/models`, and `CURSOR_MODEL` is the default.

New app (`features/home`, `POST /apps`): the home page is one prompt (what to make), with whole-prompt ideas to tap. The name comes from the prompt (`slug_of`; `GET /apps/suggest` shows it, and where the app starts from, as the person types; they can edit it); a GitHub link in the prompt means start from that repo. An app nudgethis made can be removed (`POST /apps/remove`: its row, chat, changes, notes, colour, coder; not its repo or its Yard app). A task makes the repo `nudge-<name>` through Yard, copies `NUDGE_TEMPLATE` (public: one codeload tarball; private: Yard's repo token) with the name in place of `starter`, `NUDGE_PUBLIC_URL`'s origin in place of `NUDGETHIS_ORIGIN` in `static/js/nudge.js`, and no `LICENSE`, or the public GitHub repo linked in the prompt; the prompt becomes the new app's first request once it is live (`FramePage.first_request`) (one tarball from codeload, read before the repo is made) (`app/coder/github.py`; the README goes first, because an empty repo takes no blobs; text files go inside the one tree request, so the template is one call, and only binaries become blobs), creates the Yard app with a Caddy site that lets only `NUDGE_PUBLIC_URL` frame it, and waits for the first deploy. The `apps` table holds these apps; `FramePage.url_of` adds them to `NUDGE_APPS`.

Sign-in: Google (`app/oauth/google.py`, `features/auth`) for every page but `/auth` and `/static`; only `NUDGE_ALLOWED_EMAILS` get a session. Tests sign in through a mocked Google (`tests/conftest.py`).

Settings (`features/settings`, `/settings`): the builder's integrations (Nudge's provider key, address, model, effort; the Cursor key and default model; Yard's token and address, the domain, the template) and its usage (Nudge tokens per turn in the `usage` table, changes, coder time, shots, data on disk). A saved value overlays the environment's (`app/builder`: `overlay`, `Builder.apply` rebuilds the agent, Cursor, and Yard in place, no restart); secrets are sealed in the `settings` table with a key from SESSION_SECRET (`Vault`). The pages read the live parts from `Builder`.

Config (`app/config.py`, `.env.example`): required `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `NUDGE_ALLOWED_EMAILS`; optional `SESSION_SECRET` (empty: made once and kept in `<data>/session_secret`), `NUDGE_PUBLIC_URL`, `NUDGE_APPS` (`name=url,...`), `OPENAI_API_KEY`, `NUDGE_MODEL`, `NUDGE_EFFORT`, `CURSOR_API_KEY`, `YARD_URL` (default `http://yard-app-1:8000`, the `yard` podman network), `YARD_TOKEN`, `NUDGE_DOMAIN` (default: the host of `NUDGE_PUBLIC_URL`), `NUDGE_TEMPLATE` (default `Bobowski/nudge-template`), `NUDGE_REPO_BASE`, `NUDGE_FAKE_DELAY` (tests set 0). `just smoke` runs the real model.

Features: `home`, `frame` (`/a/{app}`, `live`, `say`, `undo`; the `messages`, `changes`, and `notes` tables), `shots`, `auth`. The frame stream watches `FRAME_SQL` (the app's messages plus a line on every app: phase, newest reply, colour) and patches `_rev`, the newest live change; `app.frame.rev` reloads the iframe: it posts `nudge:reload`, and an app with nudge.js reloads itself on the page it is on; with no answer the iframe loads its first page again. Client JS: `app.pill`, `app.snap`, `app.ink`, `app.frame`, `app.pod`. The snap needs `isolation: isolate` on the iframe: Element Capture sends no frames otherwise. A phone (no `getDisplayMedia`, or a coarse pointer) skips the capture: `app.ink.live` draws on a clear canvas over the live app, and `app.snap.ask` posts `nudge:snap` to the iframe, whose `nudge.js` (from nudge-template) answers with its own picture; with no answer, the marks go on plain paper, the say carries `snap: "none"`, and nudgethis marks the app (`snapless` table) and offers the fix in its chat once; while it is marked, Nudge's instructions carry the exact brief (`SNAP_FIX`: copy nudge.js and screenshot.js from the template, load both). A phone snap that gets the picture (`snap: "ok"`) clears the mark. The ink editor has icon tools, text typed in place (`.inktext`), and its own message box; `app.ink.take()` returns the marked and the clean shot. The panel sits beside the app from 900px up, and covers all but a strip of it below that. Plain CSS in `static/css/style.css` (oklch, light and dark). The controls over the app are `.sticker`s: solid paper, a 2px ink outline, a hard shadow, one accent, the app's colour (`colors` table, `POST /a/{app}/color`, `app/common/palette.py`; red by default), the same in light and dark (`--st-*`); pressed, a sticker moves into its shadow.

A framed app must not send `x-frame-options: DENY` or a `frame-ancestors` rule that excludes nudgethis.
