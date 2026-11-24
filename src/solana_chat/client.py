"""High-level Solana Confidential Chat client.

Flow (matches the reference browser implementation):

    1. POST /api/chat/session           -> 204, sets relay session cookie
    2. POST /api/chat/attest            -> bundle {enclave report, sigstore,
                                           enclave cert, digest, release tag}
    3. extract the HPKE public key      -> from the enclave TLS SAN
    4. HPKE seal the JSON completion    -> ehbp framing + x-* headers
    5. POST /api/chat/complete          -> AEAD-framed JSON response

Steps 2-3 depend on envelope attestation material that the relay rotates.
The client parses the bundle defensively and raises AttestationError on any
shape mismatch rather than sealing to an unverified key.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import hpke
from .catalog import Model, resolve_model
from .errors import (
    AttestationError,
    RelayError,
    SessionError,
    UpstreamError,
)
from .http import DEFAULT_USER_AGENT, Response, Transport
from .session import SessionStore

MAX_COMPLETION_TOKENS = 4096
MAX_CHAT_MESSAGES = 20
MAX_MESSAGE_CHARS = 32768
EPSILON = 1e-9

RELAY_ERRORS = {
    "bot": "browser challenge failed; rotate egress IP / run fresh",
    "busy": "shared demo pool is busy",
    "chat_message_limit": "chat hit its per-chat message cap",
    "demo_exhausted": "free-tier budget exhausted",
    "forbidden": "request forbidden",
    "invalid_request": "request body rejected by relay",
    "rate_limited": "network-level rate limit",
    "session_limit": "hourly message limit reached",
    "session_required": "session cookie missing/expired",
    "timeout": "enclave timed out",
    "too_large": "payload too large",
    "unavailable": "relay/enclave unavailable",
    "unsupported_type": "media type rejected",
    "upstream": "upstream model error",
}

_HPKE_PREFIX = re.compile(r"^hpke_", re.IGNORECASE)


@dataclass
class ChatResult:
    content: str
    reasoning: str | None
    model: Model
    usage: dict[str, int]
    truncated: bool
    elapsed_ms: int
    raw: dict[str, Any]


@dataclass
class Attestation:
    hpke_public_key: bytes
    enclave_origin: str
    digest: str
    release_tag: str | None
    domain: str
    protocol: str


def _run_solve_command(
    command: str, path: str, method: str, timeout: float = 45.0
) -> dict | None:
    env = dict(os.environ)
    env.setdefault("SOLANA_CHAT_CHALLENGE_PATH", path)
    env.setdefault("SOLANA_CHAT_CHALLENGE_METHOD", method)
    try:
        args = shlex.split(command)
        if not args:
            raise SessionError("challenge command is empty")
        proc = subprocess.run(  # noqa: S603
            args,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise SessionError(f"challenge command timed out after {timeout:.0f}s") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace").strip()[:300]
        raise SessionError(f"challenge command failed: {stderr or 'no stderr'}")
    raw = proc.stdout.decode("utf-8", "replace").strip()
    if not raw:
        raise SessionError("challenge command produced no token")
    try:
        token = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SessionError(f"challenge token is not JSON: {raw[:120]}") from exc
    if not isinstance(token, dict):
        raise SessionError("challenge token is not an object")
    return token


class _ASNDecoder:
    """Tiny DER reader; enough for X.509 v3 + extension walk."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def _read_len(self) -> int:
        first = self.data[self.pos]
        self.pos += 1
        if first & 0x80 == 0:
            return first
        count = first & 0x7F
        value = int.from_bytes(self.data[self.pos : self.pos + count], "big")
        self.pos += count
        return value

    def tlv(self) -> tuple[int, bytes]:
        tag = self.data[self.pos]
        self.pos += 1
        length = self._read_len()
        value = self.data[self.pos : self.pos + length]
        self.pos += length
        return tag, value

    def children(self, value: bytes) -> list[tuple[int, bytes]]:
        out: list[tuple[int, bytes]] = []
        sub = _ASNDecoder(value)
        while sub.pos < len(sub.data):
            out.append(sub.tlv())
        return out


