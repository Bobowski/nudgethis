import asyncio
import re
from dataclasses import dataclass

import httpx
from litewriter import LiteWriter
from stario import App, Context, Middleware, Span, Writer
from stario.datastar import SSE, read_signals

from app.coder import CoderError, github
from app.coder.yard import Yard
from app.config import Config
from app.features.home import data as store
from app.features.home.urls import HOME, HOME_LIVE, NEW_APP
from app.features.home.views import render

# The name becomes the host <name>.<domain> and the repo nudge-<name>.
NAME = re.compile(r"[a-z][a-z0-9-]{0,28}[a-z0-9]")
RESERVED = {"www", "api", "app", "auth", "yard", "mail", "static", "admin"}
FIRST_DEPLOY_TIMEOUT = 900


@dataclass(frozen=True, slots=True)
class HomePage:
    db: LiteWriter
    config: Config
    http: httpx.AsyncClient
    yard: Yard | None
    signed_in: Middleware

    def register(self, app: App) -> None:
        for route, handler in ((HOME, self.show), (HOME_LIVE, self.live), (NEW_APP, self.new_app)):
            app.add(route, handler, middleware=[self.signed_in])

    def page(self, made: list[tuple]):
        return render(self.config.apps, made, self.config.domain, self.yard is not None)

    async def show(self, c: Context, w: Writer) -> None:
        w.html(self.page(self.db.query(store.APPS_SQL)))

    async def live(self, c: Context, w: Writer) -> None:
        sse = SSE(w)
        async with self.db.watch(store.APPS_SQL) as rows:
            async for made in c.alive(rows):
                sse.patch_elements(self.page(made))

    async def new_app(self, c: Context, w: Writer) -> None:
        label = str((await read_signals(c.req)).get("new_name", "")).strip().lower()
        sse = SSE(w)
        if self.yard is None:
            sse.patch_signals({"_toast": "Set YARD_TOKEN to make apps."})
            return
        if not NAME.fullmatch(label) or label in RESERVED:
            sse.patch_signals({"_toast": "A name is 2 to 30 lowercase letters, digits, or -."})
            return
        name = f"nudge-{label}"
        if name in dict(self.config.apps) or store.get_app(self.db, name) is not None:
            sse.patch_signals({"_toast": f"{label} exists."})
            return
        sse.patch_signals({"new_name": ""})
        url = f"https://{label}.{self.config.domain}"
        await self.db.write(store.add_app, name, url)
        c.app.create_task(self.make(name, url, c.span.step("nudge.new_app")))

    async def make(self, name: str, url: str, span: Span) -> None:
        """A repo from the template, a Yard app whose site only nudgethis may frame, a deploy."""
        assert self.yard is not None
        yard, template = self.yard, self.config.template
        site = (
            f"{url.removeprefix('https://')} {{\n"
            "\theader -X-Frame-Options\n"
            f'\theader Content-Security-Policy "frame-ancestors {self.config.public_url}"\n'
            f"\treverse_proxy {name}-app-1:8000 {{\n"
            "\t\tlb_try_duration 10s\n"
            "\t\tlb_try_interval 250ms\n"
            "\t}\n"
            "}\n"
        )
        with span:
            span.attrs({"app.name": name})
            try:
                await self.db.write(store.set_app, name, "creating", "Making the repo")
                repo = await yard.create_repo(name)
                await self.db.write(store.set_app, name, "creating", "Copying the template")
                read, write = await yard.repo_token(template), await yard.repo_token(repo)
                await github.copy_template(self.http, template, read, repo, write, name)
                await self.db.write(store.set_app, name, "creating", "Starting it on Yard")
                await yard.create_app(name, repo, site)
                await self.db.write(store.set_app, name, "creating", "Deploying")
                async with asyncio.timeout(FIRST_DEPLOY_TIMEOUT):
                    deploy = await yard.next_deploy(name, "")
                if deploy.get("status") != "ok":
                    why = deploy.get("error") or deploy.get("status")
                    raise CoderError(f"the first deploy did not go live: {why}")
            except (CoderError, TimeoutError) as exc:
                why = str(exc) or "the first deploy took too long"
                await self.db.write(store.set_app, name, "failed", why)
                span.fail(why)
                return
            await self.db.write(store.set_app, name, "ready", "")
