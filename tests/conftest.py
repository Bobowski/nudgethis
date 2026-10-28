import pytest
from stario.testing import TestClient

from app.main import bootstrap


def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NUDGE_FAKE_DELAY", "0")
    monkeypatch.setenv("NUDGE_APPS", "alpha=https://alpha.example,beta=https://beta.example")
    # Tests never call the API: a developer's .env may hold a real key.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


@pytest.fixture
async def client(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    async with TestClient(bootstrap, request_timeout=5) as c:
        yield c


@pytest.fixture
def spawn(tmp_path, monkeypatch):
    """Client factory; pass a FunctionModel function to script the model."""
    _env(monkeypatch, tmp_path)

    def make(fn=None):
        if fn is not None:
            from pydantic_ai.models.function import FunctionModel

            from app.nudge.agent import build_agent

            monkeypatch.setattr(
                "app.main.build_agent",
                lambda config: build_agent(config, model=FunctionModel(fn)),
            )
        return TestClient(bootstrap, request_timeout=5)

    return make
