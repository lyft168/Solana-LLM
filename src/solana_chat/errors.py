"""Typed exception hierarchy for the Solana Confidential Chat client."""

from __future__ import annotations


class SolanaChatError(Exception):
    """Base class for every error raised by this package."""


class AttestationError(SolanaChatError):
    """The enclave attestation bundle could not be parsed or trusted."""


class SessionError(SolanaChatError):
    """The relay session could not be established (bot gate, 4xx, ...)."""


class RelayError(SolanaChatError):
    """The relay rejected a sealed completion request (mapped error code)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class UpstreamError(SolanaChatError):
    """The enclave or relay returned an unexpected payload shape."""


class TransportError(SolanaChatError):
    """Network-level failure reaching the relay (DNS, TCP, TLS, timeout)."""


class UnknownModelError(SolanaChatError, KeyError):
    """The requested model alias is not in the catalog (client error, 400).

    Subclasses KeyError for backward compatibility with callers that
    caught KeyError from resolve_model().
    """

    def __str__(self) -> str:  # KeyError.__str__ would repr() the message
        return str(self.args[0]) if self.args else "unknown model"
