import asyncio
import base64
import binascii
import uuid
from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Span, Writer
from stario.datastar import SSE, read_signals

from app.config import Config
from app.features.frame import data as store
from app.features.frame.urls import ACT, FRAME, FRAME_LIVE, SAY
from app.features.frame.views import render

MAX_SHOT = 4 * 1024 * 1024
MAGIC = {
    "png": (b"\x89PNG\r\n\x1a\n", "png"),
    "jpeg": (b"\xff\xd8\xff", "jpg"),
    "webp": (b"RIFF", "webp"),
}


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


@dataclass(frozen=True, slots=True)
class FramePage:
    db: LiteWriter
    config: Config

    def register(self, app: App) -> None:
        app.add(FRAME, self.show)
        app.add(FRAME_LIVE, self.live)
        app.add(SAY, self.say)
        app.add(ACT, self.act)

    def url_of(self, name: str) -> str | None:
        return dict(self.config.apps).get(name)

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
        if self.url_of(name) is None:
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
        change_id = await self.db.write(store.add_request, name, text, names)
        c.app.create_task(self.nudge(change_id, name, c.span.step("nudge.fake")))

    async def nudge(self, change_id: int, app: str, span: Span) -> None:
        with span:
            span.attr("change.id", change_id)
            try:
                await asyncio.sleep(self.config.fake_delay)
            except asyncio.CancelledError:
                await self.db.write(store.drop_change, change_id)
                raise
            await self.db.write(store.finish_change, change_id, app)

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
        await self.db.write(store.apply_action, message_id, message.change_id, name, action)
