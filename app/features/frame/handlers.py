import asyncio
import base64
import binascii
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from litewriter import LiteWriter
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from stario import App, Context, Span, Writer
from stario.datastar import SSE, read_signals

from app.coder import CoderError
from app.coder.cursor import Cursor
from app.coder.github import GitHub
from app.config import Config
from app.features.frame import data as store
from app.features.frame.urls import ACT, FRAME, FRAME_LIVE, SAY
from app.features.frame.views import render
from app.nudge import agent as nudge
from app.nudge import data as nudge_data
from app.nudge.agent import TurnDeps

MAX_SHOT = 4 * 1024 * 1024
MAGIC = {
    "png": (b"\x89PNG\r\n\x1a\n", "png"),
    "jpeg": (b"\xff\xd8\xff", "jpg"),
    "webp": (b"RIFF", "webp"),
}
SHOT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}


def decode_shot(raw: object) -> tuple[bytes, str] | None:
    if not isinstance(raw, str):
        return None
    head, sep, payload = raw.partition(",")
    kind = head.removeprefix("data:image/").removesuffix(";base64")
    if (
        not sep
        or not head.startswith("data:image/")
        or not head.endswith(";base64")
        or kind not in MAGIC
    ):
        return None
    try:
        blob = base64.b64decode(payload, validate=True)
    except binascii.Error:
        return None
    magic, ext = MAGIC[kind]
    if len(blob) > MAX_SHOT or not blob.startswith(magic):
        return None
    if kind == "webp" and blob[8:12] != b"WEBP":
        return None
    return blob, ext


def history(messages: list[store.Message], open_app: str) -> list[ModelMessage]:
    out: list[ModelMessage] = []
    for m in messages:
        if m.role == "you":
            text = (f"[{m.app}] " if m.app != open_app else "") + m.text
            if m.shots:
                text += " [screenshot]"
            out.append(ModelRequest(parts=[UserPromptPart(text)]))
        else:
            out.append(ModelResponse(parts=[TextPart(m.text)]))
    return out


