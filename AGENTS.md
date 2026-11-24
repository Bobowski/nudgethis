<!-- BEGIN stario-create -->
# Stario app guide

A Stario app is Python 3.14: the server renders `h.*` tags, Datastar (`data.*`, `at.*`) sends
commands and keeps pages live over SSE, litewriter keeps SQLite (stario 5.9, litewriter 0.3).
The names are here or in a skill: never read `site-packages`.

## The loop

1. Start in one command with the kits the task needs (a kit replaces only files still equal to
   the scaffold): `uvx stario-create@latest new app --db && cd app && uvx stario-create@latest add auth --password`.
   Kits: `add auth --password` (email and password), `add auth` (Google, GitHub), `add tailwind`
   (DaisyUI, no Node). `new` prints the files you change: do not open them.
2. Read the spec and tests, many files per command.
3. Write `app/urls.py` (every route), `app/data.py` (tables, rows, SQL), `app/layout.py`
   (shared markup), `app/pages/<area>.py` (a module per area), then `app/main.py` (one
   register line per page class). Import what a file uses; do not tidy imports or unused names
   by hand: `check` sorts and drops them.
4. `uvx stario-create@latest check` (lint, types, tests): each problem names its fix. Repeat
   until `check: ok`.
5. See a page with no server: `uvx stario-create@latest request GET /bookmarks`. Each call starts
   on an empty database, so chain steps: `request POST /signup -d email=a@b.co -d password=12345678
   -d username=a GET /bookmarks` (`-d` a form field, `-j JSON` a Datastar action, `-s JSON` signals
   on a GET).
6. An acceptance suite (`npm test`): run it in the foreground with the Bash tool's timeout
   (600000), never in the background. When it passes, stop: no screenshots, no own tests. No
   suite: write TestClient tests (skill `stario-tests`).

Shell: macOS has no `timeout`; `sed -i ''`. Stop a server of an earlier call by its port:
`lsof -ti tcp:8000 | xargs kill`, never `pkill -f` (it stops other apps). The app listens on
127.0.0.1:8000; a host's `PORT`: `STARIO_HOST=0.0.0.0 STARIO_PORT=$PORT`. `Config` already
reads `DATABASE_PATH`.

Changing an app that holds data: read `app/urls.py`, `app/data.py` and the pages to change first.
A new column on a table with rows: skill `stario-migrate` (never drop and create). A new table
is one more `CREATE TABLE IF NOT EXISTS`.

## A page: list, search, paging, live stream, a command

```python
# app/urls.py (add)
BOOKMARKS = Route("GET /bookmarks")
BOOKMARKS_LIVE = Route("GET /bookmarks/live")
ADD_BOOKMARK = Route("POST /bookmarks")
```

```python
# app/data.py
from dataclasses import dataclass

from litewriter import LiteWriter, Tx

PER_PAGE = 20


def schema(tx: Tx) -> None:
    """Runs at each start: every statement is IF NOT EXISTS."""
    tx.execute(
        "CREATE TABLE IF NOT EXISTS bookmarks (id INTEGER PRIMARY KEY,"
        " title TEXT NOT NULL, url TEXT NOT NULL, created TEXT NOT NULL DEFAULT (datetime('now')))"
    )


@dataclass(frozen=True, slots=True)
class Bookmark:
    id: int
    title: str
    url: str


# A stream repaints when this result changes: it changes with every write the page shows.
CHANGES = "SELECT count(*), max(id) FROM bookmarks"
_MATCH = "instr(lower(title), lower(:q)) > 0"


def list_bookmarks(db: LiteWriter, q: str, page: int) -> tuple[list[Bookmark], int]:
    sql = f"SELECT id, title, url FROM bookmarks WHERE {_MATCH} ORDER BY id DESC"
    rows = db.query(
        f"{sql} LIMIT :n OFFSET :skip", Bookmark, q=q, n=PER_PAGE, skip=(page - 1) * PER_PAGE
    )
    total: int = db.value(f"SELECT count(*) FROM bookmarks WHERE {_MATCH}", q=q)
    return rows, total


def add_bookmark(tx: Tx, title: str, url: str) -> int:
    return tx.value(
        "INSERT INTO bookmarks (title, url) VALUES (:t, :u) RETURNING id", t=title, u=url
    )
```

