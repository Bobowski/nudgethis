"""Real-model smoke: three turns against the production bootstrap.

Run with `just smoke` (just loads .env, which holds OPENAI_API_KEY).
"""

import asyncio
import base64
import binascii
import json
import os
import sqlite3
import struct
import sys
import tempfile
import time
import zlib
from functools import partial

import httpx
from stario.testing import TestClient
from tests.conftest import ADAM, google_token, login

import app.main
from app.main import bootstrap


def png(width: int, height: int, marked: bool) -> str:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)
        )

    rows = []
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            on_edge = (
                marked
                and 40 <= x <= 200
                and 30 <= y <= 150
                and (x < 44 or x > 196 or y < 34 or y > 146)
            )
            row += bytes((200, 40, 30) if on_edge else (245, 244, 240))
        rows.append(bytes(row))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def last_nudge(db_path: str) -> str | None:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = con.execute("SELECT data FROM messages ORDER BY id").fetchall()
    con.close()
    last_you = max(i for i, (d,) in enumerate(rows) if json.loads(d)["role"] == "you")
    for (data,) in rows[last_you + 1 :]:
        d = json.loads(data)
        if d["role"] == "nudge" and not d.get("thinking"):
            return d["text"]
    return None


async def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set (just loads .env)")
        return 1
    os.environ["PROJECT_DATA_DIR"] = tempfile.mkdtemp(prefix="nudgethis-smoke-")
    os.environ["NUDGE_FAKE_DELAY"] = "0"
    os.environ["NUDGE_APPS"] = "demo=https://example.com"
    # The real model only: a fake coder, and a mocked Google that signs in ADAM.
    os.environ["CURSOR_API_KEY"] = ""
    os.environ |= {
        "GOOGLE_CLIENT_ID": "google-id",
        "GOOGLE_CLIENT_SECRET": "google-secret",
        "SESSION_SECRET": "smoke-secret-of-at-least-thirty-two-chars",
        "NUDGE_ALLOWED_EMAILS": ADAM,
    }
    google = httpx.MockTransport(lambda r: google_token(r) or httpx.Response(404))
    app.main.AsyncClient = partial(httpx.AsyncClient, transport=google)
    marked, clean = png(400, 240, True), png(400, 240, False)
    turns = [
        {"text": "make the header text bigger", "shots": [marked, clean]},
        {"text": "what's running?", "shots": []},
        {"text": "undo that", "shots": []},
    ]
    db_path = os.environ["PROJECT_DATA_DIR"] + "/nudgethis.sqlite3"
    async with TestClient(bootstrap, request_timeout=90) as client:
        await login(client)
        for i, turn in enumerate(turns):
            started = time.monotonic()
            r = await client.post("/a/demo/say", json={"tab": "s1", **turn})
            if r.status_code != 200:
                print(f"turn {i + 1}: say failed with {r.status_code}")
                return 1
            await client.drain_tasks()
            reply = last_nudge(db_path)
            span = client.tracer.find_span("nudge.turn", root_id=r.span_id)
            attrs = dict(span.attributes) if span else {}
            tools = attrs.get("nudge.tools") or []
            print(f"turn {i + 1} ({time.monotonic() - started:.1f}s)")
            print(f"  you:   {turn['text']}")
            print(f"  nudge: {reply}")
            print(
                f"  tools: {tools}  tokens: in={attrs.get('nudge.input_tokens')}"
                f" out={attrs.get('nudge.output_tokens')}"
                f" reasoning={attrs.get('nudge.reasoning_tokens')}"
                f"  model={attrs.get('nudge.model')}"
            )
            if reply in (None, "I could not reach the model. Try again."):
                print("  FAILED: fallback reply")
                return 1
            if i == 0 and "start_change" not in tools:
                print("  FAILED: turn 1 did not call start_change")
                return 1
    print("smoke ok")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
