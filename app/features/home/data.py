from datetime import UTC, datetime

from litewriter import LiteWriter, Tx
from stario.json import dumps

# The apps that nudgethis made, newest first: name, url, status, step.
APPS_SQL = (
    "SELECT data->>'name', data->>'url', data->>'status', data->>'step' FROM apps ORDER BY id DESC"
)


def schema(tx: Tx) -> None:
    tx.execute(
        "CREATE TABLE IF NOT EXISTS apps ("
        " id INTEGER PRIMARY KEY, data TEXT NOT NULL CHECK (json_valid(data)))"
    )
    have = {row[0] for row in tx.query("SELECT name FROM pragma_table_xinfo('apps')")}
    if "name" not in have:
        tx.execute("ALTER TABLE apps ADD COLUMN name TEXT AS (data->>'name') VIRTUAL")
    tx.execute("CREATE UNIQUE INDEX IF NOT EXISTS apps_name ON apps(name)")
    # The create job dies with the process.
    tx.execute(
        "UPDATE apps SET data = json_set(data, '$.status', 'failed',"
        " '$.step', 'A restart stopped it.') WHERE data->>'status' = 'creating'"
    )


def get_app(db: LiteWriter, name: str) -> tuple | None:
    """url and status of one app that nudgethis made."""
    return db.one("SELECT data->>'url', data->>'status' FROM apps WHERE name = :name", name=name)


def add_app(tx: Tx, name: str, url: str) -> None:
    """A new app, in place of a failed one of the same name."""
    tx.execute("DELETE FROM apps WHERE name = :name AND data->>'status' = 'failed'", name=name)
    tx.execute(
        "INSERT INTO apps (data) VALUES (:data)",
        data=dumps(
            {
                "name": name,
                "url": url,
                "status": "creating",
                "step": "Waiting",
                "created": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        ),
    )


def set_app(tx: Tx, name: str, status: str, step: str) -> None:
    tx.execute(
        "UPDATE apps SET data = json_set(data, '$.status', :status, '$.step', :step)"
        " WHERE name = :name",
        name=name,
        status=status,
        step=step,
    )
