from litewriter import LiteWriter, Tx
from stario.json import dumps

from app.builder import SECRETS, Vault


def schema(tx: Tx) -> None:
    tx.execute(
        "CREATE TABLE IF NOT EXISTS settings ("
        " id INTEGER PRIMARY KEY, data TEXT NOT NULL CHECK (json_valid(data)))"
    )
    have = {row[0] for row in tx.query("SELECT name FROM pragma_table_xinfo('settings')")}
    if "key" not in have:
        tx.execute("ALTER TABLE settings ADD COLUMN key TEXT AS (data->>'key') VIRTUAL")
    tx.execute("CREATE UNIQUE INDEX IF NOT EXISTS settings_key ON settings(key)")


def list_settings(db: LiteWriter, vault: Vault) -> dict[str, str]:
    """What the person saved, secrets opened. A secret sealed with another
    SESSION_SECRET cannot be opened and counts as not set."""
    out = {}
    for key, value in db.query("SELECT data->>'key', data->>'value' FROM settings"):
        plain = vault.open(value) if key in SECRETS else value
        if plain is not None:
            out[key] = plain
    return out


def set_setting(tx: Tx, key: str, value: str) -> None:
    """`value` is already sealed when the key is a secret."""
    tx.execute("DELETE FROM settings WHERE key = :key", key=key)
    tx.execute(
        "INSERT INTO settings (data) VALUES (:data)", data=dumps({"key": key, "value": value})
    )


def remove_setting(tx: Tx, key: str) -> None:
    tx.execute("DELETE FROM settings WHERE key = :key", key=key)