```python
# app/pages/bookmarks.py
from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Writer, classes, h
from stario.datastar import SSE, at, data, read_signals
from stario.markup import HtmlElement

from app.data import CHANGES, PER_PAGE, Bookmark, add_bookmark, list_bookmarks
from app.layout import page
from app.urls import ADD_BOOKMARK, BOOKMARKS, BOOKMARKS_LIVE


@dataclass(frozen=True, slots=True)
class BookmarksPage:
    db: LiteWriter

    def register(self, app: App) -> None:
        app.add(BOOKMARKS, self.show)
        app.add(BOOKMARKS_LIVE, self.live)
        app.add(ADD_BOOKMARK, self.add)

    def listing(self, c: Context) -> HtmlElement:
        """The live part, from the URL query: the page and the stream send it."""
        q, raw = c.req.query.get("q", "").strip(), c.req.query.get("page", "1")
        n = int(raw) if raw.isdecimal() and raw != "0" else 1
        return render_list(q, n, *list_bookmarks(self.db, q, n))

    async def show(self, c: Context, w: Writer) -> None:
        w.html(render(c.req.query.get("q", ""), self.listing(c)))

    async def live(self, c: Context, w: Writer) -> None:
        sse = SSE(w)
        async with self.db.watch(CHANGES) as changes:
            async for _ in c.alive(changes):  # now, then after each change, until the tab closes
                sse.patch_elements(self.listing(c))

    async def add(self, c: Context, w: Writer) -> None:
        signals = await read_signals(c.req)
        title, url = str(signals.get("title", "")).strip(), str(signals.get("url", "")).strip()
        if not title or not url.startswith(("https://", "http://")):
            SSE(w).patch_signals({"_error": "a title and an http(s) URL are required"})
            return
        await self.db.write(add_bookmark, title, url)
        SSE(w).patch_signals({"title": "", "url": "", "_error": ""})  # the streams repaint


def render_list(q: str, n: int, rows: list[Bookmark], total: int) -> HtmlElement:
    pages = range(1, (total + PER_PAGE - 1) // PER_PAGE + 1)
    return h.Section(
        {"id": "bookmarks"},
        data.init(at.get(BOOKMARKS_LIVE.href(query={"q": q or None, "page": n}))),
        h.Ul(*[h.Li(h.A({"href": b.url}, b.title)) for b in rows]),
        None if rows else h.P("No bookmarks yet."),
        h.Nav(*[
            h.A(
                classes({"active": p == n}),
                {"href": BOOKMARKS.href(query={"q": q or None, "page": p})},
                str(p),
            )
            for p in pages
        ]),
    )


def render(q: str, listing: HtmlElement) -> HtmlElement:
    return page(
        "Bookmarks",
        h.Main(
            {"id": "main"},
            data.signals({"title": "", "url": "", "_error": ""}),
            h.Form(
                {"method": "get", "action": BOOKMARKS.href()},
                h.Input({"type": "search", "name": "q", "value": q}),
            ),
            h.Form(
                data.on("submit", at.post(ADD_BOOKMARK.href()), prevent=True),
                h.Input({"placeholder": "Title"}, data.bind("title")),
                h.Input({"placeholder": "https://..."}, data.bind("url")),
                h.Button({"type": "submit"}, "Add"),
                h.P({"role": "alert"}, data.show("$_error"), data.text("$_error")),
            ),
            listing,
        ),
    )
```

`app/main.py`: import `BookmarksPage`; in bootstrap, `BookmarksPage(db).register(app)`. Link the
page in `LINKS` of `app/pages/home.py`. That file owns `GET /`: a task with its own home page
rewrites it (a second `GET /` raises).

## Names

- Every HTML tag is `h.<Name>`, one capital (`h.Tbody`). Attribute dicts, `classes(...)` (never
  a dict value) and `data.*` come before the children (text, tags, `None`, `*list`). A list of
  nodes in a variable is `list[HtmlElement]`;
  a `list[str]` in `data.signals` is spread, `{"tags": [*tags]}`.
  `SafeString(html)` is for trusted HTML only.
