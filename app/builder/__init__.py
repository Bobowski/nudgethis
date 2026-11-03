"""The builder's live parts: the config with the person's settings on top, Nudge's
agent, the coder (Cursor), and Yard. Settings change them without a restart."""

import base64
import dataclasses
import hashlib
from contextlib import AsyncExitStack
from dataclasses import dataclass, field

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic_ai import Agent

from app.coder import CoderError
from app.coder.cursor import Cursor, Model
from app.coder.yard import Yard
from app.config import EFFORTS, Config, parse_cursor_model
from app.nudge.agent import TurnDeps, build_agent

# What the settings page can change, and which of them are secrets.
KEYS = (
    "openai_api_key",
    "openai_base_url",
    "model",
    "effort",
    "cursor_api_key",
    "cursor_model",
    "yard_url",
    "yard_token",
    "domain",
    "template",
)
SECRETS = frozenset({"openai_api_key", "cursor_api_key", "yard_token"})


class Vault:
    """Secrets at rest, sealed with a key from SESSION_SECRET: the data directory
    alone does not give them away."""

    def __init__(self, secret: bytes) -> None:
        key = hashlib.sha256(b"nudgethis settings\0" + secret).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(key))

    def seal(self, text: str) -> str:
        return self.fernet.encrypt(text.encode()).decode()

    def open(self, sealed: str) -> str | None:
        """The secret, or None when SESSION_SECRET changed since it was sealed."""
        try:
            return self.fernet.decrypt(sealed.encode()).decode()
        except InvalidToken:
            return None


def check(key: str, value: str) -> str | None:
    """Why a value cannot be used, or None."""
    if key == "effort" and value not in EFFORTS:
        return f"Effort is one of {', '.join(EFFORTS)}."
    if key in ("openai_base_url", "yard_url") and value and not value.startswith("http"):
        return "An address starts with http:// or https://."
    if key == "template" and value and not value.startswith("https://github.com/"):
        return "The template is a https://github.com/owner/name repo."
    if key == "cursor_model":
        try:
            parse_cursor_model(value)
        except ValueError:
            return "A coder model is an id, or id:key=value,key=value."
    if key == "domain" and value and ("/" in value or " " in value):
        return "A domain is a name like wrati.dev."
    return None


def overlay(base: Config, settings: dict[str, str]) -> Config:
    """The environment's config with each setting the person saved on top."""
    changes: dict[str, object] = {}
    for key, value in settings.items():
        if key not in KEYS:
            continue
        if key == "cursor_model":
            changes["cursor_model"], changes["cursor_params"] = parse_cursor_model(value)
        elif key == "openai_base_url":
            changes[key] = value or None
        elif key in ("yard_url", "template"):
            changes[key] = value.rstrip("/")
        else:
            changes[key] = value
    return dataclasses.replace(base, **changes)


@dataclass(slots=True)
class Builder:
    base: Config
    http: httpx.AsyncClient
    config: Config = field(init=False)
    agent: Agent[TurnDeps, str] = field(init=False)
    model_name: str = field(init=False)
    cursor: Cursor | None = field(init=False)
    models: tuple[Model, ...] = field(init=False)
    models_error: str = field(init=False)
    yard: Yard | None = field(init=False)
    stack: AsyncExitStack = field(init=False)

    def __post_init__(self) -> None:
        self.stack = AsyncExitStack()

    async def apply(self, settings: dict[str, str]) -> None:
        """Build every part from the config and these settings. A turn that runs now
        keeps the agent it began with; the old agents close at shutdown."""
        config = overlay(self.base, settings)
        agent = build_agent(config)
        await self.stack.enter_async_context(agent)
        cursor = Cursor(self.http, config.cursor_api_key) if config.cursor_api_key else None
        models: tuple[Model, ...] = ()
        error = ""
        if cursor is not None:
            try:
                models = await cursor.models()
            except CoderError as exc:
                error = str(exc)
        self.config = config
        self.agent = agent
        self.model_name = config.model if config.openai_api_key.strip() else "fake"
        self.cursor = cursor
        self.models = models
        self.models_error = error
        self.yard = (
            Yard(self.http, config.yard_url, config.yard_token) if config.yard_token else None
        )

    async def close(self) -> None:
        await self.stack.aclose()
