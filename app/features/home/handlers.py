from dataclasses import dataclass

from stario import App, Context, Middleware, Writer

from app.features.home.urls import HOME
from app.features.home.views import render


@dataclass(frozen=True, slots=True)
class HomePage:
    apps: tuple[tuple[str, str], ...]
    signed_in: Middleware

    def register(self, app: App) -> None:
        app.add(HOME, self.show, middleware=[self.signed_in])

    async def show(self, c: Context, w: Writer) -> None:
        w.html(render(self.apps))
