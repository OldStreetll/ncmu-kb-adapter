"""B-NEW-08 regression: the ``strip_via_header`` middleware must remove any
``Via`` response header on 200, 4xx, and 5xx alike.

A trivial ``assert 'via' not in response.headers`` would pass even WITHOUT the
middleware because FastAPI/Starlette never emit a Via header by default, so
these tests register test-only routes that explicitly set
``Via: 1.1 squid`` on their responses. That turns the middleware's
``response.headers.pop('Via', None)`` into the only thing standing between a
Via-tagged origin response and the test assertion — i.e. the coverage becomes
meaningful.
"""

from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from kb_adapter.main import create_app


def _app_with_via_echoing_routes():
    app = create_app()

    @app.get("/__via_200")
    async def _ok():
        return JSONResponse({"ok": True}, status_code=200, headers={"Via": "1.1 squid"})

    @app.get("/__via_403")
    async def _forbidden():
        return JSONResponse(
            {"error_code": 1001, "error_msg": "forced for test"},
            status_code=403,
            headers={"Via": "1.1 squid"},
        )

    @app.get("/__via_500")
    async def _server_error():
        return JSONResponse(
            {"error_code": "fastgpt_upstream", "error_msg": "forced for test"},
            status_code=500,
            headers={"Via": "1.1 squid"},
        )

    return app


async def _get(path: str):
    app = _app_with_via_echoing_routes()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        return await ac.get(path)


async def test_via_header_stripped_on_200():
    r = await _get("/__via_200")
    assert r.status_code == 200
    assert "via" not in {k.lower() for k in r.headers.keys()}


async def test_via_header_stripped_on_4xx():
    r = await _get("/__via_403")
    assert r.status_code == 403
    assert "via" not in {k.lower() for k in r.headers.keys()}


async def test_via_header_stripped_on_5xx():
    r = await _get("/__via_500")
    assert r.status_code == 500
    assert "via" not in {k.lower() for k in r.headers.keys()}
