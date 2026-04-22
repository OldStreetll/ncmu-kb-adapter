import json

import httpx


BASE = "http://fastgpt-test"
SEARCH_URL = f"{BASE}/api/core/dataset/searchTest"
COLLECTION_LIST_URL = f"{BASE}/api/core/dataset/collection/list"


async def test_retrieval_normal_without_metadata(client, bearer, respx_mock):
    route = respx_mock.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "data": [
                    {"q": "chunk 1 body", "score": 0.91, "source": "a.md"},
                    {"q": "chunk 2 body", "score": 0.82, "source": "b.md"},
                    {"q": "chunk 3 body", "score": 0.75, "source": "c.md"},
                ],
            },
        )
    )
    resp = await client.post(
        "/retrieval",
        headers=bearer,
        json={
            "knowledge_id": "kb-1",
            "query": "hello",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["records"]) == 3
    first = body["records"][0]
    assert first["content"] == "chunk 1 body"
    assert first["score"] == 0.91
    assert first["title"] == "a.md"
    assert first["metadata"] == {}
    assert route.called

    sent = route.calls.last.request.read().decode()
    assert '"datasetId":"kb-1"' in sent or '"datasetId": "kb-1"' in sent
    assert '"text":"hello"' in sent or '"text": "hello"' in sent
    assert "collectionIds" not in sent


async def test_retrieval_explicit_null_metadata_condition(client, bearer, respx_mock):
    """Dify may send `metadata_condition: null` literally; Pydantic must accept it
    and the handler must follow the Test 1 path (no collectionIds filter)."""
    route = respx_mock.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={"code": 200, "data": [{"q": "ok", "score": 0.7, "source": "x.md"}]},
        )
    )
    resp = await client.post(
        "/retrieval",
        headers=bearer,
        json={
            "knowledge_id": "kb-1",
            "query": "hello",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
            "metadata_condition": None,
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["records"][0]["content"] == "ok"
    sent = route.calls.last.request.read().decode()
    assert "collectionIds" not in sent


async def test_retrieval_filename_contains_translates_to_collection_ids(
    client, bearer, respx_mock
):
    """filename contains X should: (1) hit FastGPT collection/list, (2) pick the
    matching collection ids, (3) forward them to /searchTest as collectionIds."""
    collection_list = respx_mock.post(COLLECTION_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "list": [
                        {"_id": "col-manual-1", "name": "operations-manual-v1.pdf"},
                        {"_id": "col-manual-2", "name": "product-manual-2025.md"},
                        {"_id": "col-other", "name": "readme.md"},
                    ],
                    "total": 3,
                },
            },
        )
    )
    search = respx_mock.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "data": [{"q": "filtered", "score": 0.88, "source": "operations-manual-v1.pdf"}],
            },
        )
    )

    resp = await client.post(
        "/retrieval",
        headers=bearer,
        json={
            "knowledge_id": "kb-1",
            "query": "how to reboot",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
            "metadata_condition": {
                "logical_operator": "and",
                "conditions": [
                    {
                        "name": ["filename"],
                        "comparison_operator": "contains",
                        "value": "manual",
                    }
                ],
            },
        },
    )

    assert resp.status_code == 200, resp.text
    assert collection_list.called
    assert search.called

    sent_search_body = json.loads(search.calls.last.request.read())
    assert sent_search_body["datasetId"] == "kb-1"
    assert sent_search_body["collectionIds"] == ["col-manual-1", "col-manual-2"]
    assert sent_search_body["text"] == "how to reboot"


async def test_retrieval_filter_matches_zero_collections_returns_empty(
    client, bearer, respx_mock
):
    """When the filter is applied but no collection matches, we must short-circuit
    with an empty records list and NEVER hit /searchTest."""
    respx_mock.post(COLLECTION_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "list": [{"_id": "col-readme", "name": "readme.md"}],
                    "total": 1,
                },
            },
        )
    )
    search = respx_mock.post(SEARCH_URL).mock(
        return_value=httpx.Response(500, json={"code": 500})
    )

    resp = await client.post(
        "/retrieval",
        headers=bearer,
        json={
            "knowledge_id": "kb-1",
            "query": "hello",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
            "metadata_condition": {
                "conditions": [
                    {"name": ["filename"], "comparison_operator": "contains", "value": "manual"}
                ],
            },
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"records": []}
    assert not search.called


async def test_fastgpt_timeout_returns_504(client, bearer, respx_mock):
    """When the FastGPT call times out, kb-adapter must return HTTP 504 with a
    top-level body ``{"error_code": "fastgpt_timeout"}`` (spec §10.5.5 Test 4).
    NOTE: §10.5.5 uses a string error_code here whereas §10.5.4's 1001/1002/2001
    are integers. This test follows §10.5.5 verbatim; the inconsistency is
    flagged in README for Pane 5 to adjudicate."""
    respx_mock.post(SEARCH_URL).mock(side_effect=httpx.ConnectTimeout("simulated timeout"))

    resp = await client.post(
        "/retrieval",
        headers=bearer,
        json={
            "knowledge_id": "kb-1",
            "query": "hello",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
        },
    )

    assert resp.status_code == 504, resp.text
    body = resp.json()
    assert body == {"error_code": "fastgpt_timeout"}
    assert "detail" not in body
