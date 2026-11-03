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
from app.features.frame import data as frame_store
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
        return render(
            self.config.apps,
            made,
            self.config.domain,
            self.yard is not None,
            frame_store.get_colors(self.db),
        )

    async def show(self, c: Context, w: Writer) -> None:
        w.html(self.page(self.db.query(store.APPS_SQL)))

    async def live(self, c: Context, w: Writer) -> None:
        sse = SSE(w)
        async with self.db.watch(store.APPS_SQL) as rows:
            async for made in c.alive(rows):
                sse.patch_elements(self.page(made))

    async def new_app(self, c: Context, w: Writer) -> None:
        signals = await read_signals(c.req)
        label = str(signals.get("new_name", "")).strip().lower()
        start_from = str(signals.get("new_from", "")).strip()
        source = github.source_of(start_from) if start_from else None
        sse = SSE(w)
        if self.yard is None:
            sse.patch_signals({"_toast": "Set YARD_TOKEN to make apps."})
            return
        if not NAME.fullmatch(label) or label in RESERVED:
            sse.patch_signals({"_toast": "A name is 2 to 30 lowercase letters, digits, or -."})
            return
        if start_from and source is None:
            sse.patch_signals(
                {"_toast": "Start from a public GitHub repo: https://github.com/owner/name"}
            )
            return
        name = f"nudge-{label}"
        made = store.get_app(self.db, name)
        if name in dict(self.config.apps) or (made is not None and made[1] != "failed"):
            sse.patch_signals({"_toast": f"{label} exists."})
            return
        sse.patch_signals({"new_name": "", "new_from": ""})
        url = f"https://{label}.{self.config.domain}"
        await self.db.write(store.add_app, name, url)
        c.app.create_task(self.make(name, url, source, c.span.step("nudge.new_app")))

    async def make(self, name: str, url: str, source: str | None, span: Span) -> None:
        """A repo from the template (or a public repo), a Yard app whose site only nudgethis
        may frame, a deploy."""
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
            span.attrs({"app.name": name, "app.source": source or template})
            try:
                files = None
                if source is not None:
                    # Read it first: a wrong URL fails before anything is made.
                    await self.db.write(store.set_app, name, "creating", f"Reading {source}")
                    files = await github.public_files(self.http, source)
                await self.db.write(store.set_app, name, "creating", "Making the repo")
                repo = await yard.create_repo(name)
                await self.db.write(store.set_app, name, "creating", "Copying the template")
                write = await yard.repo_token(repo)
                if files is None:
                    read = await yard.repo_token(template)
                    files = await github.template_files(self.http, template, read, name)
                await github.write_files(
                    self.http, files, repo, write, name, source or github.full_name(template)
                )
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
            except Exception as exc:
                # A row left on a step would look stuck until the next restart.
                why = f"{type(exc).__name__}: {exc}"
                await self.db.write(store.set_app, name, "failed", why)
                span.fail(why)
                return
            await self.db.write(store.set_app, name, "ready", "")