def extract_sans(pem_or_der: str | bytes) -> list[str]:
    if isinstance(pem_or_der, str):
        if "-----BEGIN" in pem_or_der:
            body = re.sub(
                r"-----BEGIN CERTIFICATE-----|-----END CERTIFICATE-----|\s+",
                "",
                pem_or_der,
            )
            der = base64.b64decode(body)
        else:
            der = base64.b64decode(pem_or_der)
    else:
        der = pem_or_der
    # certificate ::= SEQUENCE { tbsCertificate, sigAlg, sigValue }
    _, cert = _ASNDecoder(der).tlv()
    tbs_children = _ASNDecoder(cert).children(cert)
    tbs = tbs_children[0][1]
    fields = _ASNDecoder(tbs).children(tbs)
    for tag, value in fields:
        if tag != 0xA3:  # [3] EXPLICIT Extensions
            continue
        _, ext_seq = _ASNDecoder(value).tlv()
        for _, ext in _ASNDecoder(ext_seq).children(ext_seq):
            parts = _ASNDecoder(ext).children(ext)
            oid_raw = parts[0][1]
            if _decode_oid(oid_raw) != "2.5.29.17":
                continue
            _, names_seq = _ASNDecoder(parts[-1][1]).tlv()
            names: list[str] = []
            for tag, name_value in _ASNDecoder(names_seq).children(names_seq):
                if tag == 0x82:  # dNSName
                    names.append(name_value.decode("ascii", "replace"))
            return names
    return []


