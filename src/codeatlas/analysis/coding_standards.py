"""Coding standards analyzer — static observation of naming conventions,
dependency-injection/repository-pattern usage, and test-file naming
(ARCHITECTURE.md §14; product spec §14 "Coding Standards Analysis").

V1 scope, honestly stated:

- **Python only in this pass** — an explicit, tracked gap, consistent with
  ``codeatlas.analysis.business_rules``'s scoping. Node/TS naming and
  pattern conventions are follow-up work, not folded into this slice.
- **This is observation, never judgment.** Per the spec's explicit
  instruction ("do NOT automatically call something a violation simply
  because it differs from your preferred coding style"),
  ``recommended_improvements`` is always empty here: without a project-
  specific style guide or a human-confirmed baseline to compare against,
  there is no static, non-opinionated basis for a recommendation in V1
  — that would require either an LLM judgment call (no ``ModelProvider``
  is wired for this analyzer in this pass) or a configured baseline
  (not implemented). Leaving it empty is the honest choice.
- **Naming conventions** are measured, not asserted from a handful of
  examples: function and class names are parsed with Python's ``ast``
  module (the Python-specific deep-parsing tool per ARCHITECTURE.md §2)
  across every readable ``.py`` file, dunder methods excluded (Python
  forces those names, so they carry no information about project
  convention). A convention is only reported once a minimum sample size
  is met, and only when one style has a clear majority (> 50%) — the
  dominant style's share of the sample becomes the confidence, and
  ``CONFIRMED`` requires a >= 90% majority; anything less is ``INFERRED``.
  A sample with no majority style at all, or whose majority is "other"
  (neither snake_case, PascalCase, nor camelCase), produces no claim.
- **Dependency injection** usage is detected from literal ``Depends(``
  call sites (FastAPI's DI mechanism) — directly observed, ``CONFIRMED``.
- **Repository pattern** usage is detected from classes whose name ends
  in "Repository" — a naming convention, not a structural guarantee that
  the class actually implements the pattern, so this is reported at
  ``INFERRED`` with lower confidence than the DI signal.
- **Test file naming** convention (``test_*.py`` vs ``*_test.py``) reuses
  the test file list ``codeatlas.discovery.priority`` already built — no
  extra file reads needed for this one.

Nothing here calls an LLM. No matching pattern or insufficient sample
size → no observation, never a guess.

Note on traceability: like ``codeatlas.knowledge.schema.TestInventory``,
``CodingStandards`` carries no per-field ``EvidenceRef`` list of its own
— every ``Evidence`` record this analyzer produces is still added to the
pipeline's overall evidence list and indexed in
``ProjectKnowledge.evidence_index``, so nothing here is untraceable; it
just isn't double-linked onto this particular submodel, matching the
precedent already set by ``TestInventory``.
"""

from __future__ import annotations

import ast
import itertools
import re

from codeatlas.discovery.engine import DiscoveryContext
from codeatlas.evidence.schema import Evidence, SourceLocation, VerificationStatus
from codeatlas.knowledge.schema import CodingStandards

_MAX_FILES_SCANNED = 200
_MIN_SAMPLE_SIZE = 5
_CONFIRMED_RATIO = 0.9

_DUNDER = re.compile(r"^__[a-z0-9_]+__$")
_DEPENDS_PATTERN = re.compile(r"\bDepends\(")

NameSample = tuple[str, str, int]  # (name, relative_path, lineno)


def analyze_coding_standards(ctx: DiscoveryContext, walker) -> tuple[CodingStandards, list[Evidence]]:
    observed: list[str] = []
    design_patterns: list[str] = []
    evidence: list[Evidence] = []

    functions, classes = _collect_names(ctx, walker)

    text, ev = _naming_rule(functions, "Python function names", "function")
    if text:
        observed.append(text)
        evidence.append(ev)

    text, ev = _naming_rule(classes, "Python class names", "class")
    if text:
        observed.append(text)
        evidence.append(ev)

    text, ev = _test_file_naming_rule(ctx)
    if text:
        observed.append(text)
        evidence.append(ev)

    text, ev = _detect_dependency_injection(ctx, walker)
    if text:
        design_patterns.append(text)
        evidence.append(ev)

    text, ev = _detect_repository_pattern(classes)
    if text:
        design_patterns.append(text)
        evidence.append(ev)

    return (
        CodingStandards(observed=observed, recommended_improvements=[], design_patterns_observed=design_patterns),
        evidence,
    )


def _py_files(ctx: DiscoveryContext):
    return itertools.islice(
        (f for f in ctx.tree.readable_files if f.relative_path.endswith(".py")), _MAX_FILES_SCANNED
    )


def _collect_names(ctx: DiscoveryContext, walker) -> tuple[list[NameSample], list[NameSample]]:
    functions: list[NameSample] = []
    classes: list[NameSample] = []

    for f in _py_files(ctx):
        try:
            text = walker.read_text(f)
            tree = ast.parse(text, filename=f.relative_path)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not _DUNDER.match(node.name):
                    functions.append((node.name, f.relative_path, node.lineno))
            elif isinstance(node, ast.ClassDef):
                classes.append((node.name, f.relative_path, node.lineno))

    return functions, classes


def _classify_name(name: str) -> str:
    if re.match(r"^[a-z][a-z0-9_]*$", name):
        return "snake_case"
    if re.match(r"^[A-Z][A-Za-z0-9]*$", name):
        return "PascalCase"
    if re.match(r"^[a-z][a-zA-Z0-9]*$", name) and any(c.isupper() for c in name):
        return "camelCase"
    return "other"


