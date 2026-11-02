"""Copy the template repo into a new, empty repo through GitHub's API, with Yard's tokens."""

import base64
from typing import Any

import httpx

from app.coder import CoderError

API = "https://api.github.com"
# The files of the template that name the app `starter`.
NAMED = ("pyproject.toml", "app/config.py", "uv.lock")


async def call(http: httpx.AsyncClient, token: str, method: str, path: str, body=None) -> Any:
    r = await http.request(
        method,
        API + path,
        json=body,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    if r.status_code >= 400:
        raise CoderError(f"GitHub answered {r.status_code}: {r.text[:200]}")
    return r.json()


def full_name(repo: str) -> str:
    """owner/name of an https://github.com/owner/name URL."""
    return repo.removeprefix("https://github.com/").removesuffix(".git").strip("/")


async def copy_template(
    http: httpx.AsyncClient, template: str, read: str, repo: str, write: str, name: str
) -> None:
    src, dst = full_name(template), full_name(repo)
    tree = (await call(http, read, "GET", f"/repos/{src}/git/trees/main?recursive=1"))["tree"]
    readme = f"# {name}\n\nMade by nudgethis from nudge-template.\n".encode()
    # An empty repo takes no git objects: the README makes main through the contents API.
    first = await call(
        http,
        write,
        "PUT",
        f"/repos/{dst}/contents/README.md",
        {"message": "Start from nudge-template", "content": base64.b64encode(readme).decode()},
    )
    entries = []
    for item in tree:
        if item["type"] != "blob" or item["path"] == "README.md":
            continue
        blob = await call(http, read, "GET", f"/repos/{src}/git/blobs/{item['sha']}")
        content = base64.b64decode(blob["content"])
        if item["path"] in NAMED:
            content = content.replace(b'"starter"', f'"{name}"'.encode())
        made = await call(
            http,
            write,
            "POST",
            f"/repos/{dst}/git/blobs",
            {"content": base64.b64encode(content).decode(), "encoding": "base64"},
        )
        entries.append(
            {"path": item["path"], "mode": item["mode"], "type": "blob", "sha": made["sha"]}
        )
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
            "message": "Copy nudge-template",
            "tree": new_tree["sha"],
            "parents": [first["commit"]["sha"]],
        },
    )
    await call(http, write, "PATCH", f"/repos/{dst}/git/refs/heads/main", {"sha": commit["sha"]})
