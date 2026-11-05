import asyncio

from httpx import AsyncClient
from litewriter import LiteWriter, Tx
from stario import App, Span, serve
from stario.cookies import SignedCookie
from stario.http import same_origin, security_headers

from app.assets import ASSETS
from app.builder import Builder, Vault
from app.common.session import Session
from app.config import Config
from app.features.auth.handlers import AuthPage
from app.features.auth.urls import AUTH_GOOGLE
from app.features.frame import data as frame_data
from app.features.frame.handlers import FramePage
from app.features.home import data as home_data
from app.features.home.handlers import HomePage
from app.features.settings import data as settings_data
from app.features.settings.handlers import SettingsPage
from app.features.shots.handlers import ShotsPage
from app.nudge.agent import load_instructions
from app.oauth.google import Google


def schema(tx: Tx) -> None:
    frame_data.schema(tx)
    home_data.schema(tx)
    settings_data.schema(tx)


async def bootstrap(app: App, span: Span):
    config = Config.from_env()
    # __Host- keeps a subdomain from setting the cookie; it needs Secure, so a
    # plain-HTTP NUDGE_PUBLIC_URL (a laptop) gets a cookie without the prefix.
    https = config.public_url.startswith("https://")
    cookie = SignedCookie(
        "__Host-session" if https else "session", keys=[config.session_secret], secure=https
    )
    session = Session(cookie, AUTH_GOOGLE.href())
    app.use("/", same_origin(), security_headers(), session.attach)
    # Everything but /auth and /static is for the people in NUDGE_ALLOWED_EMAILS.
    signed_in = session.require
    app.use("/a", signed_in)
    app.use("/shots", signed_in)
    app.use("/settings", signed_in)
    span.attrs(await ASSETS.attach(app))
    instructions = load_instructions()
    # Tokens saved on the settings page are sealed with a key from SESSION_SECRET.
    vault = Vault(config.session_secret)
    async with (
        LiteWriter(config.db_path, schema=schema, claim=30) as db,
        AsyncClient(timeout=30) as http,
    ):
        builder = Builder(config, http)
        await builder.apply(settings_data.list_settings(db, vault))
        span.attrs(
            {
                "nudge.model": builder.model_name,
                "nudge.coder": "cursor" if builder.cursor else "fake",
                "cursor.models_error": builder.models_error,
            }
        )
        frame = FramePage(db, builder, instructions)
        HomePage(db, builder, http, signed_in, frame.first_request).register(app)
        SettingsPage(db, builder, vault).register(app)
        google = Google(http, config.google_client_id, config.google_client_secret)
        AuthPage(session, google, config.allowed_emails, config.public_url).register(app)
        frame.register(app)
        frame.resume(app, span)
        ShotsPage(config.shots_dir).register(app)
        try:
            yield
        finally:
            await builder.close()


if __name__ == "__main__":
    asyncio.run(serve(bootstrap))
