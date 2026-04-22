import httpx


BASE = "http://fastgpt-test"
SEARCH_URL = f"{BASE}/api/core/dataset/searchTest"


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
