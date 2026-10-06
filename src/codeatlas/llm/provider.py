"""Model provider abstraction — ARCHITECTURE.md §2, §25 of the spec.

Everything above this module (the Analysis Engine) depends only on
``ModelProvider``. Swapping Anthropic for another vendor, or for a local
model, means writing one new class here — no analyzer code changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ModelResponse:
    text: str
    model_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelUnavailableError(RuntimeError):
    """Raised when a provider cannot serve a request (no key, network, etc.)."""


class ModelProvider(Protocol):
    provider_id: str

    def is_available(self) -> bool:
        """Whether this provider can currently serve requests (e.g. API key present)."""
        ...

    def complete(self, system: str, prompt: str, *, max_tokens: int = 2000) -> ModelResponse:
        """Single-turn completion. Raises ModelUnavailableError if it cannot run."""
        ...
