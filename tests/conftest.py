"""Shared pytest fixtures for kb-adapter tests."""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("KB_ADAPTER_ALLOWED_KEYS", "dev-key-1,dev-key-2")
    monkeypatch.setenv("FASTGPT_BASE_URL", "http://fastgpt-test")
    monkeypatch.setenv("FASTGPT_API_KEY", "fg-test-key")


@pytest.fixture
async def client():
    from kb_adapter.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def bearer():
    return {"Authorization": "Bearer dev-key-1"}
