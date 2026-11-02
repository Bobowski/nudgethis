# nudgethis

A frame around a live web app. The app runs full-size in an iframe. Beside it is the pod: one conversation with an agent called Nudge. Snap a screenshot of the app, draw on it, say what you want, and Nudge changes the code; "Ship" reloads the frame.

Nudge is a real model (OpenAI via pydantic-ai, Responses API). The coder is a Cursor Cloud Agent: it works on the app's repo and opens a pull request. "Ship" merges that pull request; "Not yet" closes it. Without `CURSOR_API_KEY`, a fake coder marks a change ready after `NUDGE_FAKE_DELAY`. Local only, no auth.

## Run

```bash
just dev
```

Then open http://127.0.0.1:8000 and pick an app.

## The local loop

You can watch a whole change on this machine. Yard is not needed.

1. Run the framed app with reload, on its own port: `cd ../honorata && STARIO_PORT=8001 just dev`.
2. In `.env` here, set `NUDGE_APPS=honorata=http://127.0.0.1:8001`, `NUDGE_CHECKOUTS=..` (the folder that holds the clone `honorata/`), and `CURSOR_API_KEY`.
3. Run `just dev` here and open http://127.0.0.1:8000/a/honorata.

A Cursor agent changes the code in the cloud and opens a pull request. When it is ready, nudgethis switches the clone to the agent's branch, the app reloads, and the frame shows the change. "Ship" merges the pull request, then the clone goes back to `main` and pulls. "Not yet" closes the pull request and goes back to `main`. A clone with uncommitted changes stays where it is, and Nudge says so.

A merge to `main` also deploys the app through Yard.

## Config

All optional, via env or `.env`:

- `NUDGE_APPS` — comma list of `name=url`, e.g. `kran-fundament=https://kran.bobowski.dev,stario-site=https://stario.dev`. Names match `[a-z0-9-]+`, urls are http(s). Default: `stario-site=https://stario.dev`.
- `NUDGE_FAKE_DELAY` — seconds before the fake coder marks a change ready. Default `4`.
- `OPENAI_API_KEY` — the model key. Empty means fake mode (a scripted model answers "On it.").
- `OPENAI_BASE_URL` — optional OpenAI-compatible endpoint.
- `NUDGE_MODEL` — default `gpt-6.1-terra`.
- `NUDGE_EFFORT` — `none|low|medium|high`, default `low`.
- `NUDGE_HISTORY` — messages sent to the model, default `30`.
- `NUDGE_TIMEOUT` — seconds per turn, default `60`.
- `CURSOR_API_KEY` — the Cursor key for Cloud Agents. Empty means the fake coder.
- `CURSOR_MODEL` — optional Cursor model id. Empty means Cursor's default.
- `NUDGE_REPO_BASE` — the repo of an app is `<base>/<name>`. Default `https://github.com/Bobowski`.
- `GITHUB_TOKEN` — merges and closes the pull requests. `just dev` takes `gh auth token` when it is not set.
- `NUDGE_CHECKOUTS` — a folder with a local clone of each app (`<folder>/<name>`). Empty means no local preview.
- `PROJECT_DATA_DIR` — data directory (`nudgethis.sqlite3`, `shots/`). Default `./data`.

`just smoke` runs three turns against the real model (needs `OPENAI_API_KEY` in `.env`). The system instructions live in `app/nudge/instructions.md` — the lead owns that text.

The framed app runs in an iframe, so it must not send `x-frame-options: DENY` or a `frame-ancestors` rule that excludes nudgethis.

## Check

```bash
just check
```
