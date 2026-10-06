"""Anthropic Claude provider — the default ``ModelProvider`` implementation.

Requires ``ANTHROPIC_API_KEY`` in the environment. No key, no cost, no
calls — ``is_available()`` returns False and callers fall back to
``NullProvider`` behavior (findings marked UNKNOWN, never fabricated).

Model id is read from ``CODEATLAS_MODEL`` (default set below) so the
model is swappable via configuration, not a code change.
"""

from __future__ import annotations

import os

from codeatlas.llm.provider import ModelResponse, ModelUnavailableError

DEFAULT_MODEL = "claude-sonnet-5-5"


class AnthropicProvider:
    provider_id = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._model = model or os.environ.get("CODEATLAS_MODEL", DEFAULT_MODEL)
        self._client = None

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(self, system: str, prompt: str, *, max_tokens: int = 2000) -> ModelResponse:
        if not self.is_available():
            raise ModelUnavailableError(
                "ANTHROPIC_API_KEY is not set; cannot call the Anthropic API."
            )
        client = self._get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = getattr(response, "usage", None)
        return ModelResponse(
            text=text,
            model_id=self._model,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )
