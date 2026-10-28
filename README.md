# nudgethis

A frame around a live web app. The app runs full-size in an iframe. Beside it is the pod: one conversation with an agent called Nudge. Snap a screenshot of the app, draw on it, say what you want, and Nudge changes the code; "Ship" reloads the frame.

In this phase Nudge is fake and scripted — no LLM, no Cursor, no GitHub. Local only, no auth.

## Run

```bash
just dev
```

Then open http://127.0.0.1:8000 and pick an app.

## Config

All optional, via env or `.env`:

- `NUDGE_APPS` — comma list of `name=url`, e.g. `kran-fundament=https://kran.bobowski.dev,stario-site=https://stario.dev`. Names match `[a-z0-9-]+`, urls are http(s). Default: `stario-site=https://stario.dev`.
- `NUDGE_FAKE_DELAY` — seconds before the fake Nudge answers "Done." Default `4`.
- `PROJECT_DATA_DIR` — data directory (`nudgethis.sqlite3`, `shots/`). Default `./data`.

The framed app runs in an iframe, so it must not send `x-frame-options: DENY` or a `frame-ancestors` rule that excludes nudgethis.

## Check

```bash
just check
```
