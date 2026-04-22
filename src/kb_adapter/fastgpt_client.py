"""Thin async HTTP client for the FastGPT REST API.

Exposes the two endpoints kb-adapter needs: ``/api/core/dataset/searchTest``
for retrieval, and ``/api/core/dataset/collection/list`` for collectionIds
translation (spec §10.5.4).
"""

import os
from typing import Any, Optional

import httpx


DEFAULT_TIMEOUT = 10.0


class FastGPTClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = DEFAULT_TIMEOUT):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._timeout = timeout

    async def search_test(
        self,
        *,
        dataset_id: str,
        text: str,
        limit: int,
        similarity: float,
        collection_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "datasetId": dataset_id,
            "text": text,
            "limit": limit,
            "similarity": similarity,
            "searchMode": "embedding",
        }
        if collection_ids is not None:
            payload["collectionIds"] = collection_ids
        return await self._post("/api/core/dataset/searchTest", payload)

    async def list_collections(self, dataset_id: str) -> dict[str, Any]:
        payload = {"datasetId": dataset_id, "pageSize": 200, "pageNum": 1}
        return await self._post("/api/core/dataset/collection/list", payload)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            resp = await http.post(
                f"{self._base_url}{path}",
                json=payload,
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()


def client_from_env() -> FastGPTClient:
    return FastGPTClient(
        base_url=os.environ["FASTGPT_BASE_URL"],
        api_key=os.environ["FASTGPT_API_KEY"],
    )