@dataclass(frozen=True, slots=True)
class FramePage:
    db: LiteWriter
    config: Config
    agent: Agent[TurnDeps, str]
    model_name: str
    instructions: str
    cursor: Cursor | None
    github: GitHub

    def register(self, app: App) -> None:
        app.add(FRAME, self.show)
        app.add(FRAME_LIVE, self.live)
        app.add(SAY, self.say)
        app.add(ACT, self.act)

    def url_of(self, name: str) -> str | None:
        return dict(self.config.apps).get(name)

    def resume(self, app: App, span: Span) -> None:
        """Follow the Cursor runs that were going when the process stopped."""
        for change_id, name, _brief, agent_id, run_id in store.list_runs(self.db):
            if self.url_of(name) is not None and self.cursor is not None:
                app.create_task(
                    self.follow(change_id, name, agent_id, run_id, span.step("nudge.resume"))
                )

    def pod(self, name: str, url: str, tab: str):
        return render(
            list(reversed(self.db.query(store.MESSAGES_SQL, store.message_row))),
            name,
            url,
            store.working_count(self.db, name) > 0,
            store.shipped_rev(self.db, name),
            tab,
        )

    async def show(self, c: Context, w: Writer) -> None:
        name = c.match.params["app"]
        url = self.url_of(name)
        if url is None:
            w.text("no such app", status=404)
            return
        w.html(self.pod(name, url, uuid.uuid7().hex))

    async def live(self, c: Context, w: Writer) -> None:
        name = c.match.params["app"]
        url = self.url_of(name)
        if url is None:
            w.text("no such app", status=404)
            return
        tab = str((await read_signals(c.req)).get("tab", ""))
        if not tab.isalnum() or len(tab) > 32:
            w.text("tab must be a short id", status=400)
            return
        sse = SSE(w)
        async with self.db.watch(store.MESSAGES_SQL, store.message_row) as rows:
            async for messages in c.alive(rows):
                sse.patch_elements(
                    render(
                        list(reversed(messages)),
                        name,
                        url,
                        store.working_count(self.db, name) > 0,
                        store.shipped_rev(self.db, name),
                        tab,
                    )
                )
                sse.patch_signals({"_rev": store.shipped_rev(self.db, name)})

    async def say(self, c: Context, w: Writer) -> None:
        name = c.match.params["app"]
        url = self.url_of(name)
        if url is None:
            w.text("no such app", status=404)
            return
        signals = await read_signals(c.req)
        text = str(signals.get("text", "")).strip()
        tab = str(signals.get("tab", ""))
        raw_shots = signals.get("shots") or []
        if not tab.isalnum() or len(tab) > 32:
            w.text("tab must be a short id", status=400)
            return
        if len(text) > 2000:
            w.text("text must be at most 2000 characters", status=400)
            return
        if not isinstance(raw_shots, list) or len(raw_shots) > 2:
            w.text("shots must be a list of at most two data urls", status=400)
            return
        shots = []
        for raw in raw_shots:
            shot = decode_shot(raw)
            if shot is None:
                w.text("shots must be png, jpeg, or webp images", status=400)
                return
            shots.append(shot)
        if not text and not shots:
            w.empty()
            return
        names = []
        for blob, ext in shots:
            fname = f"{uuid.uuid7().hex}.{ext}"
            (self.config.shots_dir / fname).write_bytes(blob)
            names.append(fname)
        SSE(w).patch_signals({"text": "", "shots": []})
        you_id, placeholder_id = await self.db.write(store.add_request, name, text, names)
        step = c.span.step("nudge.turn")

        def start_ready(change_id: int, brief: str) -> None:
            c.app.create_task(
                self.code(change_id, name, url, brief, names, step.step("nudge.code"))
            )

        c.app.create_task(
            self.turn(
                name,
                url,
                you_id,
                placeholder_id,
                text,
                names,
                start_ready,
                step,
            )
        )

    async def turn(
        self,
        name: str,
        url: str,
        you_id: int,
        placeholder_id: int,
        text: str,
        shot_names: list[str],
        start_ready: Any,
        span: Span,
    ) -> None:
        with span:
            started = time.monotonic()
            deps = TurnDeps(
                db=self.db,
                app_name=name,
                you_message_id=you_id,
                start_ready=start_ready,
                settle=lambda change_id, action: self.settle(change_id, name, action, reply=False),
            )
            prompt: list[Any] = [text] if text else []
            for fname in shot_names:
                prompt.append(
                    BinaryContent(
                        data=(self.config.shots_dir / fname).read_bytes(),
                        media_type=SHOT_TYPES[Path(fname).suffix],
                    )
                )
            instructions = [
                self.instructions,
                nudge.context(
                    name,
                    url,
                    nudge_data.list_notes(self.db, name),
                    nudge_data.list_changes(self.db),
                ),
            ]
            prior = history(store.history_rows(self.db, you_id, self.config.history), name)
            try:
                async with asyncio.timeout(self.config.timeout):
                    result = await self.agent.run(
                        prompt,
                        deps=deps,
                        message_history=prior,
                        instructions=instructions,
                    )
            except asyncio.CancelledError:
                await self.db.write(store.set_reply, placeholder_id, nudge.ERROR_TEXT, None)
                raise
            except Exception as exc:
                await self.db.write(store.set_reply, placeholder_id, nudge.ERROR_TEXT, None)
                span.fail(str(exc))
                return
            output = str(result.output).strip() or "Done."
            await self.db.write(store.set_reply, placeholder_id, output, deps.change_id)
            usage = result.usage
            span.attrs(
                {
                    "nudge.model": self.model_name,
                    "nudge.tools": deps.called,
                    "nudge.input_tokens": usage.input_tokens,
                    "nudge.output_tokens": usage.output_tokens,
                    "nudge.reasoning_tokens": usage.output_reasoning_tokens,
                    "nudge.ms": int((time.monotonic() - started) * 1000),
                }
            )

    async def code(
        self,
        change_id: int,
        name: str,
        url: str,
        brief: str,
        shot_names: list[str],
        span: Span,
    ) -> None:
        with span:
            span.attrs({"change.id": change_id, "coder": "cursor" if self.cursor else "fake"})
            if self.cursor is None:
                try:
                    await asyncio.sleep(self.config.fake_delay)
                except asyncio.CancelledError:
                    await self.db.write(store.drop_change, change_id)
                    raise
                text = "Done. (fake) I'd change that now."
                await self.db.write(store.finish_change, change_id, name, text, "")
                return
            images = [
                ((self.config.shots_dir / f).read_bytes(), SHOT_TYPES[Path(f).suffix])
                for f in shot_names
            ]
            prompt = (
                f"{brief}\n\nThe app is {name}, live at {url}."
                + (
                    " The first image is the screen with the user's marks;"
                    " the second is the same screen without them."
                    if images
                    else ""
                )
                + " Keep the change small and run `just check` before you finish."
            )
            try:
                agent_id, run_id = await self.cursor.start(
                    f"{self.config.repo_base}/{name}", prompt, images, brief
                )
            except CoderError as exc:
                await self.db.write(store.fail_change, change_id, name, f"I could not start: {exc}")
                span.fail(str(exc))
                return
            await self.db.write(store.set_run, change_id, agent_id, run_id)
            await self.follow(change_id, name, agent_id, run_id, span)

    async def follow(
        self, change_id: int, name: str, agent_id: str, run_id: str, span: Span
    ) -> None:
        """Wait for the Cursor run; its pull request is the change."""
        assert self.cursor is not None
        with span:
            try:
                run = await self.cursor.wait(agent_id, run_id)
            except CoderError as exc:
                await self.db.write(store.fail_change, change_id, name, f"The coder failed: {exc}")
                span.fail(str(exc))
                return
            span.attrs({"cursor.status": run.status, "cursor.pr": run.pr_url})
            if run.status != "FINISHED" or not run.pr_url:
                why = run.result[:300] or run.status.lower()
                await self.db.write(store.fail_change, change_id, name, f"No change: {why}")
                return
            text = run.result[:600] or "Done."
            await self.db.write(store.finish_change, change_id, name, text, run.pr_url)

    async def settle(self, change_id: int, name: str, action: str, reply: bool = True) -> str:
        """Ship merges the pull request; Not yet closes it.

        A button gets a short reply; the agent's tool call writes its own.
        """
        row = nudge_data.get_change(self.db, change_id)
        if row is None or row[1] != name or row[2] != "ready":
            return f"change #{change_id} is not ready"
        try:
            if row[3]:
                await (self.github.merge if action == "ship" else self.github.close)(row[3])
        except CoderError as exc:
            await self.db.write(store.add_reply, name, f"That did not work: {exc}")
            return f"change #{change_id} failed: {exc}"
        if reply:
            await self.db.write(store.apply_action_with_reply, change_id, name, action)
        else:
            await self.db.write(nudge_data.apply_action, change_id, action)
        return f"change #{change_id} {'shipped' if action == 'ship' else 'dropped'}"

    async def act(self, c: Context, w: Writer) -> None:
        name = c.match.params["app"]
        if self.url_of(name) is None:
            w.text("no such app", status=404)
            return
        signals = await read_signals(c.req)
        tab = str(signals.get("tab", ""))
        message_id = signals.get("message_id")
        action = signals.get("action")
        if not tab.isalnum() or len(tab) > 32:
            w.text("tab must be a short id", status=400)
            return
        if type(message_id) is not int or action not in ("ship", "not_yet"):
            w.text("bad action", status=400)
            return
        message = store.get_message(self.db, message_id)
        if message is None or message.app != name:
            w.text("no such message", status=404)
            return
        if message.change_status != "ready" or message.change_id is None:
            w.text("the change is not ready", status=409)
            return
        if action not in message.actions:
            w.text("the message has no such action", status=400)
            return
        w.empty()
        await self.settle(message.change_id, name, action)
