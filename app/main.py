import asyncio

from httpx import AsyncClient
from litewriter import LiteWriter
from stario import App, Span, serve
from stario.http import same_origin, security_headers

from app.assets import ASSETS
from app.coder.cursor import Cursor
from app.coder.github import GitHub
from app.config import Config
from app.features.frame.data import schema
from app.features.frame.handlers import FramePage
from app.features.home.handlers import HomePage
from app.features.shots.handlers import ShotsPage
from app.nudge.agent import build_agent, load_instructions


async def bootstrap(app: App, span: Span):
    config = Config.from_env()
    app.use("/", same_origin(), security_headers())
    agent = build_agent(config)
    model_name = config.model if config.openai_api_key.strip() else "fake"
    coder = "cursor" if config.cursor_api_key else "fake"
    span.attrs({**await ASSETS.attach(app), "nudge.model": model_name, "nudge.coder": coder})
    instructions = load_instructions()
    async with (
        LiteWriter(config.db_path, schema=schema, claim=30) as db,
        agent,
        AsyncClient(timeout=30) as http,
    ):
        cursor = (
            Cursor(http, config.cursor_api_key, config.cursor_model) if coder == "cursor" else None
        )
        frame = FramePage(
            db,
            config,
            agent,
            model_name,
            instructions,
            http,
            cursor,
            GitHub(http, config.github_token),
        )
        HomePage(config.apps).register(app)
        frame.register(app)
        frame.resume(app, span)
        ShotsPage(config.shots_dir).register(app)
        yield


if __name__ == "__main__":
    asyncio.run(serve(bootstrap))
