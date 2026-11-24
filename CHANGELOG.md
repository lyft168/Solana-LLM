# Changelog

## 1.0.0 — 2026-11-24

Initial public release.

- EHBP v1 client implemented in pure Python
  (X25519, HKDF-SHA256, AES-256-GCM, chunk framing).
- Enclave attestation bundle parser: DER/X.509 SAN walk, base32 HPKE key
  extraction, `*.tinfoil.sh` host allow-list, protocol pin.
- CLI: `models`, `ask`, `attest`, `serve`, `session`, `doctor`.
- OpenAI-compatible bridge with SSE streaming and a tool-call re-parse shim.
- Persisted relay session (`0600`) with attestation memo.
- Hardened systemd unit + idempotent VPS installer, Dockerfile, compose file.
- 20 tests including RFC 7748 and RFC 5869 vectors.
