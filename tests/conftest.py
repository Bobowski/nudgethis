import pytest
from stario.testing import TestClient

from app.main import bootstrap


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NUDGE_FAKE_DELAY", "0")
    monkeypatch.setenv("NUDGE_APPS", "alpha=https://alpha.example,beta=https://beta.example")
    async with TestClient(bootstrap, request_timeout=5) as c:
        yield c