- Request: `c.req.query.get("q", "")`, `.getlist("tag")`, `c.match.params["slug"]` (a `str`),
  `c.req.cookies.get("k")`, `c.req.headers.get("k")`.
- Answer once: `w.html(el)`, `w.text("not found", status=404)`, `w.json(v)`, `w.empty()`,
  `w.redirect(url, 303)`, `w.respond(body, b"text/csv")`. A Datastar action answers through
  `SSE(w)`: `.patch_signals`, `.patch_elements(el)` (morphs the element with that id;
  `mode="append", selector="#list"` adds), `.remove("#id")`, `.navigate(url)`; or `w.empty()`.
- Plain form: `h.Form({"method": "post", "action": R.href()}, ...)`; `form = await read_form(c.req)`
  (`stario.forms`), `form.get("title", "")`, `form.getlist("tag")`; then `w.redirect(url, 303)`, or
  the page again with its errors, `w.html(..., status=422)`.
- Routes: `Route("GET /tags/{tag}")`, `{path...}` takes the rest; `R.href("x", query={"page": 2})`
  drops `None` values. `app.use("/admin", middleware)`; `app.not_found("/", handler)`.
- A row's button: `data.on("click", at.post(DONE.href(item.id)))`; a missing or another user's
  row answers 404. Search as you type: an input with `data.bind("q")` and `data.on("input",
  at.get(RESULTS.href()), debounce="300ms")`; that handler reads `read_signals` and patches.
- What only this tab needs before a submit (tags being typed, an open panel) is a signal set in
  an expression, `$tags = [...$tags, $tag]`, no server call; the submit sends it.
- Data: `db.one(sql, Row, **p)` is a row or None; `db.value` raises `QueryError` on no row;
  `db.watch(sql, Row, **p)`. In a write: `tx.execute`, `tx.value`, `tx.one`, `tx.query`. A taken unique value raises `apsw.ConstraintError`.
- Static: `ASSETS.href("css/x.css")` renames to `x.<hash>.css`. A URL that must keep its file name
  (a default avatar): `MEDIA = Files(ASSETS.directory / "media", "/media")` in
  `app/layout.py`, `await MEDIA.attach(app)` in bootstrap, `MEDIA.href("avatar.svg")`.
- `set_cookie(w, "k", value, max_age=86400)` (`stario.cookies`). `from stario.json import dumps,
  loads`; `loads` returns `object`: `cast(list[str], loads(s))`.
- A setting is one field with a default in `Config` (`site_url: str = ""` reads `SITE_URL`;
  no `os.environ`), passed from bootstrap to page classes. State lives in objects, not modules.

## Rules that bite

- `page()` in `app/layout.py` is `@baked`: it runs once at import with placeholders, so an `if`,
  `==`, f-string or loop on its parameters raises. A per-request part (a signed-in header) is a
  new parameter that every caller passes.
- A write function (`fn(tx, ...)`) makes no network call and hashes no password: do that first,
  slow work through `await asyncio.to_thread(...)`.
- `watch` wakes on a commit to a table it reads and yields only when its result changes. Watch
  something every shown edit changes: `max(updated)`, the edited columns, a count per table.
- `ORDER BY` takes no parameter: pick the SQL text from a dict, `SORTS = {"new": "id DESC"}`.
- A Datastar action follows no redirect: `SSE(w).navigate(url)`. A duration is a string, `"300ms"`.
- Do not read or edit the generated `tests/test_pages.py`, `_pagecheck.py`, `_lint.py`,
  `test_js.py`: their failures name the fix.

## Accounts

`add auth --password` writes `app/auth/` (users table, `Session`, hashes) and `app/pages/login.py`
(plain forms: `/login`, `/signup`, `POST /logout`) with `tests/test_login.py`. Change paths in
`app/urls.py`, labels and markup freely; keep the route names and the fields `email`, `password`,
`username`, and the tests hold. User columns go in `CREATE TABLE users` (`app/auth/data.py`).
Protect a prefix in `app/main.py`: `app.use("/settings", session.require)`. In a handler,
`current_user(c)` is the user id or None; `signed_in_user(c)` behind `require`.

