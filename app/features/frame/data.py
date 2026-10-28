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
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def schema(tx: Tx) -> None:
    for table, columns in (
        ("messages", MESSAGE_COLUMNS),
        ("changes", CHANGE_COLUMNS),
        ("notes", {}),
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
    # The fake nudge job dies with the process: a change left working is dropped.
    tx.execute(
        "UPDATE changes SET data = json_set(data, '$.status', 'dropped') WHERE status = 'working'"
    )


def get_message(db: LiteWriter, message_id: int) -> Message | None:
    return db.one(
        """
        SELECT m.id, m.data, c.status
        FROM messages m
        LEFT JOIN changes c ON c.id = json_extract(m.data, '$.change_id')
        WHERE m.id = :id
        """,
        message_row,
        id=message_id,
    )


def working_count(db: LiteWriter, app: str) -> int:
    return db.value(
        "SELECT count(*) FROM changes WHERE app = :app AND status = 'working'",
        app=app,
    )


def shipped_rev(db: LiteWriter, app: str) -> int:
    row = db.one(
        "SELECT id FROM changes WHERE app = :app AND status = 'shipped' ORDER BY id DESC LIMIT 1",
        app=app,
    )
    return row[0] if row else 0


def add_request(tx: Tx, app: str, text: str, shots: list[str]) -> int:
    now = _now()
    change_id = tx.value(
        "INSERT INTO changes (data) VALUES (:data) RETURNING id",
        data=dumps(
            {
                "app": app,
                "brief": text,
                "status": "working",
                "created": now,
                "updated": now,
            }
        ),
    )
    tx.execute(
        "INSERT INTO messages (data) VALUES (:data)",
        data=dumps(
            {
                "at": now,
                "role": "you",
                "app": app,
                "text": text,
                "shots": shots,
                "actions": [],
                "change_id": change_id,
            }
        ),
    )
    tx.execute(
        "INSERT INTO messages (data) VALUES (:data)",
        data=dumps(
            {
                "at": now,
                "role": "nudge",
                "app": app,
                "text": "On it.",
                "shots": [],
                "actions": [],
                "change_id": change_id,
            }
        ),
    )
    return change_id


def finish_change(tx: Tx, change_id: int, app: str) -> None:
    now = _now()
    tx.execute(
        "UPDATE changes"
        " SET data = json_set(data, '$.status', 'ready', '$.updated', :now)"
        " WHERE id = :id",
        id=change_id,
        now=now,
    )
    tx.execute(
        "INSERT INTO messages (data) VALUES (:data)",
        data=dumps(
            {
                "at": now,
                "role": "nudge",
                "app": app,
                "text": "Done. (fake) I'd change that now.",
                "shots": [],
                "actions": ["ship", "not_yet"],
                "change_id": change_id,
            }
        ),
    )


def drop_change(tx: Tx, change_id: int) -> None:
    tx.execute(
        "UPDATE changes SET data = json_set(data, '$.status', 'dropped')"
        " WHERE id = :id AND status = 'working'",
        id=change_id,
    )


def apply_action(tx: Tx, message_id: int, change_id: int, app: str, action: str) -> None:
    now = _now()
    shipped = action == "ship"
    tx.execute(
        "UPDATE changes"
        " SET data = json_set(data, '$.status', :status, '$.updated', :now)"
        " WHERE id = :id",
        id=change_id,
        status="shipped" if shipped else "dropped",
        now=now,
    )
    tx.execute(
        "UPDATE messages SET data = json_set(data, '$.actions', json('[]')) WHERE id = :id",
        id=message_id,
    )
    tx.execute(
        "INSERT INTO messages (data) VALUES (:data)",
        data=dumps(
            {
                "at": now,
                "role": "nudge",
                "app": app,
                "text": "Live." if shipped else "Okay. Tell me what to change.",
                "shots": [],
                "actions": [],
                "change_id": change_id,
            }
        ),
    )
