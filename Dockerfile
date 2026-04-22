FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 kbadapter

WORKDIR /app

COPY --chown=kbadapter:kbadapter pyproject.toml README.md ./
COPY --chown=kbadapter:kbadapter src/ ./src/

RUN pip install --no-cache-dir .

USER kbadapter

EXPOSE 8000

CMD ["uvicorn", "kb_adapter.main:app", "--host", "0.0.0.0", "--port", "8000"]
