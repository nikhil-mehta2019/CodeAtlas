"""Secret detection and redaction — see ARCHITECTURE.md §8.

Defense-in-depth, not a guarantee: regex rules for common secret shapes
plus a Shannon-entropy check on assigned string literals. Every excerpt
that is about to become an Evidence record or a log line must go through
``redact()`` first.

Known limitation (documented, not hidden): this will miss novel secret
formats. It is deliberately conservative (prefers false positives over
leaking a real key) because the cost of over-redacting a findings excerpt
is low and the cost of leaking a secret is high.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret_key", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("generic_bearer_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.=]{20,}")),
    (
        "generic_secret_assignment",
        re.compile(
            r"(?i)(secret|api[_-]?key|token|password|passwd|pwd|access[_-]?key)"
            r"\s*[=:]\s*['\"][^'\"\s]{8,}['\"]"
        ),
    ),
    ("connection_string_with_creds", re.compile(r"(?i)(?:[a-z]+://)[^\s:/@'\"]+:[^\s:/@'\"]+@[^\s'\"]+")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
]

_ASSIGNED_STRING = re.compile(r"""['"]([A-Za-z0-9+/=_\-]{16,})['"]""")

_ENTROPY_THRESHOLD = 4.0  # bits/char; typical secrets land well above this


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(s)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


@dataclass
class RedactionResult:
    text: str
    matched_rules: list[str]

    @property
    def had_match(self) -> bool:
        return bool(self.matched_rules)


def redact(text: str) -> RedactionResult:
    """Return a copy of ``text`` with likely secrets replaced."""
    matched: list[str] = []
    out = text

    for rule_name, pattern in _RULES:
        def _sub(m: re.Match[str], rule_name: str = rule_name) -> str:
            matched.append(rule_name)
            return f"«REDACTED:{rule_name}»"

        out = pattern.sub(_sub, out)

    def _entropy_sub(m: re.Match[str]) -> str:
        candidate = m.group(1)
        if _shannon_entropy(candidate) >= _ENTROPY_THRESHOLD and len(candidate) >= 20:
            matched.append("high_entropy_string")
            return m.group(0)[0] + f"«REDACTED:high_entropy_string»" + m.group(0)[-1]
        return m.group(0)

    out = _ASSIGNED_STRING.sub(_entropy_sub, out)

    return RedactionResult(text=out, matched_rules=matched)
