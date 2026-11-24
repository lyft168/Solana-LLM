# Wiring 9router → this bridge

9router speaks OpenAI-compatible `POST /v1/chat/completions` and expects a
provider base URL + API key. Point it at this bridge.

## 1. Start the bridge

```bash
pip install -e .
export SOLANA_CHAT_API_KEY=$(openssl rand -hex 24)
export SOLANA_CHAT_HOST=127.0.0.1
export SOLANA_CHAT_PORT=20129
solana-chat serve
```

Verify:

```bash
curl -fsS http://127.0.0.1:20129/v1/health
curl -fsS http://127.0.0.1:20129/v1/models | jq '.data[].id'
```

## 2. Add a provider in 9router

Dashboard → **Providers** → **Add custom provider** → OpenAI-compatible:

| Field | Value |
|---|---|
| Base URL | `http://127.0.0.1:20129/v1` |
| API Key | the value of `SOLANA_CHAT_API_KEY` |
| Type | `openai-compatible` |
| Tool calls | on |

Models are auto-discovered from `GET /v1/models`; that endpoint returns the
five public ids.

## 3. Point your agent at 9router

```bash
export OPENAI_BASE_URL=http://localhost:20128/v1
export OPENAI_API_KEY=<9router key>
```

Model ids are the pty public ids, e.g. `deepseek/deepseek-v4.1-flash:encrypted`.

## 4. What works / what doesn't

| Capability | Status |
|---|---|
| chat completions | ✅ |
| streaming (SSE) | ✅ |
| tool calls (`tools` / `tool_choice`) | ✅ (JSON-reparse shim) |
| vision / image input | ❌ (relay rejects `unsupported_type`) |
| embeddings / TTS / STT | ❌ (separate relays, not available) |
| JSON mode (`response_format`) | ⚠️ prompt-level only |

## 5. Capacity

9router's smart fallback tiers still apply: put this provider in **Tier 2**
(cheap) so 9router falls through to it when the free tiers hit
`session_limit`. The bridge surfaces relay errors verbatim, and 9router's
fallback keys off HTTP 429/503 — which is exactly what the relay returns.
See `examples/9router.json` for a drop-in provider config.
