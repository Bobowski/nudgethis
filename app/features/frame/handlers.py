import asyncio
import base64
import binascii
import time
import uuid
from collections.abc import Awaitable, Callable
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
from app.coder.cursor import Cursor, Model
from app.coder.yard import Yard
from app.config import Config
from app.features.frame import data as store
from app.features.frame.urls import CODER, CODER_LIVE, FRAME, FRAME_LIVE, SAY, UNDO
from app.features.frame.views import coder_panel, render
from app.features.home import data as apps
from app.nudge import agent as nudge
from app.nudge import data as nudge_data
from app.nudge.agent import TurnDeps

MAX_SHOT = 4 * 1024 * 1024
DEPLOY_TIMEOUT = 600
MAGIC = {
    "png": (b"\x89PNG\r\n\x1a\n", "png"),
    "jpeg": (b"\xff\xd8\xff", "jpg"),
    "webp": (b"RIFF", "webp"),
}
SHOT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}


def brief_of(report: str, limit: int = 2400) -> str:
    """The coder's report, cut at a line break when it is long."""
    report = report.strip()
    if len(report) <= limit:
        return report
    cut = report.rfind("\n", 0, limit)
    return report[: cut if cut > limit // 2 else limit].rstrip() + "\n\n…"


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
    yard: Yard | None
    models: tuple[Model, ...]

    def register(self, app: App) -> None:
        app.add(FRAME, self.show)
        app.add(FRAME_LIVE, self.live)
        app.add(SAY, self.say)
        app.add(UNDO, self.undo_command)
        app.add(CODER, self.set_coder)
        app.add(CODER_LIVE, self.coder_live)

    def url_of(self, name: str) -> str | None:
        """An app from NUDGE_APPS, or one that nudgethis made and Yard deployed."""
        made = apps.get_app(self.db, name)
        return dict(self.config.apps).get(name) or (
            made[0] if made and made[1] == "ready" else None
        )

    def coder_of(self, name: str) -> tuple[str, dict[str, str]]:
        """The app's own model and params, or CURSOR_MODEL; params checked against the model."""
        model_id, params = store.get_coder(self.db, name) or (
            self.config.cursor_model,
            dict(self.config.cursor_params),
        )
        model = next((m for m in self.models if m.id == model_id), None)
        return model_id, model.settle(params) if model else params

    def coder(self, name: str):
        return coder_panel(name, self.models, *self.coder_of(name), self.cursor is not None)

    def resume(self, app: App, span: Span) -> None:
        """Follow the Cursor runs and deploys that were going when the process stopped."""
        for change_id, name, agent_id, run_id, after in store.list_runs(self.db):
            if self.url_of(name) is not None and self.cursor is not None:
                app.create_task(
                    self.resumed(
                        change_id, name, agent_id, run_id, after, span.step("nudge.resume")
                    )
                )

    def pod(self, name: str, url: str, tab: str):
        return render(
            list(reversed(self.db.query(store.MESSAGES_SQL, store.message_row))),
            name,
            url,
            store.list_timeline(self.db, name),
            store.get_phase(self.db, name),
            store.live_rev(self.db, name),
            tab,
            self.coder(name),
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
                        store.list_timeline(self.db, name),
                        store.get_phase(self.db, name),
                        store.live_rev(self.db, name),
                        tab,
                        self.coder(name),
                    )
                )
                sse.patch_signals({"_rev": store.live_rev(self.db, name)})

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

        async def undo(change_id: int) -> str:
            return await self.start_undo(c.app, change_id, name, step)

        c.app.create_task(
            self.turn(
                name,
                url,
                you_id,
                placeholder_id,
                text,
                names,
                start_ready,
                undo,
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
        undo: Callable[[int], Awaitable[str]],
        span: Span,
    ) -> None:
        with span:
            started = time.monotonic()
            deps = TurnDeps(
                db=self.db,
                app_name=name,
                you_message_id=you_id,
                start_ready=start_ready,
                undo=undo,
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
                await self.fake(change_id, name, "Done. (fake) I'd change that now.")
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
                + " Keep the change small, run `just check`, and push to main."
            )
            cursor, repo = self.cursor, f"{self.config.repo_base}/{name}"
            model, params = self.coder_of(name)
            span.attrs({"cursor.model": model, "cursor.params": str(params)})
            await self.launch(
                change_id,
                name,
                span,
                lambda: cursor.start(repo, prompt, images, brief, model, params),
            )

    async def fake(self, change_id: int, name: str, text: str) -> None:
        try:
            await asyncio.sleep(self.config.fake_delay)
        except asyncio.CancelledError:
            await self.db.write(store.drop_change, change_id)
            raise
        await self.db.write(store.go_live, change_id, name, text)

    async def launch(
        self, change_id: int, name: str, span: Span, start: Callable[[], Awaitable[tuple[str, str]]]
    ) -> None:
        """Start a Cursor run, then follow it through the deploy."""
        try:
            after = str((await self.yard.last_deploy(name)).get("started", "")) if self.yard else ""
            agent_id, run_id = await start()
        except CoderError as exc:
            await self.db.write(store.fail_change, change_id, name, f"I could not start: {exc}")
            span.fail(str(exc))
            return
        await self.db.write(store.set_run, change_id, agent_id, run_id, after)
        await self.follow(change_id, name, agent_id, run_id, after, span)

    async def resumed(
        self, change_id: int, name: str, agent_id: str, run_id: str, after: str, span: Span
    ) -> None:
        with span:
            await self.follow(change_id, name, agent_id, run_id, after, span)

    async def follow(
        self, change_id: int, name: str, agent_id: str, run_id: str, after: str, span: Span
    ) -> None:
        """The run pushes to main; the change is live when Yard's next deploy is ok."""
        assert self.cursor is not None
        try:
            run = await self.cursor.wait(agent_id, run_id)
            span.attrs({"cursor.status": run.status})
            if run.status != "FINISHED":
                why = run.result[:300] or run.status.lower()
                await self.db.write(store.fail_change, change_id, name, f"No change: {why}")
                return
            text = brief_of(run.result) or "Done."
            if self.yard is not None:
                await self.db.write(store.set_deploying, change_id)
                async with asyncio.timeout(DEPLOY_TIMEOUT):
                    deploy = await self.yard.next_deploy(name, after)
                span.attrs({"yard.status": deploy.get("status", "")})
                if deploy.get("status") != "ok":
                    why = deploy.get("error") or deploy.get("status")
                    text = f"Pushed, but the deploy did not go live: {why}"
                    await self.db.write(store.fail_change, change_id, name, text)
                    return
        except (CoderError, TimeoutError) as exc:
            why = str(exc) or "the deploy took too long"
            await self.db.write(store.fail_change, change_id, name, f"The change failed: {why}")
            span.fail(why)
            return
        await self.db.write(store.go_live, change_id, name, text)

    async def start_undo(self, app: App, change_id: int, name: str, span: Span) -> str:
        """Revert a live change: a follow-up run on the agent that made it."""
        row = nudge_data.get_change(self.db, change_id)
        if row is None or row[1] != name or row[2] != "live":
            return f"change #{change_id} is not live"
        undo_id = await self.db.write(nudge_data.start_undo, change_id)
        app.create_task(self.undo(undo_id, change_id, name, row[3], span.step("nudge.undo")))
        return f"undoing change #{change_id} as #{undo_id}"

    async def undo(
        self, undo_id: int, change_id: int, name: str, agent_id: str | None, span: Span
    ) -> None:
        with span:
            span.attrs({"change.id": undo_id, "change.undoes": change_id})
            cursor = self.cursor
            if cursor is None or not agent_id:
                await self.fake(undo_id, name, "Undone. (fake)")
                return
            text = (
                "Revert the change you pushed to main in your last run, run `just check`,"
                " and push the revert to main."
            )
            await self.launch(undo_id, name, span, lambda: cursor.follow_up(agent_id, text))

    async def undo_command(self, c: Context, w: Writer) -> None:
        name = c.match.params["app"]
        if self.url_of(name) is None:
            w.text("no such app", status=404)
            return
        signals = await read_signals(c.req)
        tab = str(signals.get("tab", ""))
        change_id = signals.get("change_id")
        if not tab.isalnum() or len(tab) > 32:
            w.text("tab must be a short id", status=400)
            return
        if type(change_id) is not int:
            w.text("change_id must be a number", status=400)
            return
        row = nudge_data.get_change(self.db, change_id)
        if row is None or row[1] != name:
            w.text("no such change", status=404)
            return
        if row[2] != "live":
            w.text("the change is not live", status=409)
            return
        w.empty()
        await self.start_undo(c.app, change_id, name, c.span)

    async def set_coder(self, c: Context, w: Writer) -> None:
        """One choice in the Coder tab: `model=<id>` or `<param>=<value>`."""
        name = c.match.params["app"]
        if self.url_of(name) is None:
            w.text("no such app", status=404)
            return
        signals = await read_signals(c.req)
        tab = str(signals.get("tab", ""))
        key, _, value = str(signals.get("coder_set", "")).partition("=")
        if not tab.isalnum() or len(tab) > 32:
            w.text("tab must be a short id", status=400)
            return
        model_id, params = self.coder_of(name)
        if key == "model":
            model = next((m for m in self.models if m.id == value), None)
            if model is None:
                w.text("no such model", status=400)
                return
            model_id, params = model.id, dict(model.default)
        else:
            model = next((m for m in self.models if m.id == model_id), None)
            param = next((p for p in model.params if p.id == key), None) if model else None
            if param is None or value not in {v for v, _ in param.values}:
                w.text("no such setting for this model", status=400)
                return
            params = {**params, key: value}
        w.empty()
        await self.db.write(store.set_coder, name, model_id, params)

    async def coder_live(self, c: Context, w: Writer) -> None:
        name = c.match.params["app"]
        if self.url_of(name) is None:
            w.text("no such app", status=404)
            return
        sse = SSE(w)
        async with self.db.watch(store.CODER_SQL, app=name) as rows:
            async for _ in c.alive(rows):
                sse.patch_elements(self.coder(name))
