# Sign-in and settings

Moved from AGENTS.md `## This app`. Read when working on Google sign-in, users and sessions, or the settings page, its overlay and sealed secrets.

Sign-in: the stario-auth kit. Google (`app/common/providers/`, `features/auth`) guards every page but `/auth` and `/static`. `GET /auth` shows the button, `POST /auth/google` starts the flow (state, nonce, PKCE in the signed `login` cookie), and Google comes back to `/auth/google/callback`, the redirect URI registered at Google; keep that path. Only a verified email in `NUDGE_ALLOWED_EMAILS` gets a session. A user is `identities(issuer, subject)` to `users.id`, and the session holds that id. The data is not per user: every allowed person sees every app. Tests sign in through `FakeProviders` (`tests/conftest.py`).

Settings (`features/settings`, `/settings`): the builder's integrations (Nudge's provider key, address, model, effort; the Cursor key and default model; Yard's token and address, the domain, the template) and its usage (Nudge tokens per turn in the `usage` table, changes, coder time, shots, data on disk). A saved value overlays the environment's (`app/builder`: `overlay`, `Builder.apply` rebuilds the agent, Cursor, and Yard in place, no restart); secrets are sealed in the `settings` table with a key from SESSION_SECRET (`Vault`). The pages read the live parts from `Builder`.
