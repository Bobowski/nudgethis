import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from litewriter import LiteWriter
from stario import App, Context, Middleware, Span, Writer
from stario.datastar import SSE, read_signals

from app.builder import Builder
from app.coder import CoderError, github
from app.coder.yard import Yard
from app.config import Config
from app.features.frame import data as frame_store
from app.features.home import data as store
from app.features.home.urls import HOME, HOME_LIVE, NEW_APP, REMOVE_APP, SUGGEST
from app.features.home.views import render

# The name becomes the host <name>.<domain> and the repo nudge-<name>.
NAME = re.compile(r"[a-z][a-z0-9-]{0,28}[a-z0-9]")
RESERVED = {"www", "api", "app", "auth", "yard", "mail", "static", "admin"}
# A GitHub link in the prompt: the app starts from that repo.
LINK = re.compile(r"https?://github\.com/\S+")
# Words that say little about an app, left out of the name made from a prompt.
FILLER = set(
    "a an the for my our your with and or to of in on at by that this it its is are be "
    "can could would should will i me we us you app apps simple small little tiny "
    "page site website tool thing where what who which want make build need".split()
)


def split_prompt(prompt: str) -> tuple[str, str | None, bool]:
    """The description without its GitHub link, the repo to start from, and whether
    a link was there at all (a link that is not a repo is a mistake to say)."""
    found = LINK.search(prompt)
    if not found:
        return " ".join(prompt.split()), None, False
    link = found.group(0).rstrip(".,;:!?)")
    about = " ".join((prompt[: found.start()] + " " + prompt[found.end() :]).split())
    return about, github.source_of(link), True


def slug_of(about: str, source: str | None) -> str:
    """A short name from what the app is: its first telling words, or the repo's name."""
    words = re.findall(r"[a-z0-9]+", about.lower())
    keep = [w for w in words if w not in FILLER][:2]
    if not keep and source:
        keep = re.findall(r"[a-z0-9]+", source.rsplit("/", 1)[1].lower())[:2]
    label = "-".join(keep)[:30].strip("-") or "app"
    return label if label[0].isalpha() else f"app-{label}"[:30]


FIRST_DEPLOY_TIMEOUT = 900


@dataclass(frozen=True, slots=True)
class HomePage:
    db: LiteWriter
    builder: Builder
    http: httpx.AsyncClient
    signed_in: Middleware
    # The frame asks Nudge for a new app's first request: its description.
    first_request: Callable[[App, Span, str, str], Awaitable[None]]

    @property
    def config(self) -> Config:
        return self.builder.config

    @property
    def yard(self) -> Yard | None:
        return self.builder.yard

    def register(self, app: App) -> None:
        for route, handler in (
            (HOME, self.show),
            (HOME_LIVE, self.live),
            (NEW_APP, self.new_app),
            (SUGGEST, self.suggest),
            (REMOVE_APP, self.remove_app),
        ):
            app.add(route, handler, middleware=[self.signed_in])

    def taken(self, label: str) -> bool:
        name = f"nudge-{label}"
        made = store.get_app(self.db, name)
        return (
            label in RESERVED
            or name in dict(self.config.apps)
            or (made is not None and made[1] != "failed")
        )

    def free_label(self, label: str) -> str:
        """The label, or label-2, label-3, ... when it is taken."""
        if not self.taken(label):
            return label
        n = 2
        while self.taken(f"{label[:27]}-{n}"):
            n += 1
        return f"{label[:27]}-{n}"

    async def suggest(self, c: Context, w: Writer) -> None:
        """As the person types: the name the app would get, and where it starts from."""
        prompt = str((await read_signals(c.req)).get("new_about", ""))[:2000]
        about, source, _ = split_prompt(prompt)
        SSE(w).patch_signals(
            {
                "_hint": self.free_label(slug_of(about, source)) if about or source else "",
                "_from": github.full_name(source) if source else "",
            }
        )

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
        prompt = str(signals.get("new_about", "")).strip()
        typed = str(signals.get("new_name", "")).strip().lower()
        sse = SSE(w)
        if self.yard is None:
            sse.patch_signals({"_toast": "Set YARD_TOKEN to make apps."})
            return
        if len(prompt) > 2000:
            sse.patch_signals({"_toast": "Keep the description under 2000 characters."})
            return
        about, source, linked = split_prompt(prompt)
        if linked and source is None:
            sse.patch_signals(
                {"_toast": "Link a public GitHub repo: https://github.com/owner/name"}
            )
            return
        if not about and source is None and not typed:
            sse.patch_signals({"_toast": "Say what you want to make."})
            return
        label = typed or self.free_label(slug_of(about, source))
        if not NAME.fullmatch(label) or label in RESERVED:
            sse.patch_signals({"_toast": "A name is 2 to 30 lowercase letters, digits, or -."})
            return
        if self.taken(label):
            sse.patch_signals({"_toast": f"{label} exists."})
            return
        name = f"nudge-{label}"
        sse.patch_signals({"new_name": "", "new_about": "", "_hint": "", "_from": ""})
        url = f"https://{label}.{self.config.domain}"
        await self.db.write(store.add_app, name, url)
        c.app.create_task(self.make(c.app, name, url, source, about, c.span.step("nudge.new_app")))

    async def make(
        self, app: App, name: str, url: str, source: str | None, about: str, span: Span
    ) -> None:
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
            if about:
                # The description is the app's first request, in its own chat.
                await self.first_request(app, span, name, about)

    async def remove_app(self, c: Context, w: Writer) -> None:
        """An app nudgethis made leaves the list, with its chat and its changes. Its repo
        and its Yard app stay: nudgethis does not delete code or a running site."""
        name = str((await read_signals(c.req)).get("remove_name", ""))
        made = store.get_app(self.db, name)
        if made is None:
            w.text("only an app that nudgethis made can be removed", status=404)
            return
        if made[1] == "creating":
            w.text("it is still being made", status=409)
            return
        if frame_store.busy(self.db, name):
            w.text("a change of it is still working", status=409)
            return
        w.empty()
        await self.db.write(remove_everything, name)


def remove_everything(tx, name: str) -> None:
    store.remove_app(tx, name)
    frame_store.remove_app(tx, name)
