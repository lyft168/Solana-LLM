"""Challenge-provider and session-store tests (no network, no shell)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from solana_chat.client import SolanaChatClient, _run_solve_command
from solana_chat.errors import SessionError
from solana_chat.session import SessionStore

TOKEN = {"b": 0, "v": 0.31, "e": "tok", "s": "sig", "d": 0, "vr": "3"}

EMIT_TOKEN = f"import json, sys; sys.stdout.write(json.dumps({TOKEN!r}))"


def _argv(*parts: str) -> str:
    return " ".join(str(p) for p in parts)


def test_run_solve_command_parses_json(tmp_path: Path):
    script = tmp_path / "emit.py"
    script.write_text(EMIT_TOKEN)
    token = _run_solve_command(
        _argv(sys.executable, script), "/api/chat/session", "POST"
    )
    assert token == TOKEN


def test_run_solve_command_rejects_nonzero(tmp_path: Path):
    script = tmp_path / "fail.py"
    script.write_text("import sys; sys.stderr.write('boom'); sys.exit(3)")
    with pytest.raises(SessionError, match="boom"):
        _run_solve_command(_argv(sys.executable, script), "/api/chat/session", "POST")


def test_run_solve_command_rejects_garbage(tmp_path: Path):
    script = tmp_path / "garbage.py"
    script.write_text("print('not json')")
    with pytest.raises(SessionError, match="not JSON"):
        _run_solve_command(_argv(sys.executable, script), "/api/chat/session", "POST")


def test_from_solve_command_wires_provider(tmp_path: Path):
    script = tmp_path / "emit.py"
    script.write_text(EMIT_TOKEN)
    client = SolanaChatClient.from_solve_command(
        _argv(sys.executable, script),
        session_store=SessionStore(tmp_path / "session.json"),
    )
    assert client._challenge_provider is not None
    assert client._challenge_provider("/api/chat/session", "POST") == TOKEN


def test_session_store_roundtrip_and_expiry(tmp_path: Path):
    store = SessionStore(tmp_path / "state" / "session.json")
    store.save_cookies({"relay": "abc"})
    assert SessionStore(store.path).load_cookies() == {"relay": "abc"}
    assert (store.path.stat().st_mode & 0o777) == 0o600
    data = json.loads(store.path.read_text())
    data["issued_at"] = time.time() - 7 * 3600
    store.path.write_text(json.dumps(data))
    assert SessionStore(store.path).load_cookies() == {}


def test_session_store_memo_ttl(tmp_path: Path):
    store = SessionStore(tmp_path / "session.json")
    store.memo_attestation("deepseek-v4-1-flash", {"hpke_public_key": "ab"})
    memo = store.read_attestation("deepseek-v4-1-flash")
    assert memo is not None and memo["hpke_public_key"] == "ab"
    assert store.read_attestation("deepseek-v4-1-flash", ttl=-1) is None


def test_session_clear(tmp_path: Path):
    store = SessionStore(tmp_path / "session.json")
    store.save_cookies({"x": "y"})
    store.clear()
    assert SessionStore(store.path).load_cookies() == {}
