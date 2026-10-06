"""No-op provider — lets the pipeline degrade gracefully when no LLM key
is configured. AI-dependent analyzers must check ``is_available()`` and
mark the relevant findings UNKNOWN rather than fabricate output
(spec §3: Never Pretend to Know; §31: No Fake Completion).
"""

from __future__ import annotations

from codeatlas.llm.provider import ModelResponse, ModelUnavailableError


class NullProvider:
    provider_id = "null"

    def is_available(self) -> bool:
        return False

    def complete(self, system: str, prompt: str, *, max_tokens: int = 2000) -> ModelResponse:
        raise ModelUnavailableError(
            "NullProvider cannot serve completions; no model provider is configured. "
            "Set ANTHROPIC_API_KEY to enable LLM-assisted analysis."
        )
