# nudgethis

A frame around a live web app. The app runs full-size in an iframe. Beside it is the pod: one conversation with an agent called Nudge. Snap a screenshot of the app, draw on it, say what you want, and Nudge changes the code; "Ship" reloads the frame.

Nudge is a real model (OpenAI via pydantic-ai, Responses API). The coder sub-agent is still fake — a change is marked `ready` after `NUDGE_FAKE_DELAY`. Local only, no auth.

## Run

```bash
just dev
```

Then open http://127.0.0.1:8000 and pick an app.

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
- `PROJECT_DATA_DIR` — data directory (`nudgethis.sqlite3`, `shots/`). Default `./data`.

`just smoke` runs three turns against the real model (needs `OPENAI_API_KEY` in `.env`). The system instructions live in `app/nudge/instructions.md` — the lead owns that text.

The framed app runs in an iframe, so it must not send `x-frame-options: DENY` or a `frame-ancestors` rule that excludes nudgethis.

## Check

```bash
just check
```
