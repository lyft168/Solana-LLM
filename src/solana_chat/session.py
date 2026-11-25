"""Persisted relay session state.

The relay session is just an HttpOnly cookie plus the attestation it issued.
Persisting both lets the CLI skip a fresh attest on every call and lets
multiple worker processes (or a restarted 9router bridge) share one quota.

Stored at ``$XDG_STATE_HOME/inspectorai-solana-chat/session.json`` (falls
back to ``~/.local/state/...``), mode 0600. No secrets from the enclave and
no prompt text ever land here — only the relay cookie, the cookie's issue
time, and the last-trusted enclave origin.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


def _default_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".local" / "state"
    return root / "inspectorai-solana-chat" / "session.json"


class SessionStore:
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path else _default_path()
        self._cache: dict[str, Any] | None = None
        self._lock = threading.RLock()

    # -- raw io ----------------------------------------------------------
    def load(self) -> dict[str, Any]:
        with self._lock:
            if self._cache is not None:
                return self._cache
            try:
                raw = self.path.read_text(encoding="utf-8")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("session file is not an object")
            except (FileNotFoundError, ValueError, OSError):
                data = {}
            self._cache = data
            return data

    def save(self) -> None:
        with self._lock:
            if self._cache is None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self._cache, indent=2, sort_keys=True)
            # unique temp file per write: safe across threads and processes
            fd, tmp = tempfile.mkstemp(
                prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent
            )
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    # -- cookies ---------------------------------------------------------
    def load_cookies(self) -> dict[str, str]:
        cookies = self.load().get("cookies") or {}
        if not isinstance(cookies, dict):
            return {}
        issued = self.load().get("issued_at", 0)
        age = time.time() - float(issued) if issued else None
        if age is not None and age > 6 * 3600:
            # relay cookies observed to roll hourly; anything older is stale
            return {}
        return {str(k): str(v) for k, v in cookies.items()}

    def save_cookies(self, cookies: dict[str, str]) -> None:
        with self._lock:
            data = self.load()
            data["cookies"] = cookies
            data["issued_at"] = time.time()
            self.save()

    def clear(self) -> None:
        with self._lock:
            self._cache = {}
            self.save()

    # -- attestation memo ------------------------------------------------
    def memo_attestation(self, model: str, record: dict[str, Any]) -> None:
        with self._lock:
            data = self.load()
            memos = data.setdefault("attestations", {})
            memos[model] = {**record, "stored_at": time.time()}
            self.save()

    def read_attestation(self, model: str, ttl: float = 900.0) -> dict | None:
        with self._lock:
            memos = self.load().get("attestations") or {}
            record = memos.get(model)
        if not record:
            return None
        if time.time() - float(record.get("stored_at", 0)) > ttl:
            return None
        return record

    def forget_attestation(self, model: str) -> None:
        with self._lock:
            memos = self.load().get("attestations") or {}
            if memos.pop(model, None) is not None:
                self.save()
