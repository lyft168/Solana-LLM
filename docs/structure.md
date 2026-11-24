# Repository structure

```
inspectorai-solana-chat/
├── src/solana_chat/
│   ├── __init__.py          public exports + version
│   ├── __main__.py          `python -m solana_chat`
│   ├── cli.py               argparse: models/ask/attest/serve/session/doctor
│   ├── client.py            session→attest→seal→complete orchestration
│   ├── hpke.py              EHBP primitives (X25519, HKDF, AES-GCM, framing)
│   ├── http.py              urllib transport + shared cookie jar
│   ├── catalog.py           the five-model table (single source of truth)
│   ├── session.py           persisted cookie + attestation memo (0600)
│   ├── server.py            OpenAI-compatible bridge (SSE + tool calls)
│   └── errors.py            typed exception hierarchy
├── tests/
│   ├── test_hpke.py         RFC 7748 / RFC 5869 vectors + framing
│   ├── test_catalog.py      alias resolution, uniqueness
│   ├── test_attestation.py  DER/SAN parsing, history validation
│   └── test_server.py       OpenAI surface with a fake upstream
├── deploy/
│   ├── solana-chat.service  hardened systemd unit
│   └── install.sh           idempotent VPS installer
├── examples/
│   ├── 9router.json         9router provider config
│   └── curl.sh              smoke test (models/chat/stream)
├── docs/
│   ├── architecture.md      request lifecycle + diagrams
│   ├── protocol-ehbp.md     byte-level wire format
│   ├── quota.md             what quota/credits actually exist
│   ├── security.md          threat model + verification scope
│   ├── 9router.md           wiring walkthrough
│   └── i18n/                README translations (id, zh-CN, ja, es, ar)
├── assets/                  logo.svg + logo.png
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── .gitlab-ci.yml           lint + tests only (no release pipeline)
├── README.md
└── LICENSE
```

## Data flow at a glance

```
CLI / 9router
     │  OpenAI JSON
     ▼
server.py ──► client.py ──► hpke.py ──► http.py ──► solana.ai relay
     ▲            │                         │
     │            ▼                         ▼
     └────── session.py (cookie + memo)   enclave (TEE)
```
