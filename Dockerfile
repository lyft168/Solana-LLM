# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SOLANA_CHAT_HOST=0.0.0.0 \
    SOLANA_CHAT_PORT=20129

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 chat

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

USER chat
EXPOSE 20129
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -fsS http://127.0.0.1:20129/v1/health || exit 1

ENTRYPOINT ["solana-chat", "serve"]
CMD ["--host", "0.0.0.0", "--port", "20129"]