def _decode_oid(raw: bytes) -> str:
    if not raw:
        return ""
    first = raw[0]
    parts = [str(first // 40), str(first % 40)]
    value = 0
    for byte in raw[1:]:
        value = (value << 7) | (byte & 0x7F)
        if byte & 0x80 == 0:
            parts.append(str(value))
            value = 0
    return ".".join(parts)


def _decode_base32(data: str) -> bytes:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    out = bytearray()
    acc = 0
    bits = 0
    for char in data.rstrip("="):
        acc = (acc << 5) | alphabet.index(char)
        bits += 5
        if bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    return bytes(out)


def parse_attestation_bundle(bundle: dict[str, Any]) -> Attestation:
    for field_name in (
        "enclaveAttestationReport",
        "vcek",
        "digest",
        "releaseTag",
        "sigstoreBundle",
        "domain",
        "enclaveCert",
    ):
        if field_name not in bundle:
            raise AttestationError(f"bundle missing field {field_name}")
    cert = bundle["enclaveCert"]
    sans = extract_sans(cert)
    if not sans:
        raise AttestationError("enclave certificate carries no SANs")
    hpke_san = next((s for s in sans if ".hpke." in s), None)
    if not hpke_san:
        raise AttestationError("no hpke SAN in enclave certificate")
    prefix = hpke_san.split(".hpke.")[0]
    # base32-encoded public key, embedded as the left-most label
    try:
        hpke_key = _decode_base32(prefix.split(".")[0])
    except ValueError as exc:
        raise AttestationError(f"hpke SAN is not base32: {exc}") from exc
    if len(hpke_key) != 32:
        raise AttestationError("hpke public key is not 32 bytes")
    domain = bundle["domain"]
    # Tinfoil enclave hosts look like "<name>.tinfoil.sh" or use the '#'
    # subdomain style ("solana#chat.tinfoil.sh"); both must be accepted.
    if not re.fullmatch(r"[a-z0-9#-]+(\.[a-z0-9-]+)*\.tinfoil\.sh", domain):
        raise AttestationError(f"untrusted enclave host {domain!r}")
    return Attestation(
        hpke_public_key=hpke_key,
        enclave_origin=f"https://{domain}",
        digest=bundle["digest"],
        release_tag=bundle.get("releaseTag"),
        domain=domain,
        protocol="ehbp-v1",
    )


def validate_history(history: list[dict[str, str]]) -> str | None:
    if not history:
        return "empty"
    if len(history) > MAX_CHAT_MESSAGES:
        return "full"
    total = sum(len(m.get("content", "")) for m in history)
    if total == 0:
        return "empty"
    if any(len(m.get("content", "")) > MAX_MESSAGE_CHARS for m in history):
        return "prompt_too_long"
    if history[-1].get("role") != "user":
        return "malformed"
    for message in history:
        role = message.get("role")
        content = message.get("content", "")
        if not content.strip():
            return "malformed"
        if role not in ("user", "assistant"):
            return "malformed"
    return None


class SolanaChatClient:
    def __init__(
        self,
        base_url: str = "https://solana.ai",
        *,
        user_agent: str | None = None,
        proxy: str | None = None,
        timeout: float = 120.0,
        transport: Transport | None = None,
        challenge_provider: Callable[[str, str], dict | None] | None = None,
        session_store: SessionStore | None = None,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.transport = transport or Transport(
            base_url=base_url,
            user_agent=user_agent or DEFAULT_USER_AGENT,
            timeout=timeout,
            proxy=proxy,
        )
        self.base_url = self.transport.base_url
        self._challenge_provider = challenge_provider
        self._store = session_store or SessionStore()
        self._log = logger or (lambda _msg: None)
        self._session_ready = False
        # Seed the cookie jar from a persisted session, if any.
        for name, value in self._store.load_cookies().items():
            from http.cookiejar import Cookie

            cookie = Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain=self.transport.host,
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
            self.transport._jar.set_cookie(cookie)  # noqa: SLF001

    # -- session ---------------------------------------------------------
    def ensure_session(self, force: bool = False) -> None:
        if self._session_ready and not force:
            return
        challenge = None
        if self._challenge_provider:
            challenge = self._challenge_provider("/api/chat/session", "POST")
        headers = {"Content-Type": "application/json"}
        if challenge:
            headers.update(
                {
                    "x-is-human": json.dumps(challenge, separators=(",", ":")),
                    "x-path": "/api/chat/session",
                    "x-method": "POST",
                }
            )
        resp = self.transport.request(
            "POST",
            "/api/chat/session",
            body=b"{}",
            headers=headers,
            referer=self.base_url + "/chat",
        )
        if resp.status == 204:
            self._session_ready = True
            cookies = {
                c.name: c.value
                for c in self.transport._jar  # noqa: SLF001
            }
            self._store.save_cookies(cookies)
            return
        code = self._relay_code(resp)
        raise SessionError(
            f"session failed: HTTP {resp.status} ({code or resp.text()[:120]})"
        )

    # -- attestation -----------------------------------------------------
    def attest(self, model: Model, nonce: str) -> Attestation:
        resp = self._with_session(
            "POST", "/api/chat/attest", {"model": model.sealed, "nonce": nonce}
        )
        if not resp.ok:
            raise AttestationError(
                f"attest failed: HTTP {resp.status} {resp.text()[:160]}"
            )
        payload = resp.json()
        if payload.get("protocol") != "ehbp-v1":
            raise AttestationError(
                f"unsupported attestation protocol {payload.get('protocol')!r}"
            )
        return parse_attestation_bundle(payload["bundle"])

    # -- completion ------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | Model | None = None,
        max_completion_tokens: int = MAX_COMPLETION_TOKENS,
    ) -> ChatResult:
        if isinstance(model, Model):
            catalog = model
        elif isinstance(model, str):
            catalog = resolve_model(model)
        else:
            catalog = resolve_model(None)
        problem = validate_history(messages)
        if problem in ("empty", "full"):
            raise UpstreamError(f"conversation invalid: {problem}")
        if problem:
            raise UpstreamError(f"conversation malformed: {problem}")
        started = time.monotonic()
        nonce = hpke.generate_nonce(32)
        attestation = self.attest(catalog, nonce)
        request_json = json.dumps(
            {
                "max_completion_tokens": max_completion_tokens,
                "messages": [
                    {"content": m["content"], "role": m["role"]} for m in messages
                ],
                "model": catalog.key,
                "stream": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        ctx = hpke.setup_base_sender(attestation.hpke_public_key, hpke.REQUEST_INFO)
        sealed_body = hpke.seal_stream(ctx, request_json)
        headers = {
            "Content-Type": "application/octet-stream",
            hpke.HDR_ENCAPSULATED_KEY: ctx.enc.hex(),
            "x-enclave-origin": attestation.enclave_origin,
            "x-chat-model": catalog.key,
            "x-chat-id": hashlib.sha256(nonce.encode()).hexdigest()[:32],
        }
        resp = self._with_session(
            "POST",
            "/api/chat/complete",
            None,
            raw_body=sealed_body,
            headers=headers,
        )
        if not resp.ok:
            code = self._relay_code(resp)
            raise RelayError(
                code or f"http_{resp.status}",
                RELAY_ERRORS.get(code, resp.text()[:160]),
            )
        response_nonce_hex = resp.headers.get(hpke.HDR_RESPONSE_NONCE)
        if not response_nonce_hex:
            raise UpstreamError("relay response missing ehbp-response-nonce")
        response_nonce = bytes.fromhex(response_nonce_hex)
        exported = ctx.export(hpke.EXPORT_LABEL, 32)
        key, nonce_base = hpke.derive_response_keys(exported, ctx.enc, response_nonce)
        plaintext = hpke.open_stream(resp.body, key, nonce_base)
        payload = json.loads(plaintext)
        return self._parse_completion(payload, catalog, started)

    # -- helpers ---------------------------------------------------------
    def _parse_completion(
        self, payload: dict[str, Any], catalog: Model, started: float
    ) -> ChatResult:
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            content = message["content"]
            reasoning = message.get("reasoning_content") or message.get("reasoning")
            usage = payload["usage"]
        except (KeyError, IndexError, TypeError) as exc:
            raise UpstreamError(f"unexpected completion shape: {exc}") from exc
        return ChatResult(
            content=content,
            reasoning=reasoning,
            model=catalog,
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
                "reasoning_tokens": int(
                    (usage.get("completion_tokens_details") or {}).get(
                        "reasoning_tokens", 0
                    )
                ),
            },
            truncated=choice.get("finish_reason") == "length",
            elapsed_ms=int((time.monotonic() - started) * 1000),
            raw=payload,
        )

    def _with_session(
        self,
        method: str,
        path: str,
        obj: dict | None = None,
        *,
        raw_body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        self.ensure_session()
        resp = self._send(method, path, obj, raw_body, headers)
        if resp.status == 401:
            self.ensure_session(force=True)
            resp = self._send(method, path, obj, raw_body, headers)
        return resp

    def _send(
        self,
        method: str,
        path: str,
        obj: dict | None,
        raw_body: bytes | None,
        headers: dict[str, str] | None,
    ) -> Response:
        merged = {"Content-Type": "application/json"}
        merged.update(headers or {})
        body = raw_body
        if body is None and obj is not None:
            body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        elif body is None:
            body = b"{}"
        return self.transport.request(
            method,
            path,
            body=body,
            headers=merged,
            referer=self.base_url + "/chat",
        )

    @classmethod
    def from_solve_command(cls, command: str, **kwargs) -> SolanaChatClient:
        """Build a client whose `x-is-human` token comes from a local shim.

        ``command`` must print one JSON challenge object on stdout, e.g.
        ``node tools/botid_browser.mjs --print-once``. The relay is bot-gated;
        this is the supported way to satisfy that gate without forging tokens.
        """

        def provider(path: str, method: str) -> dict | None:
            return _run_solve_command(command, path, method)

        return cls(challenge_provider=provider, **kwargs)

    @staticmethod
    def _relay_code(resp: Response) -> str | None:
        try:
            payload = resp.json()
        except Exception:
            return None
        error = payload.get("error")
        if isinstance(error, dict):
            return error.get("code")
        if isinstance(error, str):
            return error
        return None
