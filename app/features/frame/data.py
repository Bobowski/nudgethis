from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from litewriter import LiteWriter, Tx
from stario.json import dumps, loads

MESSAGES_SQL = """
SELECT m.id, m.data, c.status
FROM messages m
LEFT JOIN changes c ON c.id = json_extract(m.data, '$.change_id')
ORDER BY m.id DESC
LIMIT 100
"""

MESSAGE_COLUMNS = {
    "at": "TEXT AS (data->>'at')",
    "app": "TEXT AS (data->>'app')",
}

CHANGE_COLUMNS = {
    "app": "TEXT AS (data->>'app')",
    "status": "TEXT AS (data->>'status')",
}


@dataclass(frozen=True, slots=True)
class Message:
    id: int
    at: str
    role: str
    app: str
    text: str
    shots: tuple[str, ...]
    actions: tuple[str, ...]
    change_id: int | None
    change_status: str | None
    thinking: bool


def message_row(id: int, data: str, status: str | None) -> Message:
    d = cast(dict[str, Any], loads(data))
    return Message(
        id=id,
        at=d["at"],
        role=d["role"],
        app=d["app"],
        text=d["text"],
        shots=tuple(d["shots"]),
        actions=tuple(d["actions"]),
        change_id=d["change_id"],
        change_status=status,
        thinking=d.get("thinking") is True,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def schema(tx: Tx) -> None:
    for table, columns in (
        ("messages", MESSAGE_COLUMNS),
        ("changes", CHANGE_COLUMNS),
        ("notes", {}),
        ("coders", {"app": "TEXT AS (data->>'app')"}),
    ):
        tx.execute(
            f"CREATE TABLE IF NOT EXISTS {table} ("
            " id INTEGER PRIMARY KEY, data TEXT NOT NULL CHECK (json_valid(data)))"
        )
        have = {row[0] for row in tx.query(f"SELECT name FROM pragma_table_xinfo('{table}')")}
        for name, column in columns.items():
            if name not in have:
                tx.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column} VIRTUAL")
    tx.execute("CREATE INDEX IF NOT EXISTS messages_app ON messages(app)")
    tx.execute("CREATE INDEX IF NOT EXISTS messages_at ON messages(at)")
    tx.execute("CREATE INDEX IF NOT EXISTS changes_app_status ON changes(app, status)")
    tx.execute("CREATE UNIQUE INDEX IF NOT EXISTS coders_app ON coders(app)")
    # A fake job dies with the process, so its change is dropped. A Cursor run
    # goes on in the cloud: bootstrap follows it again. A reply left thinking
    # admits it was lost.
    tx.execute(
        "UPDATE changes SET data = json_set(data, '$.status', 'dropped')"
        " WHERE status IN ('working', 'deploying') AND data->>'run_id' IS NULL"
    )
    tx.execute(
        "UPDATE messages SET data = json_set(data, '$.text',"
        " 'I lost that one. Say it again.', '$.thinking', json('false'))"
        " WHERE data->>'thinking' = 1"
    )


def history_rows(db: LiteWriter, before_id: int, limit: int) -> list[Message]:
    return list(
        reversed(
            db.query(
                """
                SELECT m.id, m.data, NULL FROM messages m
                WHERE m.id < :before AND data->>'thinking' IS NOT 1
                ORDER BY m.id DESC LIMIT :limit
                """,
                message_row,
                before=before_id,
                limit=limit,
            )
        )
    )


def get_phase(db: LiteWriter, app: str) -> str:
    """What the coder does for the app now: deploying, working, or nothing."""
    statuses = {
        row[0]
        for row in db.query(
            "SELECT status FROM changes WHERE app = :app AND status IN ('working', 'deploying')",
            app=app,
        )
    }
    return next((s for s in ("deploying", "working") if s in statuses), "")


# The coder of one app: model id and params (JSON). No row means CURSOR_MODEL.
CODER_SQL = "SELECT data->>'model', data->>'params' FROM coders WHERE app = :app"


def get_coder(db: LiteWriter, app: str) -> tuple[str, dict[str, str]] | None:
    row = db.one(CODER_SQL, app=app)
    return (row[0], cast(dict[str, str], loads(row[1]))) if row else None


