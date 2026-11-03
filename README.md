# nudgethis

A frame around a live web app. The app runs full-size in an iframe. Beside it is the pod: one conversation with an agent called Nudge. Snap a screenshot of the app, draw on it, say what you want, and Nudge changes the code. The frame reloads when the change is live.

Nudge is a real model (OpenAI via pydantic-ai, Responses API). The coder is a Cursor Cloud Agent: it works on the app's repo and pushes straight to `main`. Yard deploys the push. With `YARD_TOKEN`, nudgethis waits for that deploy, then the change is live and the frame reloads. "Undo" asks the same agent to push a revert. Without `CURSOR_API_KEY`, a fake coder makes a change live after `NUDGE_FAKE_DELAY`.

Every page needs a Google sign-in, and only the emails in `NUDGE_ALLOWED_EMAILS` get in. The apps that nudgethis frames are not behind this sign-in.

## Run

```bash
just dev
```

Then open http://127.0.0.1:8000 and pick an app.

## The Coder tab

Tap the pill, open the menu (⋯) in the sheet, and pick the coder. It picks the Cursor model for this app and each of its params (effort, fast, context, and so on), from Cursor's own list of models. A choice that is Max Mode says so. The next change uses it; a change that already runs keeps its model.

## New apps

The home page lists the apps and has a New app field. A name such as `plants` makes:

1. the private repo `Bobowski/nudge-plants`, through Yard;
2. its first commit, a copy of `Bobowski/nudge-template` (a `stario-create new` app) with the name in place of `starter`;
3. the Yard app `nudge-plants` on `https://plants.wrati.dev`, whose Caddy site lets only nudgethis frame it;
4. the first deploy. When it is ok, the app opens in the frame.

All of it goes through `YARD_TOKEN`: Yard creates the repo and gives a one-hour token for each repo. The Cursor GitHub app must cover all `Bobowski` repos, so that Cursor can work on a new one.

## Try it locally

1. In `.env`, set `CURSOR_API_KEY` and `NUDGE_APPS` for an app that has a repo `Bobowski/<name>`.
2. Run `just dev` and open http://127.0.0.1:8000/a/<name>.

The frame shows the live app. A change goes to `main` and to production with no review step: "Undo" is the way back.

## Config

Required, via env or `.env`. Without them nudgethis does not start:

- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` — a Google OAuth client. Its redirect URI is `<NUDGE_PUBLIC_URL>/auth/google/callback`, as in honorata.
- `SESSION_SECRET` — 32+ random characters that sign the session cookie.
- `NUDGE_ALLOWED_EMAILS` — a comma list of the Google accounts that may sign in.

Optional:

- `NUDGE_PUBLIC_URL` — the address of nudgethis, default `http://127.0.0.1:8000`. On Yard: `https://wrati.dev`. An `https` address makes the cookie secure.

- `NUDGE_APPS` — comma list of `name=url`, e.g. `kran-fundament=https://kran.bobowski.dev,stario-site=https://stario.dev`. Names match `[a-z0-9-]+`, urls are http(s). Default: `stario-site=https://stario.dev`.
- `NUDGE_FAKE_DELAY` — seconds before the fake coder marks a change ready. Default `4`.
- `OPENAI_API_KEY` — the model key. Empty means fake mode (a scripted model answers "On it.").
- `OPENAI_BASE_URL` — optional OpenAI-compatible endpoint.
- `NUDGE_MODEL` — default `gpt-6.1-terra`.
- `NUDGE_EFFORT` — `none|low|medium|high`, default `low`.
- `NUDGE_HISTORY` — messages sent to the model, default `30`.
- `NUDGE_TIMEOUT` — seconds per turn, default `60`.
- `CURSOR_API_KEY` — the Cursor key for Cloud Agents. Empty means the fake coder.
- `CURSOR_MODEL` — the default for apps that have no choice in the Coder tab. A Cursor model id, with optional params: `grok-4.7:context=256k,reasoning_effort=high,fast=false`. `GET https://api.cursor.com/v1/models` lists the ids and params. Empty means Cursor's Auto. A model without params runs its default variant, which can be Max Mode.
- `NUDGE_REPO_BASE` — the repo of an app is `<base>/<name>`. Default `https://github.com/Bobowski`.
- `NUDGE_DOMAIN` — new apps live on `<name>.<domain>`, default `wrati.dev`. `NUDGE_TEMPLATE` — the template repo, default `https://github.com/Bobowski/nudge-template`.
- `YARD_URL` — default `http://yard-app-1:8000`, Yard's container on the `yard` podman network: an app on the Yard VM cannot reach the public address. On a laptop, set `https://yard.bobowski.dev`. `YARD_TOKEN` — a Yard token (`yard token new`). Without it, a change is live when the run ends, not when the deploy ends.
- `PROJECT_DATA_DIR` — data directory (`nudgethis.sqlite3`, `shots/`). Default `./data`.

`just smoke` runs three turns against the real model (needs `OPENAI_API_KEY` in `.env`). The system instructions live in `app/nudge/instructions.md` — the lead owns that text.

The framed app runs in an iframe, so it must not send `x-frame-options: DENY` or a `frame-ancestors` rule that excludes nudgethis.

## Check

```bash
just check
```
