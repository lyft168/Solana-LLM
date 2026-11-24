#!/usr/bin/env bash
# Quick smoke test against a running bridge.
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:20129/v1}"
KEY="${SOLANA_CHAT_API_KEY:-}"

echo "== models =="
curl -fsS "$BASE/models" | python3 -m json.tool | head -n 30

echo
echo "== chat =="
curl -fsS "$BASE/chat/completions" \
  -H "Content-Type: application/json" \
  ${KEY:+-H "Authorization: Bearer $KEY"} \
  -d '{
    "model": "deepseek/deepseek-v4.1-flash:encrypted",
    "messages": [{"role": "user", "content": "Reply with the single word PONG."}]
  }' | python3 -m json.tool

echo
echo "== streaming =="
curl -fsS -N "$BASE/chat/completions" \
  -H "Content-Type: application/json" \
  ${KEY:+-H "Authorization: Bearer $KEY"} \
  -d '{
    "model": "z-ai/glm-5.3:encrypted",
    "stream": true,
    "messages": [{"role": "user", "content": "Count to three."}]
  }'
