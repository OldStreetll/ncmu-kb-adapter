# ncmu-kb-adapter

NCMU 自研协议转换层：把 Dify External KB API 的检索请求翻译成 FastGPT 数据集检索调用，再把 FastGPT 的命中结果回写成 Dify External KB 响应格式，并在协议边界完成 Bearer 鉴权、`metadata_condition → collectionIds` 过滤、错误码规范化。

## 架构位置

Dify 编排 → (External KB API) → **ncmu-kb-adapter**（本仓，FastAPI，~170 行）→ (FastGPT HTTP API) → FastGPT RAG 层。设计依据：`NCMU-Wiki/architecture/kb-adapter-self-built.md` 与 `v3-overall-architecture.md`；实现要点：`NCMU-Wiki/sources/specs/ncmu-dify-design-v3.md §10.5`。

## API 契约摘要

**端点**：`POST /retrieval`

**请求**（Dify → kb-adapter）：

```http
POST /retrieval
Authorization: Bearer <api_key>
Content-Type: application/json

{
  "knowledge_id": "kb-xxx",
  "query": "用户提问",
  "retrieval_setting": {"top_k": 5, "score_threshold": 0.5},
  "metadata_condition": {
    "logical_operator": "and",
    "conditions": [
      {"name": ["filename"], "comparison_operator": "contains", "value": "manual"}
    ]
  }
}
```

`metadata_condition` 可显式为 `null`（Dify 行为），pydantic 会正确反序列化。

**成功响应**：

```json
{
  "records": [
    {
      "content": "chunk 正文",
      "score": 0.91,
      "title": "源文件名",
      "metadata": {}
    }
  ]
}
```

`records[].metadata` 永远是对象（可能是 `{}`），绝不是 `null`（Dify spec 要求）。

**错误响应**（均为 top-level JSON，不包 `detail`）：

| HTTP | error_code  | 场景                                 | 对应 spec |
|------|-------------|--------------------------------------|-----------|
| 403  | `1001` (int)| `Authorization` 缺失或格式不对       | §10.5.4 note #3 |
| 403  | `1002` (int)| token 不在 `KB_ADAPTER_ALLOWED_KEYS` | §10.5.4 note #3 |
| 200  | `2001` (int)| FastGPT 返回 404（知识库不存在），响应体含 `records: []`，由 Dify 侧短路 | §10.5.4 note #3 |
| 502  | `fastgpt_unreachable` (str) | `httpx.ConnectError`（端口关闭 / DNS 失败 / 连接拒绝） | §10.5.5（errata-06） |
| 502  | `fastgpt_upstream` (str) | FastGPT 返回 5xx（非 404 的 HTTP 错误）              | 实现兜底 |
| 504  | `fastgpt_timeout` (str)  | FastGPT 超时（10s，含 ConnectTimeout）               | §10.5.5 Test 4 |

> **spec 内部一致性说明**（待 Pane 5 裁决）：§10.5.4 note #3 用整数错误码（1001/1002/2001）；§10.5.5 Test 4 用字符串（`"fastgpt_timeout"`）。本实现按任务指令"优先 §10.5.5"保留字符串形式，同时用整数给 1001/1002/2001。下游（Dify）若对错误码类型敏感，需要 spec 侧统一。

## `metadata_condition → collectionIds` 翻译

- 支持的字段名：`filename` / `source` / `file_name`
- 支持的运算符：`contains` / `not contains` / `is` / `is not` / `start with` / `end with` / `=` / `!=`
- 非文件名字段（例如 chunk 级 metadata）会被忽略并以 `unsupported_filter` 记入日志（spec §10.5.4 note #4）
- `logical_operator` 支持 `and`（默认）与 `or`
- 翻译结果三值语义：
  - `None`：无可用过滤条件，走无过滤检索
  - `[]`：过滤命中 0 个 collection，handler 直接返回 `{"records": []}`，不再调 FastGPT
  - `["col_id_1", ...]`：作为 `collectionIds` 传给 FastGPT `/searchTest`

## 环境变量

| 变量                         | 必填 | 说明                                               |
|------------------------------|------|----------------------------------------------------|
| `KB_ADAPTER_ALLOWED_KEYS`    | 是   | 逗号分隔的明文 API Key 列表，容器启动时注入         |
| `FASTGPT_BASE_URL`           | 是   | FastGPT HTTP endpoint，例如 `http://fastgpt:3000` |
| `FASTGPT_API_KEY`            | 是   | kb-adapter 调 FastGPT 使用的 Key（与 Dify 侧独立） |

Key 轮换流程参考 `NCMU-Wiki/sources/specs/ncmu-dify-design-v3.md §10.5.4`。

## 本地启动

```bash
# 跑测试（要求 Python 3.11）
pip install -e ".[dev]"
pytest tests/ -v
pytest tests/ --cov=src/kb_adapter --cov-report=term-missing

# 本地运行 uvicorn
export KB_ADAPTER_ALLOWED_KEYS=dev-key-1,dev-key-2
export FASTGPT_BASE_URL=http://localhost:3000
export FASTGPT_API_KEY=fg-xxx
uvicorn kb_adapter.main:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker build -t kb-adapter:tdd .

docker run --rm -p 8000:8000 \
  -e KB_ADAPTER_ALLOWED_KEYS=dev-key-1,dev-key-2 \
  -e FASTGPT_BASE_URL=http://fastgpt:3000 \
  -e FASTGPT_API_KEY=fg-xxx \
  kb-adapter:tdd
```

容器内以非 root 用户 `kbadapter` (uid 10001) 启动，入口 `uvicorn kb_adapter.main:app :8000`。

如需在容器内跑 pytest：

```bash
docker run --rm -v $(pwd):/app -w /app python:3.11-slim \
  sh -c 'pip install --quiet -e ".[dev]" && pytest -v'
```

## 状态

- TASK-12 仓骨架已 PASS WITH COMMENTS（commit `232e813`）
- TASK-13 5 例 TDD + handler 已落地（8 tests / coverage 87% / ~170 行实现）
- TASK-14 批次 6：compose 上架 + Dify 挂载 + 真环境 E2E
