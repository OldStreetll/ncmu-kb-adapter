"""Phase 1 multi-Key contract tests.

Pins three invariants against kb-adapter real code so a future refactor cannot
silently reverse the mapping again (the N-1 / A-2 修订 history in errata-08
documents how plan-side drafts inverted these twice before):

1. ``KB_ADAPTER_ALLOWED_KEYS`` is split on ``,`` and each token stands alone
   (A-2 修订: see ``auth.py:31-33``). There is no ``label:token`` scheme.
2. Missing Authorization header, or a non-``Bearer`` scheme, surfaces as
   ``error_code=1001`` / HTTP 403 (``auth.py:37-38``).
3. Well-formed ``Bearer`` with a token absent from the allowlist surfaces as
   ``error_code=1002`` / HTTP 403 (``auth.py:40-41``).
"""

import httpx
from httpx import ASGITransport, AsyncClient

from kb_adapter.main import create_app


_FASTGPT_SEARCH_URL = "http://fastgpt-test/api/core/dataset/searchTest"


async def _post_retrieval(headers=None):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        return await ac.post(
            "/retrieval",
            headers=headers or {},
            json={
                "knowledge_id": "kb-1",
                "query": "hello",
                "retrieval_setting": {"top_k": 3, "score_threshold": 0.5},
            },
        )


async def test_multi_key_both_tokens_pass(monkeypatch, respx_mock):
    """A-2 修订 pin: comma-separated plain tokens, not label:token pairs.
    Both tokens in the allowlist must reach FastGPT and return HTTP 200."""
    monkeypatch.setenv("KB_ADAPTER_ALLOWED_KEYS", "hrabc,finabc")
    respx_mock.post(_FASTGPT_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={"code": 200, "data": {"list": []}},
        )
    )

    for token in ("hrabc", "finabc"):
        r = await _post_retrieval(headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"token {token!r}: {r.status_code} {r.text}"
        assert r.json() == {"records": []}


async def test_bearer_format_error_returns_1001(monkeypatch, respx_mock):
    """N-1 修订 pin: Bearer prefix missing or wrong scheme → 1001 (not 1002).
    Must NOT reach FastGPT."""
    monkeypatch.setenv("KB_ADAPTER_ALLOWED_KEYS", "hrabc,finabc")
    search = respx_mock.post(_FASTGPT_SEARCH_URL)

    r = await _post_retrieval(headers=None)
    assert r.status_code == 403
    assert r.json()["error_code"] == 1001
    assert "error_msg" in r.json()

    r = await _post_retrieval(headers={"Authorization": "Token hrabc"})
    assert r.status_code == 403
    assert r.json()["error_code"] == 1001

    assert not search.called, "1001 path must short-circuit before FastGPT"


async def test_bearer_token_not_in_allowlist_returns_1002(monkeypatch, respx_mock):
    """N-1 修订 pin: Bearer format OK but token absent from ALLOWED_KEYS →
    1002 (not 1001). Must NOT reach FastGPT. The 1001 vs 1002 split matters
    because Dify surfaces different user-facing messages per spec §10.5.4."""
    monkeypatch.setenv("KB_ADAPTER_ALLOWED_KEYS", "hrabc,finabc")
    search = respx_mock.post(_FASTGPT_SEARCH_URL)

    r = await _post_retrieval(headers={"Authorization": "Bearer wrongkey"})
    assert r.status_code == 403
    body = r.json()
    assert body["error_code"] == 1002
    assert "error_msg" in body

    assert not search.called, "1002 path must short-circuit before FastGPT"
