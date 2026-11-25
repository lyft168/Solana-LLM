"""OpenAI-compatible local HTTP bridge.

Exposes the subset of the OpenAI Chat Completions surface that coding agents
and 9router actually call:

    GET  /v1/models
    POST /v1/chat/completions        (stream=true supported, SSE)
    GET  /v1/health
    GET  /v1/tools                   (tool-call capability probe)

Every request is translated to solana.ai/chat's sealed EHBP call via
SolanaChatClient. Bearer auth is optional: set SOLANA_CHAT_API_KEY to require
a token, otherwise the endpoint is bound to loopback only by default.

Tool calls: the upstream model does not emit OpenAI tool_calls natively, so
the bridge injects a strict JSON-tool protocol and re-parses the reply into
tool_calls / content. That gives 9router, Cline, Continue and friends a
working function-calling surface on top of a plain chat model.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .catalog import MODELS, resolve_model
from .client import ChatResult, SolanaChatClient
from .errors import SolanaChatError, UnknownModelError

TOOL_INSTRUCTION = (
    "You can call tools. When a tool is required, respond with ONLY a "
    "single JSON object and nothing else:\n"
    '{"tool_calls":[{"name":"<tool>","arguments":{...}}]}\n'
    "Never wrap it in prose or code fences. If no tool is needed, reply "
    "normally in plain text."
)

MAX_BODY_BYTES = int(os.environ.get("SOLANA_CHAT_MAX_BODY", str(1 << 20)))
_DECODER = json.JSONDecoder()


def _find_tool_json(text: str) -> tuple[dict, int, int] | None:
    """Return the first balanced JSON object containing a tool_calls list."""
    pos = text.find("{")
    while pos != -1:
        try:
            obj, end = _DECODER.raw_decode(text, pos)
        except json.JSONDecodeError:
            pos = text.find("{", pos + 1)
            continue
        if isinstance(obj, dict) and isinstance(obj.get("tool_calls"), list):
            return obj, pos, end
        pos = text.find("{", pos + 1)
    return None


def _flatten_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Collapse OpenAI message shapes into the plain user/assistant pairs
    the relay accepts (system/tool/function roles get folded into content).
    """
    out: list[dict[str, str]] = []
    pending_system: list[str] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        content = content or ""
        if role == "assistant" and message.get("tool_calls"):
            # the relay only sees text, so replay the call in the same JSON
            # protocol the model was told to emit: it keeps the tool name and
            # arguments in context instead of an opaque placeholder
            calls = []
            for call in message.get("tool_calls") or []:
                fn = (call or {}).get("function") or {}
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        pass
                calls.append({"name": fn.get("name", "unknown"), "arguments": args})
            replay = json.dumps({"tool_calls": calls}, separators=(",", ":"))
            content = f"{content}\n\n{replay}" if content else replay
        if role == "system":
            pending_system.append(content)
            continue
        if role == "tool":
            role = "user"
            content = f"[tool result {message.get('tool_call_id', '')}]\n{content}"
        if role == "function":
            role = "user"
            content = f"[function result]\n{content}"
        if role not in ("user", "assistant"):
            role = "user"
        if pending_system and role == "user":
            content = "\n\n".join(pending_system + [content])
            pending_system.clear()
        out.append({"role": role, "content": content})
    if pending_system:
        if out and out[-1]["role"] == "user":
            out[-1]["content"] = "\n\n".join(pending_system + [out[-1]["content"]])
        else:
            out.append({"role": "user", "content": "\n\n".join(pending_system)})
    # relay requires strict user/assistant alternation ending on user
    merged: list[dict[str, str]] = []
    for message in out:
        if merged and merged[-1]["role"] == message["role"]:
            merged[-1]["content"] += "\n\n" + message["content"]
        else:
            merged.append(dict(message))
    if not merged or merged[-1]["role"] != "user":
        merged.append({"role": "user", "content": "continue"})
    return merged


