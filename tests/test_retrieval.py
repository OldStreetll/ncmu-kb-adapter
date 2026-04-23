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
                "data": {
                    "list": [
                        {"q": "chunk 1 body", "score": [{"type": "embedding", "value": 0.91, "index": 0}], "sourceName": "a.md"},
                        {"q": "chunk 2 body", "score": [{"type": "embedding", "value": 0.82, "index": 0}], "sourceName": "b.md"},
                        {"q": "chunk 3 body", "score": [{"type": "embedding", "value": 0.75, "index": 0}], "sourceName": "c.md"},
                    ],
                    "duration": "0.102s",
                    "searchMode": "embedding",
                    "limit": 5,
                },
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
            json={
                "code": 200,
                "data": {
                    "list": [{"q": "ok", "score": [{"type": "embedding", "value": 0.7, "index": 0}], "sourceName": "x.md"}],
                },
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
                "data": {
                    "list": [
                        {"q": "filtered", "score": [{"type": "embedding", "value": 0.88, "index": 0}], "sourceName": "operations-manual-v1.pdf"}
                    ],
                },
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


async def test_retrieval_maps_fastgpt_v4_14_10_2_shape(client, bearer, respx_mock):
    """Explicit REWORK-13 coverage: FastGPT v4.14.10.2 returns
    ``data.list[i]`` with ``sourceName`` (string) and ``score`` (list of
    {type,value,index}). Verify: sourceName → records.title and
    score[0].value → records.score (float), plus non-reserved fields flow
    into metadata while reserved ones do not."""
    respx_mock.post(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "data": {
                    "list": [
                        {
                            "id": "chunk-abc",
                            "q": "E2E-TASK-14-MARKER body text",
                            "a": "answer text",
                            "sourceName": "TASK-14 手册",
                            "score": [
                                {"type": "embedding", "value": 0.5217, "index": 0},
                            ],
                            "chunkIndex": 2,
                        }
                    ],
                    "duration": "0.102s",
                    "searchMode": "embedding",
                    "limit": 3,
                },
            },
        )
    )

    resp = await client.post(
        "/retrieval",
        headers=bearer,
        json={
            "knowledge_id": "kb-1",
            "query": "E2E-TASK-14-MARKER",
            "retrieval_setting": {"top_k": 3, "score_threshold": 0.5},
        },
    )

    assert resp.status_code == 200, resp.text
    records = resp.json()["records"]
    assert len(records) == 1
    rec = records[0]
    assert rec["title"] == "TASK-14 手册"
    assert rec["score"] == 0.5217
    assert isinstance(rec["score"], float)
    assert rec["content"] == "E2E-TASK-14-MARKER body text"
    assert rec["metadata"] == {"id": "chunk-abc", "chunkIndex": 2}


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


async def test_auth_bearer_missing_returns_1001(client, respx_mock):
    """Test 5a: Authorization header absent OR not starting with 'Bearer '
    must return 1001 per Dify spec (§10.5.4 note #3). No FastGPT call."""
    search = respx_mock.post(SEARCH_URL)

    resp = await client.post(
        "/retrieval",
        json={
            "knowledge_id": "kb-1",
            "query": "hello",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
        },
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["error_code"] == 1001
    assert "error_msg" in body
    assert not search.called


async def test_auth_bearer_wrong_prefix_returns_1001(client, respx_mock):
    """Test 5a variant: wrong auth scheme (e.g. 'Basic xxx') also → 1001."""
    search = respx_mock.post(SEARCH_URL)

    resp = await client.post(
        "/retrieval",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
        json={
            "knowledge_id": "kb-1",
            "query": "hello",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
        },
    )

    assert resp.status_code == 403
    assert resp.json()["error_code"] == 1001
    assert not search.called


async def test_fastgpt_404_returns_2001_http_200(client, bearer, respx_mock):
    """Test 6 (REVIEW-13 C2): FastGPT returns 404 (dataset/knowledge_id
    not found). kb-adapter must return HTTP 200 with a Dify-compatible body
    carrying ``error_code=2001`` (int per spec §10.5.4) plus an empty
    ``records`` list so Dify's retrieval flow short-circuits gracefully
    rather than surfacing an HTTP error."""
    respx_mock.post(SEARCH_URL).mock(
        return_value=httpx.Response(404, json={"code": 404, "message": "dataset not found"})
    )

    resp = await client.post(
        "/retrieval",
        headers=bearer,
        json={
            "knowledge_id": "kb-missing",
            "query": "hello",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error_code"] == 2001
    assert isinstance(body["error_code"], int)
    assert "error_msg" in body
    assert body["records"] == []


async def test_auth_token_not_in_allowed_keys_returns_1002(client, respx_mock):
    """Test 5b: Bearer format is correct but token not in
    KB_ADAPTER_ALLOWED_KEYS → 1002 per Dify spec. No FastGPT call."""
    search = respx_mock.post(SEARCH_URL)

    resp = await client.post(
        "/retrieval",
        headers={"Authorization": "Bearer totally-unknown-token"},
        json={
            "knowledge_id": "kb-1",
            "query": "hello",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
        },
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["error_code"] == 1002
    assert "error_msg" in body
    assert not search.called