## Skills

Load one only when a task needs it: `stario-tests` (TestClient tests, when no acceptance suite),
`stario-migrate` (tables that already hold rows), `stario-outside-api` (another service over HTTP),
`stario-js` (any JavaScript file), `stario-background` (state in memory, slow jobs, timers),
`stario-accounts` (past the kit: Google setup, roles, tokens), `stario-reference` (a name this
file lacks or pyrefly rejects).

<!-- END stario-create -->

## This app

nudgethis is a frame around a live web app, full-size in an iframe, with a pill at the bottom. Two gestures: tap the pill for the sheet, hold it to draw on the app (`app.pill`). The sheet (`#sheet`) holds everything: a bottom sheet on a phone (swipe its header down to close, `app.swipe`), beside the app from 900px up (`/` opens it, Esc closes). Its header switches app (`#apps`: every app, its colour, whether its coder works, a new reply; + New app) and opens a menu (`#menu`: the app's colour, `colors` table, `POST /a/{app}/color`; the coder's model). Below: Chat or Changes (`$_view`). The chat only tells, like texting: one plain line per change in progress at the top (`.inflight`, Nudge's `title`), one dim status line while Nudge or the coder works (`.doing`, `app.frame.tick`), a short reply when done with a Details link (`app.frame.show`) into Changes, which holds the request, the result, the time it took, and Undo. One composer at the foot: the pencil draws, the microphone dictates (`app.dictate`, the browser's speech recognition), Enter sends. The pill hides while the sheet is open. Each app has its own chat, history, open changes, and seen mark (`seen.<app>`). Nudge changes the app's code; the iframe reloads when the change is live.

Nudge: OpenAI through pydantic-ai in `app/nudge/agent.py`; tools `start_change`, `undo`, `remember`. The lead owns `app/nudge/instructions.md`; each turn adds the open app, notes, and open changes. No `OPENAI_API_KEY` means a scripted fake model; tests always use it.

The coder: a Cursor Cloud Agent (`app/coder/cursor.py`, API v1) runs on the repo Yard deploys the app from (`GET /api/v1/apps/<app>`; `<NUDGE_REPO_BASE>/<app>` for an app Yard does not run) and pushes straight to `main`. The `nudge.code` task polls the run, then waits for Yard's next deploy (`app/coder/yard.py`). A change goes working → deploying → live, or dropped. Undo marks it undone and asks the same agent for a revert. No `CURSOR_API_KEY` means a fake coder; bootstrap follows runs that a restart cut off. The Coder tab of the panel picks the model and its params for each app (`coders` table, `POST /a/{app}/coder`, its own stream `coder/live`); bootstrap reads the model list from `GET /v1/models`, and `CURSOR_MODEL` is the default.