def _render_tools(tools: list[dict[str, Any]]) -> str:
    lines = ["# Available tools"]
    for tool in tools:
        fn = (tool or {}).get("function") or {}
        name = fn.get("name", "unknown")
        description = fn.get("description", "").strip()
        schema = fn.get("parameters") or {}
        lines.append(
            f"- {name}: {description}\n  parameters: "
            f"{json.dumps(schema, separators=(',', ':'))}"
        )
    return "\n".join(lines)


def _extract_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    calls = payload.get("tool_calls")
    if not isinstance(calls, list):
        return []
    result: list[dict[str, Any]] = []
    for idx, call in enumerate(calls):
        if not isinstance(call, dict):
            continue
        name = call.get("name")
        arguments = call.get("arguments", {})
        if not isinstance(name, str):
            continue
        if isinstance(arguments, str):
            # some models emit the arguments as a JSON string; if it is not
            # valid JSON, pass it through verbatim so the client sees the
            # error instead of the tool silently running with {}
            try:
                json.loads(arguments)
                encoded = arguments
            except json.JSONDecodeError:
                encoded = arguments
        else:
            encoded = json.dumps(arguments, separators=(",", ":"))
        result.append(
            {
                "id": f"call_{int(time.time() * 1000)}_{idx}",
                "type": "function",
                "function": {"name": name, "arguments": encoded},
            }
        )
    return result


