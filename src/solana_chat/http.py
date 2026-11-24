"""Minimal HTTP transport wrapper around urllib.

We deliberately avoid a third-party HTTP stack for the bootstrap path: the
client must run on a bare VPS with `pip install` only, and the request shapes
are simple enough that urllib is sufficient. A shared cookie jar keeps the
relay session opaque (the relay sets session cookies; we never parse them).
"""

from __future__ import annotations

import http.cookiejar
import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://solana.ai"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass
class Transport:
    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 120.0
    proxy: str | None = None
    _jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)

    def __post_init__(self) -> None:
        handlers: list[urllib.request.BaseHandler] = [
            urllib.request.HTTPCookieProcessor(self._jar)
        ]
        context = ssl.create_default_context()
        handlers.append(urllib.request.HTTPSHandler(context=context))
        if self.proxy:
            handlers.append(
                urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy})
            )
        self._opener = urllib.request.build_opener(*handlers)

    @property
    def host(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.base_url).hostname or "solana.ai"

    def absolute(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        referer: str | None = None,
    ) -> Response:
        url = self.absolute(path)
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("User-Agent", self.user_agent)
        req.add_header("Accept", "*/*")
        req.add_header("Accept-Language", "en-US,en;q=0.9")
        req.add_header("Origin", self.base_url)
        if referer:
            req.add_header("Referer", referer)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                payload = resp.read()
                return Response(
                    status=resp.status,
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    body=payload,
                )
        except urllib.error.HTTPError as exc:
            payload = exc.read() if exc.fp is not None else b""
            return Response(
                status=exc.code,
                headers={k.lower(): v for k, v in (exc.headers or {}).items()},
                body=payload,
            )

    def post_json(
        self, path: str, obj, *, headers: dict[str, str] | None = None
    ) -> Response:
        merged = {"Content-Type": "application/json"}
        merged.update(headers or {})
        return self.request(
            "POST",
            path,
            body=json.dumps(obj).encode("utf-8"),
            headers=merged,
        )
