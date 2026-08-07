"""Rule-based AI triage fallback (no LLM dependency).

Uses the Prompt 4 ``RuleBasedTriageEngine`` for deterministic ranking when
the local LLM is unavailable.
"""

from __future__ import annotations

import logging
from typing import Optional

from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.forensic_engine.processing.ioc_detector import IOCMatch
from dfat.forensic_engine.processing.relationship_mapper import RelationshipMap
from dfat.forensic_engine.processing.timeline import Timeline
from dfat.forensic_engine.triage.aggregator import TriageAggregator
from dfat.forensic_engine.triage.rule_engine import RuleBasedTriageEngine
from dfat.forensic_engine.triage.scoring import ScoringEngine
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)


class RuleBasedAnalyzer(IArtefactAnalyzer):
    """Deterministic fallback analyzer. No LLM dependency.

    Uses the rule-based triage engine from Prompt 4.
    """

    def __init__(
        self,
        rule_engine: Optional[RuleBasedTriageEngine] = None,
        triage_aggregator: Optional[TriageAggregator] = None,
        audit_logger: Optional[ForensicAuditLogger] = None,
    ) -> None:
        """Initialise the rule-based fallback analyser.

        Args:
            rule_engine: Prompt 4 triage engine (default constructed if omitted).
            triage_aggregator: Aggregator for template summaries.
            audit_logger: Optional forensic audit logger.
        """
        self._rule_engine = rule_engine or RuleBasedTriageEngine(ScoringEngine())
        self._aggregator = triage_aggregator or TriageAggregator()
        self._audit_logger = audit_logger

    @property
    def analyzer_name(self) -> str:
        """Return the stable analyser identifier."""
        return "RuleBasedFallback"

    def is_available(self) -> bool:
        """Return True — rule-based analysis is always available."""
        return True

    def analyze(self, artefact_set: ArtefactSet) -> list[RankedArtefact]:
        """Rank artefacts via ``RuleBasedTriageEngine.evaluate``.

        Uses empty IOC matches and an empty relationship map when artefact
        processing has not populated them yet.
        """
        ioc_matches: list[IOCMatch] = []
        relationship_map = RelationshipMap()
        ranked = self._rule_engine.evaluate(
            artefact_set,
            ioc_matches,
            relationship_map,
        )
        return ranked

    def summarize(self, ranked_artefacts: list[RankedArtefact]) -> str:
        """Generate a deterministic template summary from triage aggregation."""
        summary = self._aggregator.aggregate(
            ranked_artefacts,
            Timeline(),
            [],
        )
        findings = "\n".join(f"- {item}" for item in summary.key_findings) or (
            "- No key findings"
        )
        by_level = ", ".join(
            f"{level}={count}" for level, count in sorted(summary.by_suspicion.items())
        )
        return (
            f"Rule-based triage summary ({self.analyzer_name})\n"
            f"Total artefacts: {summary.total_artefacts}\n"
            f"Suspicion distribution: {by_level}\n"
            f"IOC matches considered: {summary.ioc_count}\n"
            f"Timeline range: {summary.timeline_range or 'n/a'}\n"
            f"Key findings:\n{findings}\n"
            "This summary was produced by the rule-based fallback analyser "
            "(no LLM). Structured JSON remains the authoritative record."
        )
