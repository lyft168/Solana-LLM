"""Server surface tests with a fake upstream client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from solana_chat.catalog import resolve_model
from solana_chat.client import ChatResult
from solana_chat.server import OpenAICompatServer, _flatten_messages, _parse_tool_calls


class FakeClient:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_messages = None

    def chat(self, messages, *, model=None, max_completion_tokens=4096):
        self.last_messages = messages
        return ChatResult(
            content=self.reply,
            reasoning=None,
            model=resolve_model(model.key if model else None),
            usage={
                "prompt_tokens": 7,
                "completion_tokens": 3,
                "reasoning_tokens": 0,
            },
            truncated=False,
            elapsed_ms=12,
            raw={},
        )


def _post(port: int, payload: dict, headers: dict | None = None):
    data = json.dumps(payload).encode()
    merged = {"Content-Type": "application/json"}
    merged.update(headers or {})
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=data,
        headers=merged,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_tool_call_roundtrip():
    fake = FakeClient(
        '{"tool_calls":[{"name":"read_file","arguments":{"path":"a.txt"}}]}'
    )
    server = OpenAICompatServer(fake, port=0)
    server.start_background()
    port = server._httpd.server_address[1]
    try:
        status, body = _post(
            port,
            {
                "model": "deepseek/deepseek-v4.1-flash:encrypted",
                "messages": [{"role": "user", "content": "open a.txt"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "description": "read a file",
                            "parameters": {
                                "type": "object",
                                "properties": {"path": {"type": "string"}},
                            },
                        },
                    }
                ],
            },
        )
    finally:
        server.stop()
    assert status == 200
    payload = json.loads(body)
    message = payload["choices"][0]["message"]
    assert payload["choices"][0]["finish_reason"] == "tool_calls"
    assert message["tool_calls"][0]["function"]["name"] == "read_file"
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {
        "path": "a.txt"
    }


def test_models_endpoint_lists_five():
    fake = FakeClient("hi")
    server = OpenAICompatServer(fake, port=0)
    server.start_background()
    port = server._httpd.server_address[1]
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/v1/models", timeout=5
        ) as resp:
            payload = json.loads(resp.read())
    finally:
        server.stop()
    assert len(payload["data"]) == 5
    assert payload["data"][0]["object"] == "model"


def test_flatten_merges_consecutive_roles():
    merged = _flatten_messages(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "user", "content": "again"},
        ]
    )
    assert merged[0]["content"].startswith("sys")
    assert len(merged) == 1


def test_parse_tool_calls_ignores_plain_text():
    text, calls = _parse_tool_calls("just prose, no json")
    assert text == "just prose, no json"
    assert calls == []


def test_streaming_sse_emits_chunks():
    fake = FakeClient("hello from the enclave")
    server = OpenAICompatServer(fake, port=0)
    server.start_background()
    port = server._httpd.server_address[1]
    try:
        status, body = _post(
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
    events = [line for line in body.splitlines() if line.startswith("data: ")]
    assert events[-1] == "data: [DONE]"
    first = json.loads(events[0][6:])
    assert first["object"] == "chat.completion.chunk"
    assert first["choices"][0]["delta"]["role"] == "assistant"
    text = "".join(
        json.loads(e[6:])["choices"][0]["delta"].get("content", "")
        for e in events[1:-1]
    )
    assert text == "hello from the enclave"


def test_api_key_required_when_set():
    fake = FakeClient("hi")
    server = OpenAICompatServer(fake, port=0, api_key="secret")
    server.start_background()
    port = server._httpd.server_address[1]
    try:
        status, body = _post(
            port,
            {
                "model": "deepseek/deepseek-v4.1-flash:encrypted",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    finally:
        server.stop()
    assert status == 401
    assert "invalid api key" in body


def test_flatten_merges_tool_messages():
    merged = _flatten_messages(
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "call it"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "tool_call_id": "1", "content": "42"},
        ]
    )
    assert merged[-1]["role"] == "user"
    assert "[tool result 1]" in merged[-1]["content"]
