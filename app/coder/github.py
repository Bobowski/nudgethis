"""Copy a template into a new, empty repo through GitHub's API, with Yard's tokens: nudge-template,
or any public GitHub repo."""

import asyncio
import base64
import io
import re
import tarfile
from dataclasses import dataclass
from typing import Any

import httpx

from app.coder import CoderError

API = "https://api.github.com"
# The files of the template that name the app `starter`.
NAMED = ("pyproject.toml", "app/config.py", "uv.lock")
# The template's nudge.js answers only the nudgethis whose address is put here.
NUDGE_JS = "static/js/nudge.js"
ORIGIN = "NUDGETHIS_ORIGIN"


class NoRepo(CoderError):
    """No public repo at that address: it is missing, or it is private."""


async def call(http: httpx.AsyncClient, token: str, method: str, path: str, body=None) -> Any:
    try:
        r = await http.request(
            method,
            API + path,
            json=body,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
    except httpx.HTTPError as exc:
        raise CoderError(f"GitHub did not answer: {exc}") from exc
    if r.status_code >= 400:
        raise CoderError(f"GitHub answered {r.status_code}: {r.text[:200]}")
    return r.json()


def full_name(repo: str) -> str:
    """owner/name of an https://github.com/owner/name URL."""
    return repo.removeprefix("https://github.com/").removesuffix(".git").strip("/")


@dataclass(frozen=True, slots=True)
class File:
    path: str
    mode: str  # 100644, 100755, or 120000 (a link, whose content is its target)
    content: bytes


# A public repo is read as one tarball; these keep a huge one out.
MAX_FILES = 3000
MAX_BYTES = 60 * 1024 * 1024
SOURCE = re.compile(r"https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+")


def source_of(url: str) -> str | None:
    """The https://github.com/owner/name of a public repo URL, or None."""
    url = url.strip().removesuffix("/").removesuffix(".git")
    return url if SOURCE.fullmatch(url) else None


async def private_files(http: httpx.AsyncClient, repo: str, read: str) -> list[File]:
    """The files of a private repo's main branch, read with a Yard token."""
    src = full_name(repo)
    tree = (await call(http, read, "GET", f"/repos/{src}/git/trees/main?recursive=1"))["tree"]
    files = []
    for item in tree:
        if item["type"] != "blob" or item["path"] == "README.md":
            continue
        blob = await call(http, read, "GET", f"/repos/{src}/git/blobs/{item['sha']}")
        files.append(File(item["path"], item["mode"], base64.b64decode(blob["content"])))
    return files


def named(files: list[File], name: str, origin: str) -> list[File]:
    """The template's files with the app's name in place of `starter`, and nudgethis's
    address in nudge.js. The template's own LICENSE stays out: the new app is the maker's."""
    out = []
    for f in files:
        if f.path == "LICENSE":
            continue
        content = f.content
        if f.path in NAMED:
            content = content.replace(b'"starter"', f'"{name}"'.encode())
        if f.path == NUDGE_JS:
            content = content.replace(ORIGIN.encode(), origin.encode())
        out.append(File(f.path, f.mode, content))
    return out


def _untar(blob: bytes) -> list[File]:
    files = []
    total = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for member in tar:
            # Each path starts with the archive's own folder (owner-name-sha/).
            _, _, path = member.name.partition("/")
            if not path or path == "README.md" or path.startswith("/") or ".." in path.split("/"):
                continue
            if member.issym():
                files.append(File(path, "120000", member.linkname.encode()))
            elif member.isfile():
                data = tar.extractfile(member)
                content = data.read() if data else b""
                total += len(content)
                mode = "100755" if member.mode & 0o111 else "100644"
                files.append(File(path, mode, content))
            if len(files) > MAX_FILES or total > MAX_BYTES:
                raise CoderError("that repo is too big to start from")
    return files


async def public_files(http: httpx.AsyncClient, source: str) -> list[File]:
    """The files of a public GitHub repo's default branch, in one download."""
    owner_name = full_name(source)
    try:
        r = await http.get(
            f"https://codeload.github.com/{owner_name}/tar.gz/HEAD", follow_redirects=True
        )
    except httpx.HTTPError as exc:
        raise CoderError(f"GitHub did not answer: {exc}") from exc
    if r.status_code == 404:
        raise NoRepo(f"no public repo at {source}")
    if r.status_code >= 400:
        raise CoderError(f"GitHub answered {r.status_code} for {source}")
    try:
        return await asyncio.to_thread(_untar, r.content)
    except (tarfile.TarError, OSError) as exc:
        raise CoderError(f"could not read {source}: {exc}") from exc


async def write_files(
    http: httpx.AsyncClient, files: list[File], repo: str, write: str, name: str, source: str
) -> None:
    """Put the files into the new, empty repo as one commit on main."""
    dst = full_name(repo)
    readme = f"# {name}\n\nMade by nudgethis from {source}.\n".encode()
    # An empty repo takes no git objects: the README makes main through the contents API.
    first = await call(
        http,
        write,
        "PUT",
        f"/repos/{dst}/contents/README.md",
        {"message": f"Start from {source}", "content": base64.b64encode(readme).decode()},
    )
    entries = []
    for f in files:
        made = await call(
            http,
            write,
            "POST",
            f"/repos/{dst}/git/blobs",
            {"content": base64.b64encode(f.content).decode(), "encoding": "base64"},
        )
        entries.append({"path": f.path, "mode": f.mode, "type": "blob", "sha": made["sha"]})
    entries.append(
        {"path": "README.md", "mode": "100644", "type": "blob", "sha": first["content"]["sha"]}
    )
    new_tree = await call(http, write, "POST", f"/repos/{dst}/git/trees", {"tree": entries})
    commit = await call(
        http,
        write,
        "POST",
        f"/repos/{dst}/git/commits",
        {
            "message": f"Copy {source}",
            "tree": new_tree["sha"],
            "parents": [first["commit"]["sha"]],
        },
    )
    await call(http, write, "PATCH", f"/repos/{dst}/git/refs/heads/main", {"sha": commit["sha"]})
