<div align="center">

<img src="assets/logo.png" alt="inspectorai-solana-chat" width="820"/>

# inspectorai-solana-chat

**Headless CLI + OpenAI-compatible bridge for [Solana Confidential Chat](https://solana.ai/chat).**
EHBP (HPKE-sealed) requests, TEE attestation binding, streaming, tool calls, 9router-ready.

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-14F195.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos%20%7C%20vps-9945FF.svg)](docs/security.md)
[![Tests](https://img.shields.io/badge/tests-30%20passing-14F195.svg)](tests/)
[![Crypto](https://img.shields.io/badge/crypto-HPKE%20%C2%B7%20X25519%20%C2%B7%20AES--256--GCM-9945FF.svg)](docs/protocol-ehbp.md)
[![OpenAI compatible](https://img.shields.io/badge/API-OpenAI%20compatible-10A37F.svg)](docs/9router.md)
[![9router](https://img.shields.io/badge/9router-ready-ff6b00.svg)](examples/9router.json)
[![TEE](https://img.shields.io/badge/enclave-Tinfoil%20TEE-14F195.svg)](docs/security.md)
[![Telegram](https://img.shields.io/badge/community-Telegram-26A5E4?logo=telegram&logoColor=white)](https://t.me/inspectoraiofc)
[![GitLab](https://img.shields.io/badge/gitlab-inspectorai-FC6D26?logo=gitlab&logoColor=white)](https://gitlab.com/inspectorai/inspectorai-solana-chat)

[English](README.md) · [Bahasa Indonesia](docs/i18n/README.id.md) · [中文](docs/i18n/README.zh-CN.md) · [日本語](docs/i18n/README.ja.md) · [Español](docs/i18n/README.es.md) · [العربية](docs/i18n/README.ar.md)

</div>

---

## What is solana.ai/chat?

Solana's chat runs models inside a **confidential enclave** (Tinfoil TEE) on
Solana hardware. The browser encrypts your prompt **to the enclave** with
HPKE, the enclave runs the model, and the reply comes back encrypted so the
relay never sees either side. The web app speaks a chunked AEAD body format
called **EHBP** — that's the whole API.

This repo is the **headless client** for it: pure-Python EHBP, attestation
parsing, plus a local `POST /v1/chat/completions` server so 9router, Cline,
Cursor, Continue and any OpenAI-shaped tool can use it.

## Available models

The chat ships **five** models, all TEE-sealed. Use the *public id* as the
`model` field anywhere.

| Public ID | Key | Display name |
|---|---|---|
| `deepseek/deepseek-v4.1-flash:encrypted` | `deepseek-v4.1-flash` | DeepSeek V4.1 Flash *(default)* |
| `openai/gpt-oss-120b:encrypted` | `gpt-oss` | GPT-OSS 120B |
| `google/gemma-4-31b-it:encrypted` | `gemma-4-31b` | Gemma 4 31B |
| `z-ai/glm-5.3:encrypted` | `glm-5.3` | GLM 5.3 |
| `moonshotai/kimi-k3.1-pro:encrypted` | `kimi-k3.1-pro` | Kimi K3.1 Pro |

```bash
solana-chat models        # same table from the CLI
```

## Credits — the honest answer

`solana.ai/chat` has **no sign-up, no accounts, no promo code, no credit
balance.** The unit is *messages per relay session*, gated by
`session_limit` (hourly) and `chat_message_limit` (per conversation) against
a shared demo pool (`demo_exhausted`). There is no `/credits` endpoint and no
number to "claim". Full evidence, with the exact error-code table:
**[docs/quota.md](docs/quota.md)**.

Any README quoting a hard per-account credit number for this product is
inventing it.

## Install

```bash
git clone https://gitlab.com/inspectorai/inspectorai-solana-chat.git
cd inspectorai-solana-chat
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
solana-chat doctor          # checks crypto + reachability
```

VPS one-liner (systemd unit, hardened, API key generated):

```bash
sudo REPO=https://gitlab.com/inspectorai/inspectorai-solana-chat.git bash deploy/install.sh
```

Docker:

```bash
docker compose up -d --build
curl -fsS http://127.0.0.1:20129/v1/health
```

## Use it

**CLI, one shot:**

```bash
solana-chat ask "explain x402 in two sentences"
solana-chat ask -m kimi-k3.1-pro "write a haiku about enclaves" --usage
solana-chat attest -m deepseek-v4.1-flash --json   # dump the attestation bundle
```

**OpenAI bridge (what 9router talks to):**

```bash
export SOLANA_CHAT_API_KEY=$(openssl rand -hex 24)
solana-chat serve --host 127.0.0.1 --port 20129

curl -s http://127.0.0.1:20129/v1/chat/completions \
  -H "Authorization: Bearer $SOLANA_CHAT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek/deepseek-v4.1-flash:encrypted",
       "messages":[{"role":"user","content":"PONG?"}]}'
```

**9router:**

```
Base URL : http://127.0.0.1:20129/v1
API Key  : $SOLANA_CHAT_API_KEY
Type     : openai-compatible
Tool calls: on
```

Provider JSON: [`examples/9router.json`](examples/9router.json) · walkthrough:
[docs/9router.md](docs/9router.md). Pair it with
[9router](https://github.com/decolua/9router) so Claude Code / Codex / Cursor /
Cline get a free TEE provider in the fallback chain.

## Capability matrix

| Feature | CLI | Bridge |
|---|---|---|
| chat completions | ✅ | ✅ |
| streaming (SSE) | — | ✅ |
| tool calls / function calling | — | ✅ (JSON-reparse shim) |
| model listing | ✅ | ✅ |
| attestation inspection | ✅ | via `solana-chat attest` |
| persisted session cookie | ✅ | ✅ |
| vision / images | ❌ relay rejects | ❌ |
| embeddings / TTS / STT | ❌ | ❌ |

## Structure

```
inspectorai-solana-chat/
├── src/solana_chat/
│   ├── cli.py        models · ask · attest · serve · session · doctor
│   ├── client.py     session → attest → seal → complete
│   ├── hpke.py       EHBP: X25519 · HKDF-SHA256 · AES-256-GCM · framing
│   ├── server.py     OpenAI-compatible bridge (SSE + tool calls)
│   ├── session.py    persisted relay cookie + attestation memo (0600)
│   ├── catalog.py    the five-model table
│   ├── http.py       urllib transport + cookie jar
│   └── errors.py     typed errors
├── tests/            30 tests, RFC 7748 / RFC 5869 vectors included
├── deploy/           hardened systemd unit + idempotent installer
├── examples/         9router provider JSON, curl smoke test
├── docs/             architecture · protocol · quota · security · 9router
├── assets/           logo.svg · logo.png
├── Dockerfile · docker-compose.yml · .gitlab-ci.yml
└── pyproject.toml
```

Deeper: [architecture](docs/architecture.md) ·
[EHBP wire format](docs/protocol-ehbp.md) ·
[security review](docs/security.md).

## How the sealing works (short version)

```
POST /api/chat/session   ──► 204 + relay cookie
POST /api/chat/attest    ──► bundle → HPKE key from the enclave cert SAN
HPKE seal (X25519-HKDF-SHA256 / HKDF-SHA256 / AES-256-GCM, info="ehbp request")
POST /api/chat/complete  ──► AEAD-framed JSON, opened with the response nonce
```

Verification scope is stated plainly in [docs/security.md](docs/security.md):
structural binding (cert parse, SAN, host allow-list, suite pin, AEAD tags)
runs here; full Sigstore/VCEK verification is upstream's
`@tinfoilsh/verifier`, and the bundle is exposed for it via
`solana-chat attest --json`.

## Known limitation: the relay is bot-gated

`POST /api/chat/session` sits behind a Vercel bot-protection challenge. A
browser visit passes it; a bare datacenter IP does not, and the relay answers
`HTTP 403 {"error":{"code":"bot"}}`. That is a property of the upstream, not
of this client — the client implements the headers and the challenge hook, but
it does not forge tokens.

Practical paths, both supported in code:

1. **Route through a browser-like egress** — `SOLANA_CHAT_PROXY=http://user:pass@host:port`
   (residential/US), then `solana-chat session show` to confirm a cookie landed.
2. **Seed from a machine you browse from** — open `solana.ai/chat`, copy
   `~/.local/state/inspectorai-solana-chat/session.json` from the browser-run
   instance, or pass `--session-file` to point at it.

Read `docs/quota.md` §5 for the exact evidence, including what a `b:0` vs `b:1`
token looks like.

The repo ships the bridge for this gate: [`tools/botid_browser.mjs`](tools/botid_browser.mjs)
drives a real headless Chromium, asks the page for a token, and serves it over
loopback. Wire it in one flag:

```bash
npm i playwright && npx playwright install chromium
export SOLANA_CHAT_SOLVE_COMMAND="node tools/botid_browser.mjs --print-once"
solana-chat serve                 # session + attest + complete all get x-is-human
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q          # 30 tests
ruff check src tests
ruff format --check src tests
```

CI runs lint + tests only — no release pipeline, no roadmap file.

## Community & support

- Telegram: **[t.me/inspectoraiofc](https://t.me/inspectoraiofc)**
- Issues: [gitlab.com/inspectorai/inspectorai-solana-chat/-/issues](https://gitlab.com/inspectorai/inspectorai-solana-chat/-/issues)

## License

MIT — see [LICENSE](LICENSE).

<div align="center">

**[⬆ back to top](#inspectorai-solana-chat)**

</div>
