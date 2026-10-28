import asyncio

from litewriter import LiteWriter
from stario import App, Span, serve
from stario.http import same_origin, security_headers

from app.assets import ASSETS
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
    span.attrs({**await ASSETS.attach(app), "nudge.model": model_name})
    instructions = load_instructions()
    async with LiteWriter(config.db_path, schema=schema, claim=30) as db, agent:
        HomePage(config.apps).register(app)
        FramePage(db, config, agent, model_name, instructions).register(app)
        ShotsPage(config.shots_dir).register(app)
        yield


if __name__ == "__main__":
    asyncio.run(serve(bootstrap))
