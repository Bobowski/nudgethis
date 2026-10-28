from dataclasses import dataclass

from stario import App, Context, Writer

from app.features.home.urls import HOME
from app.features.home.views import render


@dataclass(frozen=True, slots=True)
class HomePage:
    apps: tuple[tuple[str, str], ...]

    def register(self, app: App) -> None:
        app.add(HOME, self.show)

    async def show(self, c: Context, w: Writer) -> None:
        w.html(render(self.apps))