def set_coder(tx: Tx, app: str, model: str, params: dict[str, str]) -> None:
    tx.execute("DELETE FROM coders WHERE app = :app", app=app)
    tx.execute(
        "INSERT INTO coders (data) VALUES (:data)",
        data=dumps({"app": app, "model": model, "params": params}),
    )


def list_timeline(db: LiteWriter, app: str) -> list[tuple]:
    """The changes of the app, newest first: id, brief, status, updated."""
    return db.query(
        "SELECT id, data->>'brief', status, data->>'updated' FROM changes"
        " WHERE app = :app ORDER BY id DESC LIMIT 50",
        app=app,
    )


def live_rev(db: LiteWriter, app: str) -> int:
    """The newest change that went live: the frame reloads when it grows."""
    return db.value(
        "SELECT coalesce(max(id), 0) FROM changes"
        " WHERE app = :app AND status IN ('live', 'undone')",
        app=app,
    )


def list_runs(db: LiteWriter) -> list[tuple]:
    """Changes whose Cursor run or deploy is still going: id, app, agent, run, after."""
    return db.query(
        "SELECT id, app, data->>'agent_id', data->>'run_id', data->>'after' FROM changes"
        " WHERE status IN ('working', 'deploying') AND data->>'run_id' IS NOT NULL"
    )


def _add_message(
    tx: Tx, app: str, role: str, text: str, change_id: int | None, **extra: object
) -> int:
    return tx.value(
        "INSERT INTO messages (data) VALUES (:data) RETURNING id",
        data=dumps(
            {
                "at": _now(),
                "role": role,
                "app": app,
                "text": text,
                "shots": extra.pop("shots", []),
                "actions": extra.pop("actions", []),
                "change_id": change_id,
                **extra,
            }
        ),
    )


def add_request(tx: Tx, app: str, text: str, shots: list[str]) -> tuple[int, int]:
    you_id = _add_message(tx, app, "you", text, None, shots=shots)
    placeholder_id = _add_message(tx, app, "nudge", "", None, thinking=True)
    return you_id, placeholder_id


def set_reply(tx: Tx, message_id: int, text: str, change_id: int | None) -> None:
    tx.execute(
        "UPDATE messages SET data = json_set(data, '$.text', :text,"
        " '$.thinking', json('false'), '$.change_id', :cid) WHERE id = :id",
        id=message_id,
        text=text,
        cid=change_id,
    )


def set_run(tx: Tx, change_id: int, agent_id: str, run_id: str, after: str) -> None:
    """The Cursor run of a change, and the deploy that was newest when it began."""
    tx.execute(
        "UPDATE changes SET data = json_set(data, '$.agent_id', :agent, '$.run_id', :run,"
        " '$.after', :after) WHERE id = :id",
        id=change_id,
        agent=agent_id,
        run=run_id,
        after=after,
    )


def set_deploying(tx: Tx, change_id: int) -> None:
    tx.execute(
        "UPDATE changes SET data = json_set(data, '$.status', 'deploying', '$.updated', :now)"
        " WHERE id = :id",
        id=change_id,
        now=_now(),
    )


def go_live(tx: Tx, change_id: int, app: str, text: str) -> None:
    """The change is deployed. An undo offers no undo itself."""
    undoes = tx.value("SELECT data->>'undoes' FROM changes WHERE id = :id", id=change_id)
    tx.execute(
        "UPDATE changes SET data = json_set(data, '$.status', 'live', '$.updated', :now)"
        " WHERE id = :id",
        id=change_id,
        now=_now(),
    )
    _add_message(tx, app, "nudge", text, change_id, actions=[] if undoes else ["undo"])


def fail_change(tx: Tx, change_id: int, app: str, text: str) -> None:
    """The change did not go live. A failed undo leaves its change live again."""
    drop_change(tx, change_id)
    tx.execute(
        "UPDATE changes SET data = json_set(data, '$.status', 'live')"
        " WHERE id = (SELECT data->>'undoes' FROM changes WHERE id = :id)",
        id=change_id,
    )
    _add_message(tx, app, "nudge", text, change_id)


def drop_change(tx: Tx, change_id: int) -> None:
    tx.execute(
        "UPDATE changes SET data = json_set(data, '$.status', 'dropped')"
        " WHERE id = :id AND status IN ('working', 'deploying')",
        id=change_id,
    )
