"""inspectorai-solana-chat — Python client + OpenAI-compatible bridge
for Solana Confidential Chat (https://solana.ai/chat).

Public surface:
    SolanaChatClient   low-level client: attestation, session, sealed completion
    OpenAICompatServer local OpenAI-compatible HTTP endpoint (drop-in for 9router)
    Model              model catalog entry
"""

from .catalog import DEFAULT_MODEL, MODELS, Model, resolve_model
from .client import ChatResult, SolanaChatClient
from .errors import (
    AttestationError,
    RelayError,
    SessionError,
    SolanaChatError,
    UpstreamError,
)
from .server import OpenAICompatServer

__all__ = [
    "MODELS",
    "DEFAULT_MODEL",
    "Model",
    "resolve_model",
    "ChatResult",
    "SolanaChatClient",
    "SolanaChatError",
    "AttestationError",
    "SessionError",
    "RelayError",
    "UpstreamError",
    "OpenAICompatServer",
]

__version__ = "1.0.0"
