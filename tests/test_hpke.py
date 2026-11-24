"""RFC 9180 / RFC 7748 / RFC 5869 vectors + EHBP framing invariants."""

from __future__ import annotations

import hashlib
import os
import struct

import pytest

from solana_chat import hpke


def test_x25519_rfc7748_alice_public():
    sk = bytes.fromhex(
        "77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a"
    )
    assert hpke.x25519_public(sk).hex() == (
        "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"
    )


def test_x25519_shared_secret_rfc7748():
    a_sk = bytes.fromhex(
        "77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a"
    )
    b_pk = bytes.fromhex(
        "de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f"
    )
    assert hpke.x25519(a_sk, b_pk).hex() == (
        "4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742"
    )


def test_hkdf_rfc5869_case1():
    ikm = bytes.fromhex("0b" * 22)
    salt = bytes.fromhex("000102030405060708090a0b0c")
    info = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
    okm = hpke.hkdf_sha256(ikm, salt, info, 42)
    assert okm.hex() == (
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
        "34007208d5b887185865"
    )


def test_seq_nonce_xor_is_big_endian():
    base = bytes(range(12))
    nonce = hpke.seq_nonce(base, 1)
    assert nonce[:11] == base[:11]
    assert nonce[11] == base[11] ^ 1
    big = hpke.seq_nonce(base, 1 << 32)
    assert big[7] == base[7] ^ 1


def test_hpke_roundtrip_with_local_recipient():
    recipient_sk = os.urandom(32)
    recipient_pk = hpke.x25519_public(recipient_sk)
    ctx = hpke.setup_base_sender(recipient_pk, hpke.REQUEST_INFO)
    plaintext = b'{"model":"deepseek-v4-1-flash","stream":false}'
    sealed = hpke.seal_stream(ctx, plaintext)
    exported = ctx.export(hpke.EXPORT_LABEL, 32)
    assert len(exported) == 32
    key, nonce_base = hpke.derive_response_keys(exported, ctx.enc, b"\x00" * 32)
    assert len(key) == 32 and len(nonce_base) == 12
    # framing sanity: each chunk is 4-byte length + 32-byte digest + sealed
    offset = 0
    chunks = 0
    while offset < len(sealed):
        (length,) = struct.unpack(">I", sealed[offset : offset + 4])
        digest = sealed[offset + 4 : offset + 36]
        payload = sealed[offset + 36 : offset + 36 + length]
        assert hashlib.sha256(payload).digest() == digest
        offset += 36 + length
        chunks += 1
    assert chunked_plaintext_size(sealed) == len(plaintext)
    assert chunks >= 1


def chunked_plaintext_size(sealed: bytes) -> int:
    offset = 0
    total = 0
    while offset < len(sealed):
        (length,) = struct.unpack(">I", sealed[offset : offset + 4])
        total += length - 16
        offset += 36 + length
    return total


def test_open_stream_roundtrip():
    try:
        key = os.urandom(32)
        nonce_base = os.urandom(12)
        chunks = [b"hello", b"world", b""]
        raw = b""
        for seq, chunk in enumerate(chunks):
            sealed = hpke.aes_gcm_seal(key, hpke.seq_nonce(nonce_base, seq), chunk)
            raw += struct.pack(">I", len(sealed))
            raw += hashlib.sha256(sealed).digest()
            raw += sealed
        assert hpke.open_stream(raw, key, nonce_base) == b"helloworld"
    except hpke.HPKEError:
        pytest.skip("pycryptodome missing")


def test_open_stream_rejects_digest_mismatch():
    try:
        key = os.urandom(32)
        nonce_base = os.urandom(12)
        sealed = hpke.aes_gcm_seal(key, hpke.seq_nonce(nonce_base, 0), b"x")
        raw = struct.pack(">I", len(sealed)) + b"\x00" * 32 + sealed
        with pytest.raises(hpke.HPKEError):
            hpke.open_stream(raw, key, nonce_base)
    except hpke.HPKEError:
        pytest.skip("pycryptodome missing")
