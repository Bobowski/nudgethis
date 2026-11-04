import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

APP_NAME = re.compile(r"[a-z0-9-]+")


def parse_apps(raw: str) -> tuple[tuple[str, str], ...]:
    apps = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        name, sep, url = part.partition("=")
        name, url = name.strip(), url.strip().rstrip("/")
        if not sep or not APP_NAME.fullmatch(name) or not url.startswith(("http://", "https://")):
            raise ValueError(f"NUDGE_APPS entry must be name=http(s)://…: {part!r}")
        apps.append((name, url))
    return tuple(apps)


EFFORTS = ("none", "low", "medium", "high")
CURSOR_MODEL = re.compile(r"[a-z0-9][a-z0-9.-]*(:[a-z_]+=[a-z0-9.]+(,[a-z_]+=[a-z0-9.]+)*)?")


def parse_cursor_model(raw: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    """`grok-4.7:context=256k,reasoning_effort=high`: the model id and its params."""
    if raw and not CURSOR_MODEL.fullmatch(raw):
        raise ValueError(f"CURSOR_MODEL must be id or id:key=value,key=value: {raw!r}")
    model, _, params = raw.partition(":")
    return model, tuple(
        (key, value) for key, _, value in (p.partition("=") for p in params.split(",") if p)
    )


def require_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise ValueError(f"{key} must be set: nudgethis does not run without sign-in")
    return value


def load_session_secret(data_dir: Path) -> bytes:
    """SESSION_SECRET, or one made on the first start and kept in the data directory,
    which survives every deploy. It signs the cookie and seals the saved tokens."""
    value = os.environ.get("SESSION_SECRET", "").strip()
    if value:
        return value.encode()
    path = data_dir / "session_secret"
    if not path.is_file():
        path.touch(mode=0o600)
        path.write_text(secrets.token_urlsafe(48))
    return path.read_text().strip().encode()


def default_domain(public_url: str) -> str:
    """New apps live under nudgethis's own host: nudge.example.com gives
    <name>.nudge.example.com. No default on a laptop."""
    host = urlsplit(public_url).hostname or ""
    return "" if host in ("localhost", "127.0.0.1", "::1") or "." not in host else host


@dataclass(frozen=True, slots=True)
class Config:
    apps: tuple[tuple[str, str], ...]
    fake_delay: float
    data_dir: Path
    db_path: Path
    shots_dir: Path
    openai_api_key: str
    openai_base_url: str | None
    model: str
    effort: str
    history: int
    timeout: float
    cursor_api_key: str
    cursor_model: str
    cursor_params: tuple[tuple[str, str], ...]
    repo_base: str
    yard_url: str
    domain: str
    owner: str
    template: str
    yard_token: str
    google_client_id: str
    google_client_secret: str
    session_secret: bytes
    allowed_emails: frozenset[str]
    public_url: str

    @property
    def origin(self) -> str:
        """nudgethis's own origin, the one a framed app answers."""
        return "{0.scheme}://{0.netloc}".format(urlsplit(self.public_url))

    @classmethod
    def from_env(cls) -> Config:
        # Yard sets PROJECT_DATA_DIR=/data, a host directory that survives every deploy.
        data_dir = Path(os.environ.get("PROJECT_DATA_DIR", "data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        shots_dir = data_dir / "shots"
        shots_dir.mkdir(exist_ok=True)
        effort = os.environ.get("NUDGE_EFFORT", "low").strip()
        if effort not in EFFORTS:
            raise ValueError(f"NUDGE_EFFORT must be one of {EFFORTS}: {effort!r}")
        cursor_model, cursor_params = parse_cursor_model(os.environ.get("CURSOR_MODEL", "").strip())
        public_url = os.environ.get("NUDGE_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
        return cls(
            cursor_model=cursor_model,
            cursor_params=cursor_params,
            apps=parse_apps(os.environ.get("NUDGE_APPS", "")),
            fake_delay=float(os.environ.get("NUDGE_FAKE_DELAY", "4")),
            data_dir=data_dir,
            db_path=data_dir / "nudgethis.sqlite3",
            shots_dir=shots_dir,
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            openai_base_url=os.environ.get("OPENAI_BASE_URL") or None,
            model=os.environ.get("NUDGE_MODEL", "gpt-6.1-terra").strip() or "gpt-6.1-terra",
            effort=effort,
            history=int(os.environ.get("NUDGE_HISTORY", "30")),
            timeout=float(os.environ.get("NUDGE_TIMEOUT", "60")),
            cursor_api_key=os.environ.get("CURSOR_API_KEY", "").strip(),
            # Yard knows the repo of each app it runs; this is for an app it does not.
            repo_base=os.environ.get("NUDGE_REPO_BASE", "").strip().rstrip("/"),
            # Yard's own container on the `yard` podman network: an app on the Yard host
            # cannot reach the host's public address.
            yard_url=os.environ.get("YARD_URL", "http://yard-app-1:8000").rstrip("/"),
            yard_token=os.environ.get("YARD_TOKEN", "").strip(),
            domain=os.environ.get("NUDGE_DOMAIN", "").strip() or default_domain(public_url),
            # The GitHub account of new repos; empty: the one account Yard's app is on.
            owner=os.environ.get("NUDGE_OWNER", "").strip(),
            template=os.environ.get(
                "NUDGE_TEMPLATE", "https://github.com/Bobowski/nudge-template"
            ).rstrip("/"),
            google_client_id=require_env("GOOGLE_CLIENT_ID"),
            google_client_secret=require_env("GOOGLE_CLIENT_SECRET"),
            session_secret=load_session_secret(data_dir),
            allowed_emails=frozenset(
                e.strip().lower()
                for e in require_env("NUDGE_ALLOWED_EMAILS").split(",")
                if e.strip()
            ),
            public_url=public_url,
        )
