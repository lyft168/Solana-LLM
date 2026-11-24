# Review notes (patch set on top of upstream d355b19)

Upstream: https://gitlab.com/inspectorai/inspectorai-solana-chat
This set fixes correctness, thread safety, speed and process lifecycle. It does **not** change how the bot check is handled.

## Status
- Offline: 30/30 tests pass. The HPKE output was cross-checked against `pyhpke`. 100 requests (20 at a time) peaked at about 33 MB RSS.
- **Live: NOT verified.** The live smoke test got HTTP 403 when opening a session, before any encryption ran.

## Changes
### src/solana_chat/hpke.py — REVIEW CAREFULLY
- AES-GCM nonce bug: the cipher was built with an all-zero nonce, and setting `cipher.nonce` afterwards had no effect. The nonce is now passed to `AES.new(..., nonce=...)`.
- The key schedule now follows RFC 9180: labelled extract includes the label, KEM suite id `KEM||kem_id`, HPKE suite id `HPKE||kem||kdf||aead`, no extra extract inside expand, the `sec` label on export, and an all-zero DH output is rejected.
- **Risk:** if the real enclave depended on the old non-standard behaviour, decryption will fail live. In that case compare against the site's own JS client before reverting anything. Never revert the nonce fix.
- Note: the existing tests are round-trip only, which is how these bugs went unnoticed. Add known-answer tests (RFC 9180 Appendix A) for the full key schedule.

### src/solana_chat/session.py
- `SessionStore` writes are guarded by a lock and use a unique temp file plus `os.replace`.

### src/solana_chat/client.py
- Lock around `ensure_session`, so parallel requests can't open duplicate sessions.
- Attestation cache using `memo_attestation`/`read_attestation`. TTL is `SOLANA_CHAT_ATTEST_TTL` (default 900 s, 0 disables it). The cache is dropped when the relay rejects a request. Trade-off: a cached key is trusted for up to one TTL.

### src/solana_chat/http.py
- Per-thread keep-alive `http.client` pool for direct connections, with the cookie jar preserved. Proxied requests still use `urllib`.
- To check: stale-connection retry for POSTs (it must not replay a request that is not idempotent after a partial send).

### src/solana_chat/server.py
- Body limit `SOLANA_CHAT_MAX_BODY` (default 1 MB, returns 413), constant-time API key check, duplicate `Connection` header removed, the tool-call parser takes the first balanced JSON object, unused `re` import removed.

### tools/botid_browser.mjs — lifecycle only
- Single-flight boot with a generation counter (no duplicate or orphaned Chromium), the browser is closed on a failed boot, SIGTERM/SIGINT/uncaught handlers with a 10 s force-kill, reset on disconnect or crash, 15 s mint timeout, a serial mint queue (max 8, then 503 + Retry-After), recycling after 500 mints, idle close after 5 minutes, HTTP timeouts and a connection cap, IPv6-safe `--listen`, `size` validation, generic errors returned to clients.
- The original `window` reference in Node (which crashed every boot) was moved into `page.evaluate`.
- Mint logic, launch flags, UA and viewport are unchanged. Only `node --check` has been run, not a real execution yet.
- Deploy under systemd with `MemoryMax=500M`, `TasksMax=200`, `KillMode=control-group` and a dedicated user (`--no-sandbox` is still set).

## Open TODOs
1. Real upstream streaming. `iter_open_stream` is ready, but the upstream SSE format isn't documented. Capture one real streamed reply first instead of guessing the format.
2. Thinking passthrough: the server drops `result.reasoning`. Add `reasoning_content` to messages and stream deltas, and `reasoning_tokens` to usage.
3. Offline regression tests for all 5 models (`gpt-oss`, `gemma-4-31b`, `deepseek-v4.1-flash`, `glm-5.3`, `kimi-k3.1-pro`) against a mocked upstream, plus tests that pin the nonce and the RFC key schedule.
4. Lifecycle test for `botid_browser.mjs` with a fake Playwright (concurrent boots, crash, timeout, idle).
5. The 20-message limit has no trimming yet. Tool results are inlined as plain text (prompt-injection risk).
6. 9router wiring (Docker, host port 5003): the bridge has to bind to the Docker gateway with an API key, not 127.0.0.1.

## Security
- An earlier debug command printed 9router's `MACHINE_ID_SALT` into a chat log. Rotate it if that log is shared.
