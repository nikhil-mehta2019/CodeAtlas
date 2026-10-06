"""Model provider abstraction (ARCHITECTURE.md §2, §25)."""

from __future__ import annotations

from codeatlas.llm.anthropic_provider import AnthropicProvider
from codeatlas.llm.null_provider import NullProvider
from codeatlas.llm.provider import ModelProvider, ModelResponse, ModelUnavailableError


def get_default_provider() -> ModelProvider:
    """Anthropic if ANTHROPIC_API_KEY is set, else the Null provider."""
    anthropic = AnthropicProvider()
    if anthropic.is_available():
        return anthropic
    return NullProvider()


__all__ = [
    "ModelProvider",
    "ModelResponse",
    "ModelUnavailableError",
    "AnthropicProvider",
    "NullProvider",
    "get_default_provider",
]
