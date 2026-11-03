import pytest

from app.config import Config, default_domain


def env(monkeypatch, tmp_path, **extra):
    monkeypatch.setenv("PROJECT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("NUDGE_ALLOWED_EMAILS", "ada@example.com")
    for key in ("SESSION_SECRET", "NUDGE_DOMAIN", "NUDGE_PUBLIC_URL", "NUDGE_APPS"):
        monkeypatch.delenv(key, raising=False)
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_without_session_secret_one_is_made_once_and_kept(monkeypatch, tmp_path):
    env(monkeypatch, tmp_path)
    first = Config.from_env().session_secret
    assert len(first) >= 32
    assert (tmp_path / "session_secret").stat().st_mode & 0o077 == 0
    assert Config.from_env().session_secret == first


def test_session_secret_from_the_env_wins(monkeypatch, tmp_path):
    env(monkeypatch, tmp_path, SESSION_SECRET="x" * 40)
    assert Config.from_env().session_secret == b"x" * 40
    assert not (tmp_path / "session_secret").exists()


def test_sign_in_is_required(monkeypatch, tmp_path):
    env(monkeypatch, tmp_path)
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    with pytest.raises(ValueError, match="GOOGLE_CLIENT_ID"):
        Config.from_env()


def test_new_apps_live_under_the_public_host_by_default(monkeypatch, tmp_path):
    env(monkeypatch, tmp_path, NUDGE_PUBLIC_URL="https://nudge.example.com/")
    config = Config.from_env()
    assert config.domain == "nudge.example.com"
    assert config.origin == "https://nudge.example.com"
    assert config.apps == ()
    env(monkeypatch, tmp_path, NUDGE_PUBLIC_URL="https://nudge.example.com", NUDGE_DOMAIN="x.dev")
    assert Config.from_env().domain == "x.dev"


@pytest.mark.parametrize(
    ("url", "domain"),
    [
        ("http://127.0.0.1:8000", ""),
        ("http://localhost:8000", ""),
        ("https://wrati.dev", "wrati.dev"),
        ("https://nudge.example.com:8443", "nudge.example.com"),
    ],
)
def test_default_domain(url, domain):
    assert default_domain(url) == domain