New app (`features/home`, `POST /apps`): the home page is one prompt (what to make), with whole-prompt ideas to tap. The name comes from the prompt (`slug_of`; `GET /apps/suggest` shows it, and where the app starts from, as the person types; they can edit it); a GitHub link in the prompt means start from that repo. An app nudgethis made can be removed (`POST /apps/remove`: its row, chat, changes, notes, colour, coder; not its repo or its Yard app). A task makes the repo `nudge-<name>` through Yard, copies `NUDGE_TEMPLATE` (public: one codeload tarball; private: Yard's repo token) with the name in place of `starter`, `NUDGE_PUBLIC_URL`'s origin in place of `NUDGETHIS_ORIGIN` in `static/js/nudge.js`, and no `LICENSE`, or the public GitHub repo linked in the prompt; the prompt becomes the new app's first request once it is live (`FramePage.first_request`) (one tarball from codeload, read before the repo is made) (`app/coder/github.py`; the README goes first, because an empty repo takes no blobs; text files go inside the one tree request, so the template is one call, and only binaries become blobs), creates the Yard app with a Caddy site that lets only `NUDGE_PUBLIC_URL` frame it, and waits for the first deploy. The `apps` table holds these apps; `FramePage.url_of` adds them to `NUDGE_APPS`.

Sign-in: the stario-auth kit. Google (`app/common/providers/`, `features/auth`) guards every page but `/auth` and `/static`. `GET /auth` shows the button, `POST /auth/google` starts the flow (state, nonce, PKCE in the signed `login` cookie), and Google comes back to `/auth/google/callback`, the redirect URI registered at Google; keep that path. Only a verified email in `NUDGE_ALLOWED_EMAILS` gets a session. A user is `identities(issuer, subject)` to `users.id`, and the session holds that id. The data is not per user: every allowed person sees every app. Tests sign in through `FakeProviders` (`tests/conftest.py`).

Settings (`features/settings`, `/settings`): the builder's integrations (Nudge's provider key, address, model, effort; the Cursor key and default model; Yard's token and address, the domain, the template) and its usage (Nudge tokens per turn in the `usage` table, changes, coder time, shots, data on disk). A saved value overlays the environment's (`app/builder`: `overlay`, `Builder.apply` rebuilds the agent, Cursor, and Yard in place, no restart); secrets are sealed in the `settings` table with a key from SESSION_SECRET (`Vault`). The pages read the live parts from `Builder`.

Config (`app/config.py`, `.env.example`): required `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `NUDGE_ALLOWED_EMAILS`; optional `SESSION_SECRET` (empty: made once and kept in `<data>/session_secret`), `NUDGE_PUBLIC_URL`, `NUDGE_APPS` (`name=url,...`), `OPENAI_API_KEY`, `NUDGE_MODEL`, `NUDGE_EFFORT`, `CURSOR_API_KEY`, `YARD_URL` (default `http://yard-app-1:8000`, the `yard` podman network), `YARD_TOKEN`, `NUDGE_DOMAIN` (default: the host of `NUDGE_PUBLIC_URL`), `NUDGE_TEMPLATE` (default `Bobowski/nudge-template`), `NUDGE_REPO_BASE`, `NUDGE_FAKE_DELAY` (tests set 0). `just smoke` runs the real model.

Features: `home`, `frame` (`/a/{app}`, `live`, `say`, `undo`; the `messages`, `changes`, and `notes` tables), `shots`, `auth`. The frame stream watches `FRAME_SQL` (the app's messages plus a line on every app: phase, newest reply, colour) and patches `_rev`, the newest live change; `app.frame.rev` reloads the iframe: it posts `nudge:reload`, and an app with nudge.js reloads itself on the page it is on; with no answer the iframe loads its first page again. Client JS: `app.pill`, `app.snap`, `app.ink`, `app.frame`, `app.pod`. The snap needs `isolation: isolate` on the iframe: Element Capture sends no frames otherwise. A phone (no `getDisplayMedia`, or a coarse pointer) skips the capture: `app.ink.live` draws on a clear canvas over the live app, and `app.snap.ask` posts `nudge:snap` to the iframe, whose `nudge.js` (from nudge-template) answers with its own picture; with no answer, the marks go on plain paper, the say carries `snap: "none"`, and nudgethis marks the app (`snapless` table) and offers the fix in its chat once; while it is marked, Nudge's instructions carry the exact brief (`SNAP_FIX`: copy nudge.js and screenshot.js from the template, load both). A phone snap that gets the picture (`snap: "ok"`) clears the mark. The ink editor has icon tools, text typed in place (`.inktext`), and its own message box; `app.ink.take()` returns the marked and the clean shot. The panel sits beside the app from 900px up, and covers all but a strip of it below that. Plain CSS in `static/css/style.css` (oklch, light and dark). The controls over the app are `.sticker`s: solid paper, a 2px ink outline, a hard shadow, one accent, the app's colour (`colors` table, `POST /a/{app}/color`, `app/common/palette.py`; red by default), the same in light and dark (`--st-*`); pressed, a sticker moves into its shadow.

A framed app must not send `x-frame-options: DENY` or a `frame-ancestors` rule that excludes nudgethis.
