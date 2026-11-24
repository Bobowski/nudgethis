# Config

Moved from AGENTS.md `## This app`. Read when adding or changing an environment variable or its default.

Config (`app/config.py`, `.env.example`): required `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `NUDGE_ALLOWED_EMAILS`; optional `SESSION_SECRET` (empty: made once and kept in `<data>/session_secret`), `NUDGE_PUBLIC_URL`, `NUDGE_APPS` (`name=url,...`), `OPENAI_API_KEY`, `NUDGE_MODEL`, `NUDGE_EFFORT`, `CURSOR_API_KEY`, `YARD_URL` (default `http://yard-app-1:8000`, the `yard` podman network), `YARD_TOKEN`, `NUDGE_DOMAIN` (default: the host of `NUDGE_PUBLIC_URL`), `NUDGE_TEMPLATE` (default `Bobowski/nudge-template`), `NUDGE_REPO_BASE`, `NUDGE_FAKE_DELAY` (tests set 0). `just smoke` runs the real model.
