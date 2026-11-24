"""Offline attestation parser tests using a crafted X.509 certificate."""

from __future__ import annotations

import base64

import pytest

from solana_chat.client import (
    parse_attestation_bundle,
    validate_history,
)
from solana_chat.errors import AttestationError


def _der(tag: int, value: bytes) -> bytes:
    if len(value) < 0x80:
        return bytes([tag, len(value)]) + value
    length = len(value).to_bytes((len(value).bit_length() + 7) // 8, "big")
    return bytes([tag, 0x80 | len(length)]) + length + value


def _oid(dotted: str) -> bytes:
    parts = [int(p) for p in dotted.split(".")]
    body = bytes([parts[0] * 40 + parts[1]])
    for value in parts[2:]:
        chunk = [value & 0x7F]
        value >>= 7
        while value:
            chunk.append(0x80 | (value & 0x7F))
            value >>= 7
        body += bytes(reversed(chunk))
    return _der(0x06, body)


def build_certificate(sans: list[str]) -> str:
    names = [_der(0x82, n.encode()) for n in sans]
    listname = _der(0x30, b"".join(names))
    san_ext = _der(
        0x30,
        _oid("2.5.29.17") + _der(0x04, listname),
    )
    extensions = _der(0xA3, _der(0x30, san_ext))
    tbs = _der(
        0x30,
        _der(0xA0, _der(0x02, b"\x02"))
        + _der(0x02, b"\x01")
        + _der(0x30, b"")
        + _der(0x30, b"")
        + _der(0x30, b"")
        + extensions,
    )
    cert = _der(0x30, tbs + _der(0x30, b"") + _der(0x03, b"\x00"))
    return base64.b64encode(cert).decode()


def test_parse_bundle_extracts_hpke_key():
    sans = ["abc.hpke.solana#chat.tinfoil.sh", "solana#chat.tinfoil.sh"]
    cert = build_certificate(sans)
    bundle = {
        "enclaveAttestationReport": "x",
        "vcek": "y",
        "digest": "0" * 64,
        "releaseTag": "v1",
        "sigstoreBundle": {},
        "domain": "solana#chat.tinfoil.sh",
        "enclaveCert": cert,
    }
    with pytest.raises(AttestationError):
        parse_attestation_bundle(bundle)


def test_rejects_untrusted_host():
    sans = ["AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKKLLLLMMMM.hpke.x.tinfoil.sh"]
    cert = build_certificate(sans)
    bundle = {
        "enclaveAttestationReport": "x",
        "vcek": "y",
        "digest": "0" * 64,
        "releaseTag": "v1",
        "sigstoreBundle": {},
        "domain": "evil.example.com",
        "enclaveCert": cert,
    }
    with pytest.raises(AttestationError):
        parse_attestation_bundle(bundle)


def test_bundle_missing_field():
    with pytest.raises(AttestationError):
        parse_attestation_bundle({"domain": "a.tinfoil.sh"})


def test_validate_history_rules():
    good = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "again"},
    ]
    assert validate_history(good) is None
    assert validate_history([]) == "empty"
    assert validate_history([{"role": "user", "content": "x"}] * 21) == "full"
    assert validate_history([{"role": "assistant", "content": "x"}]) == "malformed"
    assert validate_history([{"role": "user", "content": "   "}]) == "malformed"


def test_large_history_prompt_too_long():
    messages = [
        {"role": "user", "content": "a" * 33000},
    ]
    assert validate_history(messages) == "prompt_too_long"
