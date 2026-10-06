"""Discovery result container — see ARCHITECTURE.md §5.

Discovery is pure static fact-gathering: zero LLM calls. Every
``Evidence`` produced here has ``discovered_by == "static"``, which is
exactly what lets downstream findings be ``CONFIRMED`` (see
``codeatlas.evidence.schema.assert_status_supported``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codeatlas.evidence.schema import Evidence
from codeatlas.knowledge.schema import ConfigurationItem, Dependency, TechnologyItem


@dataclass
class DiscoveryResult:
    technology_items: list[TechnologyItem] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    configuration_items: list[ConfigurationItem] = field(default_factory=list)
    test_frameworks: list[str] = field(default_factory=list)
    infra_signals: dict[str, bool] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # e.g. "shallow detector: no dependency parsing"

    def merge(self, other: "DiscoveryResult") -> None:
        self.technology_items.extend(other.technology_items)
        self.dependencies.extend(other.dependencies)
        self.configuration_items.extend(other.configuration_items)
        for fw in other.test_frameworks:
            if fw not in self.test_frameworks:
                self.test_frameworks.append(fw)
        self.infra_signals.update(other.infra_signals)
        self.evidence.extend(other.evidence)
        self.notes.extend(other.notes)
