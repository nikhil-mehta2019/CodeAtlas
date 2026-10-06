"""M3 sanity tests: provider abstraction degrades gracefully without a key."""

from __future__ import annotations

import pytest

from codeatlas.llm import AnthropicProvider, NullProvider, get_default_provider
from codeatlas.llm.provider import ModelUnavailableError


def test_null_provider_unavailable_and_raises():
    provider = NullProvider()
    assert provider.is_available() is False
    with pytest.raises(ModelUnavailableError):
        provider.complete("sys", "prompt")


def test_anthropic_provider_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = AnthropicProvider()
    assert provider.is_available() is False
    with pytest.raises(ModelUnavailableError):
        provider.complete("sys", "prompt")


def test_anthropic_provider_available_with_key(monkeypatch):
    provider = AnthropicProvider(api_key="fake-key-for-test")
    assert provider.is_available() is True


def test_default_provider_falls_back_to_null_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = get_default_provider()
    assert isinstance(provider, NullProvider)
