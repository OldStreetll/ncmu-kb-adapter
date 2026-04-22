# ncmu-kb-adapter

NCMU 自研协议转换层：把 Dify External KB API 的检索请求翻译成 FastGPT 数据集检索调用，再把 FastGPT 的命中结果回写成 Dify External KB 响应格式，并在协议边界完成 Bearer 鉴权、`metadata_condition → collectionIds` 过滤、分数归一化。

## 架构位置

Dify 编排 → (External KB API) → **ncmu-kb-adapter**（本仓，FastAPI，~150-250 行）→ (FastGPT HTTP API) → FastGPT RAG 层。设计依据：`NCMU-Wiki/architecture/kb-adapter-self-built.md` 与 `v3-overall-architecture.md`。

## 启动命令占位

```bash
# 本地测试（骨架阶段只会空跑通过）
pytest tests/

# 构建镜像
docker build -t kb-adapter .
```

TASK-13 会落地 5 例单测 + 完整 handler 与 FastAPI 路由；当前版本只是让构建与测试空跑链路通畅。
