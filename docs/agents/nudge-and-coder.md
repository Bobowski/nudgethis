# Nudge and the coder

Moved from AGENTS.md `## This app`. Read when working on the Nudge agent, its tools and instructions, or the Cursor coder, change phases, undo, and the Yard deploy wait.

Nudge: OpenAI through pydantic-ai in `app/nudge/agent.py`; tools `start_change`, `undo`, `remember`. The lead owns `app/nudge/instructions.md`; each turn adds the open app, notes, and open changes. No `OPENAI_API_KEY` means a scripted fake model; tests always use it.

The coder: a Cursor Cloud Agent (`app/coder/cursor.py`, API v1) runs on the repo Yard deploys the app from (`GET /api/v1/apps/<app>`; `<NUDGE_REPO_BASE>/<app>` for an app Yard does not run) and pushes straight to `main`. The `nudge.code` task polls the run, then waits for Yard's next deploy (`app/coder/yard.py`). A change goes working → deploying → live, or dropped. Undo marks it undone and asks the same agent for a revert. No `CURSOR_API_KEY` means a fake coder; bootstrap follows runs that a restart cut off. The Coder tab of the panel picks the model and its params for each app (`coders` table, `POST /a/{app}/coder`, its own stream `coder/live`); bootstrap reads the model list from `GET /v1/models`, and `CURSOR_MODEL` is the default.
