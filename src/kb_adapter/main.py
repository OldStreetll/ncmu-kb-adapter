"""FastAPI app: Dify External KB → FastGPT retrieval adapter.

Endpoint: ``POST /retrieval``. Flow: verify bearer → translate
``metadata_condition`` to FastGPT ``collectionIds`` (if possible) → call
FastGPT ``/searchTest`` → rewrite response to Dify schema.
"""

from typing import Optional

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from .auth import DifyError, dify_error, verify_bearer
from .fastgpt_client import FastGPTClient, client_from_env
from .models import DifyRetrievalRequest


_FASTGPT_RESERVED = {"q", "a", "source", "score"}


def create_app(client_factory=client_from_env) -> FastAPI:
    app = FastAPI(title="ncmu-kb-adapter")

    @app.exception_handler(DifyError)
    async def _dify_error_handler(_: Request, exc: DifyError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.body)

    @app.post("/retrieval")
    async def retrieval(
        body: DifyRetrievalRequest,
        authorization: Optional[str] = Header(default=None),
    ):
        verify_bearer(authorization)
        client = client_factory()
        return await _do_retrieval(body, client)

    return app


async def _do_retrieval(body: DifyRetrievalRequest, client: FastGPTClient) -> dict:
    collection_ids = None  # metadata translation lands in Test 3
    try:
        fastgpt_resp = await client.search_test(
            dataset_id=body.knowledge_id,
            text=body.query,
            limit=body.retrieval_setting.top_k,
            similarity=body.retrieval_setting.score_threshold,
            collection_ids=collection_ids,
        )
    except httpx.TimeoutException:
        raise dify_error("fastgpt_timeout", 504)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise dify_error(2001, 404, f"Knowledge {body.knowledge_id} not found")
        raise dify_error("fastgpt_upstream", 502, f"upstream {exc.response.status_code}")

    return {"records": [_to_record(item) for item in fastgpt_resp.get("data", [])]}


def _to_record(item: dict) -> dict:
    metadata = {k: v for k, v in item.items() if k not in _FASTGPT_RESERVED}
    return {
        "content": item.get("q", ""),
        "score": item.get("score"),
        "title": item.get("source", ""),
        "metadata": metadata,
    }


app = create_app()