def _parse_tool_calls(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Find the first balanced JSON object with a tool_calls list."""
    if '"tool_calls"' not in text:
        return text, []
    found = _find_tool_json(text)
    if not found:
        return text, []
    payload, start, end = found
    calls = _extract_calls(payload)
    if not calls:
        return text, []
    return (text[:start] + text[end:]).strip(), calls


class OpenAICompatServer:
    def __init__(
        self,
        client: SolanaChatClient,
        *,
        host: str = "127.0.0.1",
        port: int = 20129,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self.client = client
        self.host = host
        self.port = port
        self.api_key = api_key
        self.default_model = default_model
        self._httpd: ThreadingHTTPServer | None = None

    # -- lifecycle -------------------------------------------------------
    def make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "inspectorai-solana-chat/1.0"

            def log_message(self, fmt, *args):  # quieter default logging
                return

            def do_GET(self):  # noqa: N802
                if self.path.startswith("/v1/models"):
                    self._json(200, server._models_payload())
                elif self.path.startswith("/v1/health"):
                    self._json(200, {"status": "ok", "upstream": "solana.ai/chat"})
                elif self.path.startswith("/v1/tools"):
                    self._json(
                        200,
                        {
                            "object": "tools",
                            "tool_calls": True,
                            "streaming": True,
                        },
                    )
                else:
                    self._json(404, {"error": {"message": "not found"}})

            def do_POST(self):  # noqa: N802
                if not self.path.startswith("/v1/chat/completions"):
                    self._json(404, {"error": {"message": "not found"}})
                    return
                if not self._authorized():
                    self._json(
                        401,
                        {"error": {"message": "invalid api key", "code": 401}},
                    )
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_BODY_BYTES:
                    self.close_connection = True
                    self._json(413, {"error": {"message": "request body too large"}})
                    return
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    request = json.loads(raw)
                except json.JSONDecodeError:
                    self._json(400, {"error": {"message": "invalid json"}})
                    return
                try:
                    server._handle_chat(self, request)
                except UnknownModelError as exc:
                    # only a bad model name is a client error; any other
                    # KeyError is a real bug and must surface as a 500
                    self._json(
                        400,
                        {
                            "error": {
                                "message": str(exc),
                                "type": "invalid_request",
                            }
                        },
                    )
                except SolanaChatError as exc:
                    self._json(
                        502,
                        {
                            "error": {
                                "message": str(exc),
                                "type": exc.__class__.__name__,
                            }
                        },
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    self._json(500, {"error": {"message": f"internal: {exc}"}})

            # -- helpers ---------------------------------------------
            def _authorized(self) -> bool:
                if not server.api_key:
                    return True
                header = self.headers.get("Authorization", "")
                return hmac.compare_digest(
                    header.encode("utf-8"), f"Bearer {server.api_key}".encode("utf-8")
                )

            def _json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _sse(self, payload: dict) -> None:
                chunk = f"data: {json.dumps(payload)}\n\n".encode()
                self.wfile.write(chunk)
                self.wfile.flush()

            def _sse_done(self) -> None:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        return Handler

    def start_background(self) -> threading.Thread:
        handler = self.make_handler()
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        thread.start()
        return thread

    def serve_forever(self) -> None:
        handler = self.make_handler()
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._httpd.serve_forever()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()

    # -- payload builders ------------------------------------------------
    def _models_payload(self) -> dict:
        created = int(time.time())
        return {
            "object": "list",
            "data": [
                {
                    "id": model.public_id,
                    "object": "model",
                    "created": created,
                    "owned_by": model.provider,
                    "permission": [],
                    "root": model.public_id,
                    "parent": None,
                }
                for model in MODELS
            ],
        }

    def _handle_chat(self, handler, request: dict) -> None:
        model_name = request.get("model") or self.default_model
        catalog = resolve_model(model_name)
        messages = _flatten_messages(request.get("messages", []))
        tools = request.get("tools") or []
        if tools:
            messages.insert(
                0,
                {
                    "role": "user",
                    "content": f"{TOOL_INSTRUCTION}\n\n{_render_tools(tools)}",
                },
            )
            # collapse the synthetic first message into the first real turn
            merged = []
            for message in messages:
                if merged and merged[-1]["role"] == message["role"]:
                    merged[-1]["content"] += "\n\n" + message["content"]
                else:
                    merged.append(dict(message))
            messages = merged
        max_tokens = int(
            request.get("max_completion_tokens") or request.get("max_tokens") or 4096
        )
        result = self.client.chat(
            messages, model=catalog, max_completion_tokens=max_tokens
        )
        content, tool_calls = _parse_tool_calls(result.content)
        finish_reason = (
            "tool_calls" if tool_calls else ("length" if result.truncated else "stop")
        )
        payload = self._completion_payload(
            catalog.public_id, content, tool_calls, finish_reason, result
        )
        if request.get("stream"):
            self._stream(handler, payload, catalog.public_id)
        else:
            handler._json(200, payload)

    @staticmethod
    def _completion_payload(
        model_id: str,
        content: str,
        tool_calls: list[dict],
        finish_reason: str,
        result: ChatResult,
    ) -> dict:
        message: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls
            message["content"] = content or None
        return {
            "id": f"chatcmpl-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": result.usage["prompt_tokens"],
                "completion_tokens": result.usage["completion_tokens"],
                "total_tokens": result.usage["prompt_tokens"]
                + result.usage["completion_tokens"],
            },
        }

    def _stream(self, handler, payload: dict, model_id: str) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        # No Content-Length: the connection itself delimits the body, so we
        # must close it after [DONE] or keep-alive clients wait for more.
        handler.send_header("Connection", "close")
        handler.close_connection = True
        handler.end_headers()
        base = {
            "id": payload["id"],
            "object": "chat.completion.chunk",
            "created": payload["created"],
            "model": model_id,
        }
        chunk0 = {
            **base,
            "choices": [
                {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
            ],
        }
        handler._sse(chunk0)
        message = payload["choices"][0]["message"]
        if message.get("tool_calls"):
            for idx, call in enumerate(message["tool_calls"]):
                handler._sse(
                    {
                        **base,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": idx,
                                            "id": call["id"],
                                            "type": "function",
                                            "function": call["function"],
                                        }
                                    ]
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                )
        else:
            text = message.get("content") or ""
            for start in range(0, len(text), 48):
                handler._sse(
                    {
                        **base,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": text[start : start + 48]},
                                "finish_reason": None,
                            }
                        ],
                    }
                )
        handler._sse(
            {
                **base,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": payload["choices"][0]["finish_reason"],
                    }
                ],
                "usage": payload["usage"],
            }
        )
        handler._sse_done()
