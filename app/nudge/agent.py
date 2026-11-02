from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pydantic_ai
from litewriter import LiteWriter
from pydantic_ai import Agent, ConcurrencyLimitedModel, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import (
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import Config
from app.nudge import data as nudge_data

ERROR_TEXT = "I could not reach the model. Try again."


@dataclass(slots=True)
class TurnDeps:
    db: LiteWriter
    app_name: str
    you_message_id: int
    start_ready: Callable[[int, str], None]
    undo: Callable[[int], Awaitable[str]]
    called: list[str] = field(default_factory=list)
    change_id: int | None = None


def load_instructions() -> str:
    return (Path(__file__).with_name("instructions.md")).read_text()


def context(name: str, url: str, notes: list[tuple], changes: list[tuple]) -> str:
    lines = [f"Open app: {name} ({url})", "Remembered:"]
    lines += [f"- {text} [{app or 'all apps'}]" for app, text in notes] or ["- none"]
    lines.append("Open changes:")
    lines += [f"- #{cid} {app} {status}: {brief[:140]}" for cid, app, status, brief in changes] or [
        "- none"
    ]
    return "\n".join(lines)


def _fake(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    last = messages[-1]
    if isinstance(last, ModelRequest) and any(isinstance(p, ToolReturnPart) for p in last.parts):
        return ModelResponse(parts=[TextPart("On it.")])
    brief = "see screenshot"
    if isinstance(last, ModelRequest):
        for part in last.parts:
            if isinstance(part, UserPromptPart):
                content = part.content if isinstance(part.content, list) else [part.content]
                texts = [c.strip() for c in content if isinstance(c, str) and c.strip()]
                if texts:
                    brief = " ".join(texts)
    return ModelResponse(parts=[ToolCallPart("start_change", {"brief": brief})])


def build_agent(config: Config, *, model: Any = None) -> Agent[TurnDeps, str]:
    pydantic_ai.BANNER_ENABLED = False
    if model is None:
        if config.openai_api_key.strip():
            model = OpenAIResponsesModel(
                config.model,
                provider=OpenAIProvider(
                    api_key=config.openai_api_key,
                    base_url=config.openai_base_url,
                ),
            )
        else:
            model = FunctionModel(_fake)
    agent: Agent[TurnDeps, str] = Agent(
        ConcurrencyLimitedModel(model, 4),
        deps_type=TurnDeps,
        model_settings=OpenAIResponsesModelSettings(
            openai_reasoning_effort=cast(Any, config.effort)
        ),
    )

    @agent.tool
    async def start_change(ctx: RunContext[TurnDeps], brief: str) -> str:
        """Start a change on the open app; a coder agent does the work."""
        deps = ctx.deps
        deps.called.append("start_change")
        if deps.change_id is not None:
            return "already started one this turn"
        change_id = await deps.db.write(
            nudge_data.start_change,
            deps.app_name,
            brief.strip(),
            deps.you_message_id,
        )
        deps.change_id = change_id
        deps.start_ready(change_id, brief.strip())
        return f"change #{change_id} started"

    @agent.tool
    async def undo(ctx: RunContext[TurnDeps], change_id: int) -> str:
        """Revert a live change of the open app; the coder pushes the revert."""
        ctx.deps.called.append("undo")
        return await ctx.deps.undo(change_id)

    @agent.tool
    async def remember(ctx: RunContext[TurnDeps], note: str, app_only: bool) -> str:
        """Keep a fact for later sessions."""
        deps = ctx.deps
        deps.called.append("remember")
        text = note.strip()[:300]
        if not text:
            return "nothing to note"
        await deps.db.write(nudge_data.add_note, deps.app_name if app_only else "", text)
        return "noted"

    return agent
