"""Business rule analyzer — static detection of validation,
authorization-tied, and state rules (ARCHITECTURE.md §9; product spec §9
"Business Rule Discovery").

V1 scope, honestly stated:

- **Python only in this pass.** Node/TS validation-library parsing
  (Joi/Zod/Yup schema builders) and JS route+role business rules are not
  implemented here — a real gap, tracked explicitly, not silently
  skipped. Extending this analyzer to Node/TS is natural follow-up work,
  not folded into this slice (CLAUDE.md: prefer small, complete vertical
  slices over broad, partial changes).
- **Validation rules** come from declared Pydantic ``Field(...)``
  constraints (``min_length``/``max_length``/``gt``/``ge``/``lt``/``le``)
  and from whether a field has no default (``Field(...)`` with an
  Ellipsis first argument, meaning required). These are directly
  observed, explicit constraints, so they are ``explicit=True`` and
  ``CONFIRMED``.
- **Authorization-tied rules** reuse the same role/permission-decorator
  pattern ``codeatlas.analysis.authentication`` already scans for, but
  phrase it as a specific rule tied to the gated *action* (the decorated
  function's name) rather than that analyzer's aggregate authorization
  model. Both analyzers independently scan for the same decorator because
  they answer different questions — one a general mechanism, this one a
  per-action rule — so this intentionally duplicates the pattern match,
  not the conclusion. Only decorators naming a specific role are treated
  as a business rule here (a bare ``@login_required`` says "must be
  authenticated," not a role-specific business rule, so it is left to
  the authentication analyzer).
- **State rules** come from Python ``Enum`` classes whose name contains
  "status" or "state" (a conservative filter — this analyzer does not
  attempt to classify every enum in a codebase as business-relevant).
  Only the *set of valid states* is reported, at ``CONFIRMED`` (the enum
  membership is directly declared) — no specific transition between
  those states is ever asserted, since determining allowed transitions
  requires control-flow analysis this pass does not do.
- Workflow rules, data constraints expressed only in prose/comments, and
  anything requiring semantic interpretation beyond pattern matching are
  NOT detected in this pass.

Nothing here calls an LLM. No matching pattern → no rule, never a guess.
"""

from __future__ import annotations

import itertools
import re

from codeatlas.discovery.engine import DiscoveryContext
from codeatlas.evidence.schema import Evidence, SourceLocation, VerificationStatus
from codeatlas.knowledge.schema import BusinessRule

_MAX_FILES_SCANNED = 200

_PY_FIELD_PATTERN = re.compile(r"^\s*(\w+)\s*:\s*[\w\[\]\.\"']+\s*=\s*Field\(([^)]*)\)")
_NUMERIC_CONSTRAINT = re.compile(r"\b(min_length|max_length|gt|ge|lt|le)\s*=\s*(-?\d+)")

_PY_ROLE_DECORATOR_WITH_ROLE = re.compile(
    r"@(?:role_required|requires_role|roles_allowed|permission_required)\(\s*['\"]([\w\-]+)['\"]\s*\)"
)
_PY_DEF_LINE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")

_PY_CLASS_LINE = re.compile(r"^\s*class\s+(\w+)\s*\(([^)]*)\)\s*:")
_PY_ENUM_MEMBER_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*\S")


def analyze_business_rules(ctx: DiscoveryContext, walker) -> tuple[list[BusinessRule], list[Evidence]]:
    pairs: list[tuple[BusinessRule, Evidence]] = []
    pairs += _detect_pydantic_validation_rules(ctx, walker)
    pairs += _detect_role_gated_action_rules(ctx, walker)
    pairs += _detect_state_enum_rules(ctx, walker)

    rules = [rule for rule, _ in pairs]
    evidence = [ev for _, ev in pairs]
    return rules, evidence


def _py_files(ctx: DiscoveryContext):
    return itertools.islice(
        (f for f in ctx.tree.readable_files if f.relative_path.endswith(".py")), _MAX_FILES_SCANNED
    )


def _detect_pydantic_validation_rules(ctx: DiscoveryContext, walker) -> list[tuple[BusinessRule, Evidence]]:
    pairs: list[tuple[BusinessRule, Evidence]] = []

    for f in _py_files(ctx):
        try:
            text = walker.read_text(f)
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = _PY_FIELD_PATTERN.match(line)
            if not m:
                continue
            field_name, args = m.group(1), m.group(2)
            required = args.strip().startswith("...")
            constraints = _NUMERIC_CONSTRAINT.findall(args)
            if not required and not constraints:
                continue

            clauses = []
            if required:
                clauses.append("is required")
            if constraints:
                clauses.append("must satisfy " + ", ".join(f"{name}={value}" for name, value in constraints))
            rule_text = f"Field '{field_name}' " + " and ".join(clauses) + "."

            ev = Evidence(
                finding_id=f"business_rule:validation:{field_name}:{f.relative_path}:{lineno}",
                source_file=f.relative_path,
                location=SourceLocation(file=f.relative_path, line_start=lineno, line_end=lineno),
                excerpt=line.strip()[:160],
                reasoning=f"Pydantic Field constraint declared for '{field_name}' at {f.relative_path}:{lineno}.",
                confidence=0.85,
                verification_status=VerificationStatus.CONFIRMED,
                discovered_by="static",
            )
            rule = BusinessRule(
                rule=rule_text,
                kind="validation",
                explicit=True,
                status=VerificationStatus.CONFIRMED,
                confidence=0.85,
            )
            pairs.append((rule, ev))

    return pairs


