import os
import re
from dataclasses import dataclass
from pathlib import Path

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


def require_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise ValueError(f"{key} must be set: nudgethis does not run without sign-in")
    return value


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
    repo_base: str
    yard_url: str
    domain: str
    template: str
    yard_token: str
    google_client_id: str
    google_client_secret: str
    session_secret: bytes
    allowed_emails: frozenset[str]
    public_url: str

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
        return cls(
            apps=parse_apps(os.environ.get("NUDGE_APPS", "stario-site=https://stario.dev")),
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
            cursor_model=os.environ.get("CURSOR_MODEL", "").strip(),
            repo_base=os.environ.get("NUDGE_REPO_BASE", "https://github.com/Bobowski").rstrip("/"),
            yard_url=os.environ.get("YARD_URL", "https://yard.bobowski.dev").rstrip("/"),
            yard_token=os.environ.get("YARD_TOKEN", "").strip(),
            domain=os.environ.get("NUDGE_DOMAIN", "wrati.dev").strip(),
            template=os.environ.get(
                "NUDGE_TEMPLATE", "https://github.com/Bobowski/nudge-template"
            ).rstrip("/"),
            google_client_id=require_env("GOOGLE_CLIENT_ID"),
            google_client_secret=require_env("GOOGLE_CLIENT_SECRET"),
            session_secret=require_env("SESSION_SECRET").encode(),
            allowed_emails=frozenset(
                e.strip().lower()
                for e in require_env("NUDGE_ALLOWED_EMAILS").split(",")
                if e.strip()
            ),
            public_url=os.environ.get("NUDGE_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/"),
        )
