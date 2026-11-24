"""Model catalog mirrored from solana.ai/chat.

Two identifiers per model, both required:

    key        client-side label used by x-chat-model (e.g. gpt-oss).
    sealed     enclave-side model id (e.g. gpt-oss-120b).
    public_id  OpenAI-visible id (e.g. openai/gpt-oss-120b:encrypted) that
               downstream clients/9router use as ``model``.

Keep this table in sync with the live chat app when solana.ai rolls a new
model out; nothing else in the codebase hard-codes a model name.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Model:
    key: str
    sealed: str
    public_id: str
    display_name: str
    provider: str

    @property
    def aliases(self) -> tuple[str, ...]:
        return (self.key, self.sealed, self.public_id, self.display_name)


MODELS: tuple[Model, ...] = (
    Model(
        key="gpt-oss",
        sealed="gpt-oss-120b",
        public_id="openai/gpt-oss-120b:encrypted",
        display_name="GPT-OSS 120B",
        provider="openai",
    ),
    Model(
        key="gemma-4-31b",
        sealed="gemma4-31b",
        public_id="google/gemma-4-31b-it:encrypted",
        display_name="Gemma 4 31B",
        provider="google",
    ),
    Model(
        key="deepseek-v4.1-flash",
        sealed="deepseek-v4-1-flash",
        public_id="deepseek/deepseek-v4.1-flash:encrypted",
        display_name="DeepSeek V4.1 Flash",
        provider="deepseek",
    ),
    Model(
        key="glm-5.3",
        sealed="glm-5-3",
        public_id="z-ai/glm-5.3:encrypted",
        display_name="GLM 5.3",
        provider="z-ai",
    ),
    Model(
        key="kimi-k3.1-pro",
        sealed="kimi-k3-1-pro",
        public_id="moonshotai/kimi-k3.1-pro:encrypted",
        display_name="Kimi K3.1 Pro",
        provider="moonshotai",
    ),
)

DEFAULT_MODEL: Model = MODELS[2]


def _normalise(name: str) -> str:
    return name.strip().lower()


def resolve_model(name: str | None) -> Model:
    """Resolve any alias (key, sealed id, public id, display name) to a Model.

    Raises KeyError with the available aliases when the model is unknown.
    """
    if not name:
        return DEFAULT_MODEL
    target = _normalise(name)
    for model in MODELS:
        if target in {_normalise(a) for a in model.aliases}:
            return model
    known = sorted({a for m in MODELS for a in m.aliases if a == a.lower()})
    raise KeyError(f"unknown model {name!r}; available: {', '.join(known)}")


def iter_models() -> Iterable[Model]:
    return iter(MODELS)