def _naming_rule(samples: list[NameSample], label: str, finding_suffix: str) -> tuple[str | None, Evidence | None]:
    if len(samples) < _MIN_SAMPLE_SIZE:
        return None, None

    counts: dict[str, int] = {}
    examples: dict[str, NameSample] = {}
    for name, file, lineno in samples:
        style = _classify_name(name)
        counts[style] = counts.get(style, 0) + 1
        examples.setdefault(style, (name, file, lineno))

    total = len(samples)
    dominant_style, dominant_count = max(counts.items(), key=lambda kv: kv[1])
    ratio = dominant_count / total

    if dominant_style == "other" or ratio <= 0.5:
        return None, None  # no clear majority convention -- nothing honest to report

    status = VerificationStatus.CONFIRMED if ratio >= _CONFIRMED_RATIO else VerificationStatus.INFERRED
    confidence = round(min(0.5 + ratio * 0.4, 0.9), 2)
    example_name, example_file, example_lineno = examples[dominant_style]

    observed_text = (
        f"{label} predominantly use {dominant_style} naming "
        f"({dominant_count}/{total}, {ratio:.0%}); example: '{example_name}' in {example_file}."
    )
    ev = Evidence(
        finding_id=f"coding_standards:naming:{finding_suffix}",
        source_file=example_file,
        location=SourceLocation(file=example_file, line_start=example_lineno, symbol=example_name),
        excerpt=example_name,
        reasoning=(
            f"Parsed {total} {label.lower()} across the scanned Python files: "
            + ", ".join(f"{style}={count}" for style, count in sorted(counts.items(), key=lambda kv: -kv[1]))
            + f". {dominant_style} accounts for {ratio:.0%} of the sample."
        ),
        confidence=confidence,
        verification_status=status,
        discovered_by="static",
    )
    return observed_text, ev


def _test_file_naming_rule(ctx: DiscoveryContext) -> tuple[str | None, Evidence | None]:
    test_paths = [p for p in ctx.priority_plan.tests if p.endswith(".py")]
    total = len(test_paths)
    if total < _MIN_SAMPLE_SIZE:
        return None, None

    prefix_count = sum(1 for p in test_paths if p.rsplit("/", 1)[-1].startswith("test_"))
    suffix_count = sum(1 for p in test_paths if p.rsplit("/", 1)[-1].endswith("_test.py"))

    if prefix_count >= suffix_count:
        dominant_label, dominant_count = "test_*.py (prefix)", prefix_count
    else:
        dominant_label, dominant_count = "*_test.py (suffix)", suffix_count

    ratio = dominant_count / total
    if ratio <= 0.5:
        return None, None

    status = VerificationStatus.CONFIRMED if ratio >= _CONFIRMED_RATIO else VerificationStatus.INFERRED
    confidence = round(min(0.5 + ratio * 0.4, 0.9), 2)
    example = test_paths[0]

    observed_text = (
        f"Test files predominantly follow the {dominant_label} naming convention "
        f"({dominant_count}/{total}, {ratio:.0%})."
    )
    ev = Evidence(
        finding_id="coding_standards:naming:test_file",
        source_file=example,
        excerpt=example,
        reasoning=f"{dominant_count} of {total} discovered test files follow the {dominant_label} convention.",
        confidence=confidence,
        verification_status=status,
        discovered_by="static",
    )
    return observed_text, ev


def _detect_dependency_injection(ctx: DiscoveryContext, walker) -> tuple[str | None, Evidence | None]:
    occurrences: list[tuple[str, int, str]] = []
    for f in _py_files(ctx):
        try:
            text = walker.read_text(f)
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _DEPENDS_PATTERN.search(line):
                occurrences.append((f.relative_path, lineno, line.strip()))

    if not occurrences:
        return None, None

    file, lineno, excerpt = occurrences[0]
    files_count = len({o[0] for o in occurrences})
    observed_text = (
        f"FastAPI's Depends(...) dependency-injection pattern is used "
        f"({len(occurrences)} occurrence(s) across {files_count} file(s))."
    )
    ev = Evidence(
        finding_id="coding_standards:pattern:dependency_injection",
        source_file=file,
        location=SourceLocation(file=file, line_start=lineno, line_end=lineno),
        excerpt=excerpt[:160],
        reasoning=(
            f"Found {len(occurrences)} Depends(...) call site(s) across {files_count} file(s); "
            f"first at {file}:{lineno}."
        ),
        confidence=0.85,
        verification_status=VerificationStatus.CONFIRMED,
        discovered_by="static",
    )
    return observed_text, ev


def _detect_repository_pattern(classes: list[NameSample]) -> tuple[str | None, Evidence | None]:
    repo_classes = [c for c in classes if c[0].endswith("Repository")]
    if not repo_classes:
        return None, None

    name, file, lineno = repo_classes[0]
    observed_text = (
        f"Repository-pattern naming is used for data-access classes "
        f"({len(repo_classes)} class(es) ending in 'Repository')."
    )
    ev = Evidence(
        finding_id="coding_standards:pattern:repository",
        source_file=file,
        location=SourceLocation(file=file, line_start=lineno, symbol=name),
        excerpt=f"class {name}(...)",
        reasoning=(
            f"Found {len(repo_classes)} class(es) named with a 'Repository' suffix, e.g. '{name}' in {file}. "
            "Naming alone is observed; this does not confirm the class actually implements the Repository "
            "pattern's behavior, which would require deeper structural analysis this pass does not do."
        ),
        confidence=0.6,
        verification_status=VerificationStatus.INFERRED,
        discovered_by="static",
    )
    return observed_text, ev
