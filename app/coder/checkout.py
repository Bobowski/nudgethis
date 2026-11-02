"""The local loop: a clone of the app on this machine follows each change.

The app's own dev server (`just dev`) reloads when git switches the files. The
frame waits until the server answers again, then reloads.
"""

import asyncio
from pathlib import Path

import httpx

from app.coder import CoderError

RESTART = 1.5


async def git(path: Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    if proc.returncode:
        raise CoderError(f"git {args[0]} in {path.name}: {err.decode().strip()[:200]}")
    return out.decode()


async def preview(path: Path, branch: str) -> None:
    if (await git(path, "status", "--porcelain", "--untracked-files=no")).strip():
        raise CoderError(f"{path.name} has uncommitted changes, so it stays on its branch")
    await git(path, "fetch", "origin", branch)
    await git(path, "switch", "--detach", "FETCH_HEAD")


async def back(path: Path) -> None:
    await git(path, "switch", "main")
    await git(path, "pull", "--ff-only")


async def answers(http: httpx.AsyncClient, url: str, timeout: float = 30) -> bool:
    await asyncio.sleep(RESTART)
    try:
        async with asyncio.timeout(timeout):
            while True:
                try:
                    if (await http.get(url)).status_code < 500:
                        return True
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
    except TimeoutError:
        return False