def _detect_role_gated_action_rules(ctx: DiscoveryContext, walker) -> list[tuple[BusinessRule, Evidence]]:
    pairs: list[tuple[BusinessRule, Evidence]] = []

    for f in _py_files(ctx):
        try:
            text = walker.read_text(f)
        except Exception:
            continue
        lines = text.splitlines()
        for lineno, line in enumerate(lines, start=1):
            m = _PY_ROLE_DECORATOR_WITH_ROLE.search(line)
            if not m:
                continue
            role_name = m.group(1)
            action_name = _find_following_def_name(lines, lineno)
            if action_name is None:
                continue

            rule_text = f"Only users with role '{role_name}' may call '{action_name}'."
            ev = Evidence(
                finding_id=f"business_rule:authorization:{action_name}:{f.relative_path}:{lineno}",
                source_file=f.relative_path,
                location=SourceLocation(file=f.relative_path, line_start=lineno, line_end=lineno, symbol=action_name),
                excerpt=line.strip()[:160],
                reasoning=(
                    f"Role-check decorator for role '{role_name}' found directly above "
                    f"'{action_name}' at {f.relative_path}:{lineno}."
                ),
                confidence=0.8,
                verification_status=VerificationStatus.CONFIRMED,
                discovered_by="static",
            )
            rule = BusinessRule(
                rule=rule_text,
                kind="authorization",
                explicit=True,
                status=VerificationStatus.CONFIRMED,
                confidence=0.8,
            )
            pairs.append((rule, ev))

    return pairs


def _find_following_def_name(lines: list[str], decorator_lineno: int, max_lookahead: int = 3) -> str | None:
    """Look at the lines immediately after a decorator (index is 0-based;
    decorator_lineno is 1-based) for the `def name(...)` it decorates,
    tolerating a small number of stacked decorators in between."""
    for offset in range(max_lookahead):
        idx = decorator_lineno + offset  # decorator_lineno is 1-based, so this is the 0-based index of the next line
        if idx >= len(lines):
            break
        candidate = lines[idx]
        if not candidate.strip():
            continue
        def_match = _PY_DEF_LINE.match(candidate)
        if def_match:
            return def_match.group(1)
        if candidate.strip().startswith("@"):
            continue
        break
    return None


def _detect_state_enum_rules(ctx: DiscoveryContext, walker) -> list[tuple[BusinessRule, Evidence]]:
    pairs: list[tuple[BusinessRule, Evidence]] = []

    for f in _py_files(ctx):
        try:
            text = walker.read_text(f)
        except Exception:
            continue
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            m = _PY_CLASS_LINE.match(lines[i])
            if not m or not _looks_like_status_enum(m.group(1), m.group(2)):
                i += 1
                continue

            class_name, class_line = m.group(1), i + 1
            members: list[str] = []
            indent: int | None = None
            j = i + 1
            while j < len(lines):
                line = lines[j]
                if not line.strip():
                    j += 1
                    continue
                cur_indent = len(line) - len(line.lstrip())
                if indent is None:
                    indent = cur_indent
                if cur_indent < indent:
                    break
                member_match = _PY_ENUM_MEMBER_LINE.match(line)
                if member_match and not line.strip().startswith("def "):
                    members.append(member_match.group(1))
                j += 1

            if members:
                rule_text = f"Entity state '{class_name}' is constrained to the following values: {', '.join(members)}."
                ev = Evidence(
                    finding_id=f"business_rule:state:{class_name}:{f.relative_path}",
                    source_file=f.relative_path,
                    location=SourceLocation(file=f.relative_path, line_start=class_line, symbol=class_name),
                    excerpt=lines[i].strip()[:160],
                    reasoning=(
                        f"Enum class '{class_name}' declares {len(members)} member(s): {', '.join(members)}. "
                        "No transition logic between these states was analyzed."
                    ),
                    confidence=0.8,
                    verification_status=VerificationStatus.CONFIRMED,
                    discovered_by="static",
                )
                rule = BusinessRule(
                    rule=rule_text,
                    kind="state_transition",
                    explicit=True,
                    status=VerificationStatus.CONFIRMED,
                    confidence=0.8,
                )
                pairs.append((rule, ev))

            i = j

    return pairs


def _looks_like_status_enum(class_name: str, bases: str) -> bool:
    return bool(re.search(r"\bEnum\b", bases)) and bool(re.search(r"status|state", class_name, re.IGNORECASE))
