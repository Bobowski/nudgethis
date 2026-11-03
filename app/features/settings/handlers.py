from dataclasses import dataclass

from litewriter import LiteWriter
from stario import App, Context, Writer
from stario.datastar import SSE, read_signals

from app.builder import KEYS, SECRETS, Builder, Vault, check
from app.features.frame import data as frame_store
from app.features.home import data as home_store
from app.features.settings import data as store
from app.features.settings.urls import SAVE_SETTINGS, SETTINGS
from app.features.settings.views import render


def folder_size(path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


@dataclass(frozen=True, slots=True)
class SettingsPage:
    """What the builder runs on: the tokens and models it uses, and what it has used."""

    db: LiteWriter
    builder: Builder
    vault: Vault

    def register(self, app: App) -> None:
        app.add(SETTINGS, self.show)
        app.add(SAVE_SETTINGS, self.save)

    async def show(self, c: Context, w: Writer) -> None:
        config = self.builder.config
        shots = {f.name: f.stat().st_size for f in config.shots_dir.iterdir() if f.is_file()}
        w.html(
            render(
                self.builder,
                set(store.list_settings(self.db, self.vault)),
                frame_store.list_usage(self.db),
                [row[0] for row in self.db.query(home_store.APPS_SQL)],
                shots,
                folder_size(config.data_dir),
            )
        )

    async def save(self, c: Context, w: Writer) -> None:
        signals = await read_signals(c.req)
        sse = SSE(w)
        clear = str(signals.get("clear", ""))
        if clear and clear not in KEYS:
            w.text("no such setting", status=400)
            return
        updates: dict[str, str] = {}
        for key in KEYS:
            raw = signals.get(f"s_{key}")
            if raw is None:
                continue
            value = str(raw).strip()
            if key in SECRETS and not value:
                continue  # an empty secret field keeps the saved one
            if len(value) > 500:
                sse.patch_signals({"_toast": "That value is too long."})
                return
            if why := check(key, value):
                sse.patch_signals({"_toast": why})
                return
            updates[key] = value

        def write(tx) -> None:
            for key, value in updates.items():
                if value:
                    store.set_setting(tx, key, self.vault.seal(value) if key in SECRETS else value)
                else:
                    store.remove_setting(tx, key)  # empty: back to the environment
            if clear:
                store.remove_setting(tx, clear)

        await self.db.write(write)
        await self.builder.apply(store.list_settings(self.db, self.vault))
        sse.navigate(SETTINGS.href())
