from datetime import UTC, datetime

from litewriter import LiteWriter, Tx
from stario.json import dumps


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def get_change(db: LiteWriter, change_id: int) -> tuple | None:
    return db.one(
        "SELECT id, data->>'app' AS app, status, data->>'pr_url' FROM changes WHERE id = :id",
        id=change_id,
    )


def list_changes(db: LiteWriter) -> list[tuple]:
    return db.query(
        """
        SELECT id, app, status, data->>'brief' AS brief FROM changes
        WHERE status IN ('working', 'ready')
           OR id IN (SELECT id FROM changes WHERE status IN ('shipped', 'dropped')
                     ORDER BY id DESC LIMIT 5)
        ORDER BY id
        """
    )


def list_notes(db: LiteWriter, app: str) -> list[tuple]:
    return db.query(
        "SELECT data->>'app' AS app, data->>'text' AS text FROM notes"
        " WHERE app IN (:app, '') ORDER BY id",
        app=app,
    )


def start_change(tx: Tx, app: str, brief: str, you_message_id: int) -> int:
    now = _now()
    change_id = tx.value(
        "INSERT INTO changes (data) VALUES (:data) RETURNING id",
        data=dumps(
            {
                "app": app,
                "brief": brief,
                "status": "working",
                "created": now,
                "updated": now,
            }
        ),
    )
    tx.execute(
        "UPDATE messages SET data = json_set(data, '$.change_id', :cid) WHERE id = :id",
        cid=change_id,
        id=you_message_id,
    )
    return change_id


def apply_action(tx: Tx, change_id: int, action: str) -> None:
    tx.execute(
        "UPDATE changes"
        " SET data = json_set(data, '$.status', :status, '$.updated', :now)"
        " WHERE id = :id",
        id=change_id,
        status="shipped" if action == "ship" else "dropped",
        now=_now(),
    )
    tx.execute(
        "UPDATE messages SET data = json_set(data, '$.actions', json('[]'))"
        " WHERE json_extract(data, '$.change_id') = :id"
        " AND json_array_length(data->>'actions') > 0",
        id=change_id,
    )


def add_note(tx: Tx, app: str, text: str) -> None:
    tx.execute(
        "INSERT INTO notes (data) VALUES (:data)",
        data=dumps({"app": app, "text": text, "at": _now()}),
    )
