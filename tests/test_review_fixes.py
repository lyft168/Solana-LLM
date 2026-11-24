"""Regression tests for the 2026-11 review fixes (server, client, http)."""

from __future__ import annotations

import base64
import http.client
import json
import os

import pytest

from solana_chat.catalog import resolve_model
from solana_chat.client import ChatResult, parse_attestation_bundle
from solana_chat.errors import AttestationError, TransportError
from solana_chat.http import Transport
from solana_chat.server import OpenAICompatServer, _flatten_messages, _parse_tool_calls
from tests.test_attestation import build_certificate


class FakeClient:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def chat(self, messages, *, model=None, max_completion_tokens=4096):
        return ChatResult(
            content=self.reply,
            reasoning=None,
            model=resolve_model(model.key if model else None),
            usage={"prompt_tokens": 1, "completion_tokens": 1, "reasoning_tokens": 0},
            truncated=False,
            elapsed_ms=1,
            raw={},
        )


# -- attestation domain allow-list -------------------------------------------


@pytest.mark.parametrize(
    "domain",
    [
        "solana#chat.tinfoil.sh",
        "localhost#x.tinfoil.sh",
        "attacker#a.tinfoil.sh",
        "evil.com/x.tinfoil.sh",
        "evil.com?x.tinfoil.sh",
        "user@evil.com.tinfoil.sh",
        "evil.com:443.tinfoil.sh",
    ],
)
def test_url_metachar_domain_rejected(domain):
    # '#', '/', '?', '@', ':' change which host a URL targets: an allow-list
    # bypass. These must always be rejected.
    label = domain.split(".tinfoil.sh")[0]
    key_b32 = base64.b32encode(os.urandom(32)).decode().rstrip("=")
    sans = [f"{key_b32}.hpke.{label}.tinfoil.sh"]
    bundle = {
        "enclaveAttestationReport": "x",
        "vcek": "y",
        "digest": "0" * 64,
        "releaseTag": "v1",
        "sigstoreBundle": {},
        "domain": domain,
        "enclaveCert": build_certificate(sans),
    }
    with pytest.raises(AttestationError):
        parse_attestation_bundle(bundle)


def test_plain_tinfoil_domain_accepted():
    key_b32 = base64.b32encode(os.urandom(32)).decode().rstrip("=")
    sans = [f"{key_b32}.hpke.solana-chat.tinfoil.sh"]
    bundle = {
        "enclaveAttestationReport": "x",
        "vcek": "y",
        "digest": "0" * 64,
        "releaseTag": "v1",
        "sigstoreBundle": {},
        "domain": "solana-chat.tinfoil.sh",
        "enclaveCert": build_certificate(sans),
    }
    att = parse_attestation_bundle(bundle)
    assert att.domain == "solana-chat.tinfoil.sh"
    assert len(att.hpke_public_key) == 32


def test_suffix_spoof_domain_rejected():
    key_b32 = base64.b32encode(os.urandom(32)).decode().rstrip("=")
    sans = [f"{key_b32}.hpke.x.tinfoil.sh"]
    bundle = {
        "enclaveAttestationReport": "x",
        "vcek": "y",
        "digest": "0" * 64,
        "releaseTag": "v1",
        "sigstoreBundle": {},
        "domain": "tinfoil.sh.evil.com",
        "enclaveCert": build_certificate(sans),
    }
    with pytest.raises(AttestationError):
        parse_attestation_bundle(bundle)


# -- tool-call parsing --------------------------------------------------------


def test_parse_tool_calls_with_prose_braces_around_json():
    text = 'Sure! {"note": "not a call"} then {"tool_calls":[{"name":"f","arguments":{"a":1}}]} done {trailing'
    remainder, calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "f"
    assert json.loads(calls[0]["function"]["arguments"]) == {"a": 1}
    assert "tool_calls" not in remainder


def test_parse_tool_calls_string_arguments():
    text = '{"tool_calls":[{"name":"g","arguments":"{\\"x\\": 2}"}]}'
    _, calls = _parse_tool_calls(text)
    assert json.loads(calls[0]["function"]["arguments"]) == {"x": 2}


# -- flatten ------------------------------------------------------------------


def test_flatten_assistant_tool_call_gets_placeholder():
    merged = _flatten_messages(
        [
            {"role": "user", "content": "call it"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "tool_call_id": "1", "content": "42"},
        ]
    )
    # assistant turn keeps a non-empty placeholder so validate_history passes
    assert any(m["role"] == "assistant" and m["content"].strip() != "" for m in merged)
    assert merged[-1]["role"] == "user"


# -- server behaviour ----------------------------------------------------------


def _post_raw(port: int, payload: dict, headers: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    merged = {"Content-Type": "application/json"}
    merged.update(headers or {})
    conn.request("POST", "/v1/chat/completions", json.dumps(payload).encode(), merged)
    resp = conn.getresponse()
    body = resp.read().decode()
    all_headers = resp.headers.get_all("Connection")
    status = resp.status
    conn.close()
    return status, body, all_headers


def test_sse_single_connection_close_header():
    server = OpenAICompatServer(FakeClient("ok"), port=0)
    server.start_background()
    port = server._httpd.server_address[1]
    try:
        status, _body, conn_headers = _post_raw(
            port,
            {
                "model": "deepseek/deepseek-v4.1-flash:encrypted",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    finally:
        server.stop()
    assert status == 200
    assert conn_headers == ["close"]


def test_unknown_model_returns_400():
    server = OpenAICompatServer(FakeClient("hi"), port=0)
    server.start_background()
    port = server._httpd.server_address[1]
    try:
        status, body, _ = _post_raw(
            port,
            {
                "model": "no/such-model:encrypted",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    finally:
        server.stop()
    assert status == 400
    assert "unknown model" in body


# -- transport ----------------------------------------------------------------


def test_transport_wraps_network_failure():
    transport = Transport(base_url="http://127.0.0.1:1", timeout=2.0)
    with pytest.raises(TransportError, match="cannot reach"):
        transport.request("GET", "/chat")
