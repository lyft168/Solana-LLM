# Architecture

## What this project is

`solana.ai/chat` is a confidential-compute chat: your prompt is encrypted in
the browser **to the enclave**, the enclave decrypts and runs a model inside a
TEE, and the reply comes back encrypted so that the relay never sees either
side. The web app is a thin client over four HTTP endpoints plus a chunked
AEAD body format called **EHBP**.

This project provides a headless, reimplementation of that client in pure
Python, plus an OpenAI-compatible HTTP façade so any coding agent or router
can use it.

```
┌──────────────┐   OpenAI /v1      ┌──────────────────────────┐
│  9router     │ ────────────────► │  solana-chat serve       │
│  Cline       │                   │  (this project)          │
│  Cursor      │ ◄──── SSE ─────── │  :20129/v1               │
└──────────────┘                   └────────────┬─────────────┘
                                                │ EHBP (HPKE+AES-GCM)
                                                ▼
                                   ┌──────────────────────────┐
                                   │ solana.ai relay          │
                                   │ /api/chat/{session,      │
                                   │           attest,        │
                                   │           complete}      │
                                   └────────────┬─────────────┘
                                                │ attested TLS
                                                ▼
                                   ┌──────────────────────────┐
                                   │ Tinfoil enclave (TEE)    │
                                   │ model: deepseek-v4-1 ... │
                                   └──────────────────────────┘
```

## Request lifecycle

1. **Session** — `POST /api/chat/session` returns `204` and sets the relay
   cookie. It is bot-gated by a Vercel bot-protection challenge
   (`x-is-human` header from `a-4-a/c.js`). The cookie is opaque; the client
   persists it in `session.json`. Token minting is delegated to
   `tools/botid_browser.mjs` via `SOLANA_CHAT_SOLVE_COMMAND` — see
   [quota §5a](quota.md).
2. **Attest** — `POST /api/chat/attest` returns a bundle:
   `enclaveAttestationReport`, `vcek`, `sigstoreBundle`, `digest`,
   `releaseTag`, `domain`, `enclaveCert`. The HPKE public key is embedded in
   a `*.hpke.*` SAN of `enclaveCert`, base32-encoded.
3. **Verify (lightweight)** — the client parses the X.509 DER, extracts the
   SAN, requires a `*.tinfoil.sh` host and a 32-byte X25519 key. Full Sigstore
   verification is delegated to upstream `@tinfoilsh/verifier`; see
   *Verification scope* below.
4. **Seal** — the request body is JSON, HPKE-sealed with `info="ehbp
   request"`, wrapped in the EHBP chunk framing (`u32 len || sha256 ||
   ciphertext`).
5. **Complete** — `POST /api/chat/complete` with headers
   `ehbp-encapsulated-key`, `x-enclave-origin`, `x-chat-model`, `x-chat-id`.
   Response is EHBP-framed, keyed from `ehbp-response` nonce.
6. **Bridge** — payload is translated into an OpenAI `chat.completion`
   (or SSE chunks), with tool calls re-assembled from the model's JSON.

## Verification scope

Two layers, on purpose:

| Layer | Where | Depth |
|---|---|---|
| Structural | this project | cert parses, SAN extracted, base32 decodes, 32-byte X25519, `*.tinfoil.sh` host, `ehbp-v1` protocol |
| Cryptographic | upstream `@tinfoilsh/verifier` | Sigstore bundle, VCEK chain, measurement equality, certificate-binding |

The structural layer is what runs on a VPS with zero JS dependencies — it
prevents sealing to an obviously wrong key. Running the *full* Sigstore
verification requires the JS verifier; the CLI exposes the bundle at
`solana-chat attest --json` so it can be handed to a verifier of choice when
strict verification matters. See `docs/security.md`.

## Credit / quota

`solana.ai/chat` has no wallet, no signup, no API key, no promo code field,
and no free-credit counter. The quota is **per relay session and per egress
IP**, observed and documented in `docs/quota.md`. There is no "auto claim
promo" because there is no promo system — see `docs/quota.md` for the exact
evidence.

## Files

```
src/solana_chat/
  hpke.py        EHBP / HPKE / AES-GCM / X25519 / HKDF primitives
  client.py      session → attest → seal → complete
  server.py      OpenAI-compatible bridge (streaming + tool calls)
  session.py     persisted relay cookie + attestation memo
  catalog.py     model table (single source of truth)
  http.py        urllib transport + cookie jar
  cli.py         argparse surface
tests/           20 tests incl. RFC 7748 / RFC 5869 vectors
deploy/          systemd unit + idempotent installer
examples/        9router provider JSON, curl smoke test
```
