#!/usr/bin/env bash
# Quick smoke test against a running bridge.
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:20129/v1}"
KEY="${SOLANA_CHAT_API_KEY:-}"

AUTH_ARGS=()
if [[ -n "$KEY" ]]; then
  AUTH_ARGS=(-H "Authorization: Bearer $KEY")
fi

echo "== models =="
curl -fsS "${AUTH_ARGS[@]}" "$BASE/models" | python3 -m json.tool | head -n 30

echo
echo "== chat =="
curl -fsS "${AUTH_ARGS[@]}" "$BASE/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek/deepseek-v4.1-flash:encrypted",
    "messages": [{"role": "user", "content": "Reply with the single word PONG."}]
  }' | python3 -m json.tool

echo
echo "== streaming =="
curl -fsS -N "${AUTH_ARGS[@]}" "$BASE/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "z-ai/glm-5.3:encrypted",
    "stream": true,
    "messages": [{"role": "user", "content": "Count to three."}]
  }'
