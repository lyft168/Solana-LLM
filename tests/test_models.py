"""Per-model regression tests with a fake upstream (no live site needed).

For every catalog model this checks: alias resolution, the model the server
hands to the client, the model id echoed back, and thinking passthrough in
both normal and streamed replies.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from solana_chat.catalog import MODELS, resolve_model
from solana_chat.client import ChatResult
from solana_chat.errors import UnknownModelError
from solana_chat.server import OpenAICompatServer


class ThinkingClient:
    def __init__(self, reasoning: str | None = "step 1: think", reasoning_tokens: int = 5):
        self.reasoning = reasoning
        self.reasoning_tokens = reasoning_tokens
        self.last_model = None

    def chat(self, messages, *, model=None, max_completion_tokens=4096):
        self.last_model = model
        return ChatResult(
            content="final answer",
            reasoning=self.reasoning,
            model=model,
            usage={
                "prompt_tokens": 7,
                "completion_tokens": 3,
                "reasoning_tokens": self.reasoning_tokens,
            },
            truncated=False,
            elapsed_ms=1,
            raw={},
        )


def _post(port: int, payload: dict):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


@pytest.fixture
def serve():
    servers = []

    def start(client):
        server = OpenAICompatServer(client, port=0)
        server.start_background()
        servers.append(server)
        return server._httpd.server_address[1]

    yield start
    for server in servers:
        server.stop()


IDS = [m.key for m in MODELS]


def test_catalog_has_five_models():
    assert len(MODELS) == 5


@pytest.mark.parametrize("model", MODELS, ids=IDS)
def test_every_alias_resolves(model):
    for alias in model.aliases:
        assert resolve_model(alias) is model
        assert resolve_model(alias.upper()) is model


def test_unknown_model_rejected(serve):
    with pytest.raises(UnknownModelError):
        resolve_model("no-such-model")
    port = serve(ThinkingClient())
    status, body = _post(port, {"model": "no-such-model", "messages": [{"role": "user", "content": "hi"}]})
    assert status == 400
    assert "unknown model" in body


@pytest.mark.parametrize("model", MODELS, ids=IDS)
def test_completion_per_model_with_thinking(serve, model):
    client = ThinkingClient()
    port = serve(client)
    status, body = _post(port, {"model": model.public_id, "messages": [{"role": "user", "content": "hi"}]})
    assert status == 200, body
    payload = json.loads(body)
    assert client.last_model is model
    assert payload["model"] == model.public_id
    message = payload["choices"][0]["message"]
    assert message["content"] == "final answer"
    assert message["reasoning_content"] == "step 1: think"
    assert payload["usage"]["completion_tokens_details"]["reasoning_tokens"] == 5


@pytest.mark.parametrize("model", MODELS, ids=IDS)
def test_stream_per_model_with_thinking(serve, model):
    long_reasoning = "r" * 130  # spans several 48-char chunks
    port = serve(ThinkingClient(reasoning=long_reasoning))
    status, body = _post(
        port,
        {"model": model.key, "stream": True, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert status == 200
    events = [l[6:] for l in body.splitlines() if l.startswith("data: ")]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert all(c["model"] == model.public_id for c in chunks)
    deltas = [c["choices"][0]["delta"] for c in chunks]
    assert "".join(d.get("reasoning_content", "") for d in deltas) == long_reasoning
    assert "".join(d.get("content", "") for d in deltas) == "final answer"
    # thinking must come before the answer
    first_content = next(i for i, d in enumerate(deltas) if d.get("content"))
    last_reasoning = max(i for i, d in enumerate(deltas) if d.get("reasoning_content"))
    assert last_reasoning < first_content


@pytest.mark.parametrize("model", MODELS, ids=IDS)
def test_no_thinking_fields_when_model_gives_none(serve, model):
    port = serve(ThinkingClient(reasoning=None, reasoning_tokens=0))
    status, body = _post(port, {"model": model.key, "messages": [{"role": "user", "content": "hi"}]})
    assert status == 200
    payload = json.loads(body)
    assert "reasoning_content" not in payload["choices"][0]["message"]
    assert "completion_tokens_details" not in payload["usage"]
