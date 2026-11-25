"""Command-line interface: solana-chat / scchat."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from . import __version__
from .catalog import DEFAULT_MODEL, MODELS, resolve_model
from .client import SolanaChatClient
from .errors import SolanaChatError
from .hpke import generate_nonce
from .http import Transport
from .server import OpenAICompatServer
from .session import SessionStore


def _client(args) -> SolanaChatClient:
    store = SessionStore(args.session_file) if args.session_file else None
    solve = getattr(args, "solve_command", None) or os.environ.get(
        "SOLANA_CHAT_SOLVE_COMMAND"
    )
    if solve:
        return SolanaChatClient.from_solve_command(
            solve,
            base_url=args.base_url,
            proxy=args.proxy,
            timeout=args.timeout,
            user_agent=args.user_agent,
            session_store=store,
        )
    return SolanaChatClient(
        base_url=args.base_url,
        proxy=args.proxy,
        timeout=args.timeout,
        user_agent=args.user_agent,
        session_store=store,
    )


def cmd_models(args) -> int:
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "key": m.key,
                        "sealed": m.sealed,
                        "public_id": m.public_id,
                        "name": m.display_name,
                    }
                    for m in MODELS
                ],
                indent=2,
            )
        )
        return 0
    print(f"{'PUBLIC ID':44} {'KEY':20} {'DISPLAY'}")
    for model in MODELS:
        marker = "*" if model is DEFAULT_MODEL else " "
        print(f"{marker}{model.public_id:43} {model.key:20} {model.display_name}")
    return 0


def cmd_ask(args) -> int:
    client = _client(args)
    messages = [{"role": "user", "content": args.prompt}]
    try:
        result = client.chat(
            messages,
            model=args.model,
            max_completion_tokens=args.max_tokens,
        )
    except SolanaChatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {
                    "model": result.model.public_id,
                    "content": result.content,
                    "reasoning": result.reasoning,
                    "usage": result.usage,
                    "elapsed_ms": result.elapsed_ms,
                },
                indent=2,
            )
        )
    else:
        print(result.content)
        if args.usage:
            print(
                f"\n[{result.model.public_id} · "
                f"{result.usage['prompt_tokens']}→"
                f"{result.usage['completion_tokens']} tok · "
                f"{result.elapsed_ms} ms]",
                file=sys.stderr,
            )
    return 0


def cmd_attest(args) -> int:
    client = _client(args)
    model = resolve_model(args.model)
    nonce = args.nonce or generate_nonce(32)
    try:
        client.ensure_session()
        attestation = client.attest(model, nonce)
    except SolanaChatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "model": model.public_id,
                "nonce": nonce,
                "enclave_host": attestation.domain,
                "enclave_origin": attestation.enclave_origin,
                "release_digest": attestation.digest,
                "release_tag": attestation.release_tag,
                "hpke_public_key": attestation.hpke_public_key.hex(),
                "protocol": attestation.protocol,
            },
            indent=2,
        )
    )
    return 0


def cmd_serve(args) -> int:
    client = _client(args)
    server = OpenAICompatServer(
        client,
        host=args.host,
        port=args.port,
        api_key=args.api_key or os.environ.get("SOLANA_CHAT_API_KEY"),
        default_model=args.default_model,
    )
    api_key = args.api_key or os.environ.get("SOLANA_CHAT_API_KEY")
    print(
        f"solana-chat bridge listening on http://{args.host}:{args.port}/v1", flush=True
    )
    print("  models : GET  /v1/models", flush=True)
    print("  chat   : POST /v1/chat/completions", flush=True)
    print(f"  key    : {'set' if api_key else 'none (loopback only)'}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        server.stop()
    return 0


def cmd_doctor(args) -> int:
    checks: list[tuple[str, bool, str]] = []
    try:
        import Crypto.Cipher.AES  # noqa: F401

        checks.append(("pycryptodome", True, "AES-GCM available"))
    except ImportError:
        checks.append(("pycryptodome", False, "pip install pycryptodome"))
    from . import hpke

    sk = b"\x07" * 32
    try:
        pub = hpke.x25519_public(sk)
        ok = len(pub) == 32
        checks.append(("x25519", ok, pub.hex()[:16] + "..."))
    except Exception as exc:  # pragma: no cover
        checks.append(("x25519", False, str(exc)))
    try:
        okm = hpke.hkdf_sha256(b"ikm", b"salt", b"info", 32)
        checks.append(("hkdf-sha256", len(okm) == 32, okm.hex()[:16]))
    except Exception as exc:  # pragma: no cover
        checks.append(("hkdf-sha256", False, str(exc)))

    transport = Transport(base_url=args.base_url, proxy=args.proxy)
    started = time.monotonic()
    try:
        resp = transport.request("GET", "/chat")
        elapsed = int((time.monotonic() - started) * 1000)
        checks.append(
            ("reach solana.ai", resp.ok, f"HTTP {resp.status} in {elapsed} ms")
        )
    except Exception as exc:
        checks.append(("reach solana.ai", False, str(exc)))

    width = max(len(name) for name, _, _ in checks)
    failed = 0
    for name, ok, detail in checks:
        mark = "OK " if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{mark}] {name.ljust(width)}  {detail}")
    return 1 if failed else 0


def cmd_session(args) -> int:
    store = SessionStore(args.session_file) if args.session_file else SessionStore()
    if args.action == "clear":
        store.clear()
        print(f"cleared {store.path}")
        return 0
    data = store.load()
    cookies = data.get("cookies") or {}
    print(f"file     : {store.path}")
    print(f"exists   : {store.path.exists()}")
    print(f"cookies  : {len(cookies)} ({', '.join(cookies) or 'none'})")
    print(f"issued   : {data.get('issued_at', 'never')}")
    print(f"memos    : {len(data.get('attestations') or {})}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="solana-chat",
        description="Solana Confidential Chat CLI + OpenAI-compatible bridge",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--base-url", default="https://solana.ai", help="relay base URL"
    )
    parser.add_argument("--proxy", default=os.environ.get("SOLANA_CHAT_PROXY"))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("SOLANA_CHAT_UA"),
    )
    parser.add_argument(
        "--session-file",
        default=os.environ.get("SOLANA_CHAT_SESSION_FILE"),
        help="path to persisted relay session JSON",
    )
    parser.add_argument(
        "--solve-command",
        default=None,
        help="shell command that prints one x-is-human challenge token "
        "(e.g. 'node tools/botid_browser.mjs --print-once'); "
        "defaults to $SOLANA_CHAT_SOLVE_COMMAND",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_models = sub.add_parser("models", help="list catalog models")
    p_models.add_argument("--json", action="store_true")
    p_models.set_defaults(func=cmd_models)

    p_ask = sub.add_parser("ask", help="one-shot prompt")
    p_ask.add_argument("prompt")
    p_ask.add_argument("-m", "--model", default=None)
    p_ask.add_argument("--max-tokens", type=int, default=4096)
    p_ask.add_argument("--json", action="store_true")
    p_ask.add_argument("--usage", action="store_true")
    p_ask.set_defaults(func=cmd_ask)

    p_attest = sub.add_parser("attest", help="inspect enclave attestation")
    p_attest.add_argument("-m", "--model", default=None)
    p_attest.add_argument("--nonce", default=None)
    p_attest.set_defaults(func=cmd_attest)

    p_serve = sub.add_parser("serve", help="run OpenAI-compatible bridge")
    p_serve.add_argument(
        "--host",
        default=os.environ.get("SOLANA_CHAT_HOST", "127.0.0.1"),
    )
    p_serve.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SOLANA_CHAT_PORT", "20129")),
    )
    p_serve.add_argument("--api-key", default=None)
    p_serve.add_argument("--default-model", default=None)
    p_serve.set_defaults(func=cmd_serve)

    p_session = sub.add_parser(
        "session", help="inspect or clear the persisted relay session"
    )
    p_session.add_argument(
        "action", choices=["show", "clear"], nargs="?", default="show"
    )
    p_session.set_defaults(func=cmd_session)

    p_doctor = sub.add_parser("doctor", help="diagnose local setup")
    p_doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
