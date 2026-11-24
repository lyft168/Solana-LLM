# EHBP v1 — wire format (client side)

EHBP ("Encrypted HTTP Body Protocol") is the on-the-wire envelope Solana
Confidential Chat uses so the relay never sees plaintext. This file records
the exact bytes the client emits, so a future reverse-engineer can diff
against the reference implementation in `_next/static/.../0mb8qxw2yv0o1.js`.

## Headers

| Header | Value |
|---|---|
| `ehbp-encapsulated-key` | hex(X25519 ephemeral public key, 32 bytes) |
| `x-enclave-origin` | `https://<enclave-host>` |
| `x-chat-model` | model `key` from `catalog.py` |
| `x-chat-id` | opaque chat id (32 hex chars) |
| `ehbp-response-nonce` | (response) hex 32-byte nonce chosen by enclave |

## Keys

```
salt            = enc || response_nonce
prk             = HKDF-SHA256(salt, exported_secret, 32)
key             = HKDF-SHA256(prk, "", "key", 32)
nonce_base      = HKDF-SHA256(prk, "", "nonce", 12)
```

`exported_secret = HKDF-Expand(exporter_secret_from_HPKE, "ehbp response", 32)`.

## Chunks

```
chunk_n         = AES-256-GCM(key, nonce_base XOR BE64(n), plaintext_slice)
frame           = u32_be(len(chunk_n)) || sha256(chunk_n) || chunk_n
```

- Chunk size: 65536 bytes plaintext.
- `nonce_base XOR BE64(n)` is **not** standard AES-GCM counter mode; it is
  the reference implementation's "seq_nonce" (XOR into the last 8 bytes,
  big-endian).
- Empty body ⇒ one empty chunk (still framed).

## HPKE parameters

- KEM: DHKEM(X25519, HKDF-SHA256), `id = 0x0020`
- KDF: HKDF-SHA256, `id = 0x0001`
- AEAD: AES-256-GCM, `id = 0x0002`
- Mode: base (mode 0), no PSK
- `info`: `"ehbp request"` for request, `"ehbp response"` for export

See `tests/test_hpke.py` for the RFC 7748 / RFC 5869 cross-checks that pin
the primitives.

## Relay error codes

```
bot | busy | chat_message_limit | demo_exhausted | forbidden
invalid_request | rate_limited | session_limit | session_required
timeout | too_large | unavailable | unsupported_type | upstream
```

Mapped to human text in `src/solana_chat/client.py::RELAY_ERRORS`.
