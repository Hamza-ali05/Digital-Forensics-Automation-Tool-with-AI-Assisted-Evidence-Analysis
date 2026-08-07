"""Rule-based triage engine — combine scoring engine output with triage rules."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from dfat.core.enums import SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.forensic_engine.processing.ioc_detector import IOCMatch
from dfat.forensic_engine.processing.relationship_mapper import RelationshipMap
from dfat.forensic_engine.triage.rules import DEFAULT_TRIAGE_RULES, TriageRule
from dfat.forensic_engine.triage.scoring import ScoringEngine

logger = logging.getLogger(__name__)

_SUSPICION_RANK: dict[SuspicionLevel, int] = {
    SuspicionLevel.CRITICAL: 0,
    SuspicionLevel.HIGH: 1,
    SuspicionLevel.MEDIUM: 2,
    SuspicionLevel.LOW: 3,
    SuspicionLevel.INFORMATIONAL: 4,
}


class RuleBasedTriageEngine:
    """Execute declarative triage rules and merge with ``ScoringEngine`` scores."""

    def __init__(
        self,
        scoring_engine: ScoringEngine,
        rules: list[TriageRule] | None = None,
    ) -> None:
        """Initialise the rule-based triage engine.

        Args:
            scoring_engine: Numerical suspicion scoring engine.
            rules: Triage rules to evaluate (defaults to ``DEFAULT_TRIAGE_RULES``).
        """
        self._scoring_engine = scoring_engine
        self._rules = list(rules) if rules is not None else list(DEFAULT_TRIAGE_RULES)

    def evaluate(
        self,
        artefact_set: ArtefactSet,
        ioc_matches: list[IOCMatch],
        relationship_map: RelationshipMap,
    ) -> list[RankedArtefact]:
        """Score artefacts, apply matching rules, and return ranked results.

        Steps:
            1. Score via ``scoring_engine``.
            2. Evaluate category-applicable triage rules.
            3. Apply each matching rule's ``suspicion_boost``.
            4. Convert to ``RankedArtefact`` with level + relevance score.
            5. Sort CRITICAL first, then score descending.
            6. Attach ``classification_reasoning`` from rules and IOCs.

        Args:
            artefact_set: Artefacts to triage.
            ioc_matches: IOC detector matches.
            relationship_map: Correlation graph.

        Returns:
            Sorted list of ``RankedArtefact``.
        """
        scored = self._scoring_engine.score(
            artefact_set,
            ioc_matches,
            relationship_map,
        )
        iocs_by_id = self._index_iocs(ioc_matches)
        ranked: list[RankedArtefact] = []

        for item in scored:
            artefact = item.artefact
            final_score = float(item.score)
            matched_rules: list[TriageRule] = []

            for rule in self._rules_for_category(artefact):
                if self._rule_matches(rule, artefact):
                    final_score += float(rule.suspicion_boost)
                    matched_rules.append(rule)

            final_score = max(0.0, min(1.0, final_score))
            level = ScoringEngine._to_suspicion_level(final_score)
            reasoning = self._build_reasoning(
                item.scoring_factors,
                matched_rules,
                iocs_by_id.get(artefact.artefact_id, []),
            )
            ranked.append(
                RankedArtefact(
                    **artefact.model_dump(),
                    suspicion_level=level,
                    relevance_score=round(final_score, 4),
                    classification_reasoning=reasoning,
                )
            )

        ranked.sort(
            key=lambda entry: (
                _SUSPICION_RANK.get(entry.suspicion_level, 99),
                -entry.relevance_score,
            )
        )
        logger.info(
            "Rule-based triage for evidence %s: %d ranked artefacts "
            "(rules=%d, iocs=%d)",
            artefact_set.evidence_id,
            len(ranked),
            len(self._rules),
            len(ioc_matches),
        )
        return ranked

    def _rules_for_category(self, artefact: Artefact) -> list[TriageRule]:
        """Return configured rules that apply to ``artefact.category``."""
        return [rule for rule in self._rules if rule.category is artefact.category]

    def _rule_matches(self, rule: TriageRule, artefact: Artefact) -> bool:
        """Evaluate whether ``rule`` matches ``artefact.raw_data``."""
        field_value = self._resolve_field(artefact.raw_data, rule.condition_field)
        if field_value is None and rule.condition_operator != "equals":
            # Missing field cannot satisfy most operators; equals may match None.
            if rule.condition_value is not None:
                return False
        return self._apply_operator(
            rule.condition_operator,
            field_value,
            rule.condition_value,
        )

    def _apply_operator(
        self,
        operator: str,
        field_value: Any,
        expected: Any,
    ) -> bool:
        """Apply a triage condition operator."""
        if operator == "equals":
            return self._coerce_comparable(field_value) == self._coerce_comparable(expected)

        if operator == "contains":
            if field_value is None:
                return False
            needle = str(expected)
            if isinstance(field_value, (list, tuple, set)):
                return any(needle.lower() in str(item).lower() for item in field_value)
            return needle.lower() in str(field_value).lower()

        if operator == "regex":
            if field_value is None:
                return False
            pattern = str(expected)
            try:
                compiled = re.compile(pattern)
            except re.error:
                logger.warning("Invalid triage regex ignored: %s", pattern)
                return False
            if isinstance(field_value, (list, tuple, set)):
                return any(compiled.search(str(item)) is not None for item in field_value)
            return compiled.search(str(field_value)) is not None

        if operator == "greater_than":
            left = self._as_float(field_value)
            right = self._as_float(expected)
            if left is None or right is None:
                return False
            return left > right

        if operator == "in_list":
            if not isinstance(expected, (list, tuple, set)):
                return False
            candidates = [self._coerce_comparable(item) for item in expected]
            actual = self._coerce_comparable(field_value)
            if actual in candidates:
                return True
            # Substring fallback for process-style names vs short indicators.
            if isinstance(field_value, str):
                lowered = field_value.lower()
                return any(
                    isinstance(item, str) and item.lower() in lowered
                    for item in expected
                )
            return False

        logger.warning("Unknown triage operator ignored: %s", operator)
        return False

    @staticmethod
    def _resolve_field(raw_data: dict[str, Any], field_path: str) -> Any:
        """Resolve a possibly dotted field path against ``raw_data``."""
        if not isinstance(raw_data, dict):
            return None
        current: Any = raw_data
        for part in field_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    @staticmethod
    def _build_reasoning(
        scoring_factors: list[str],
        matched_rules: list[TriageRule],
        ioc_matches: list[IOCMatch],
    ) -> str:
        """Compose classification reasoning from scores, rules, and IOCs."""
        parts: list[str] = []
        if scoring_factors:
            parts.append("Scoring: " + "; ".join(scoring_factors))
        if matched_rules:
            rule_bits = [
                f"{rule.rule_id} {rule.name} (+{rule.suspicion_boost:.2f}): "
                f"{rule.description}"
                for rule in matched_rules
            ]
            parts.append("Rules: " + " | ".join(rule_bits))
        if ioc_matches:
            ioc_bits = [
                f"{match.indicator} [{match.confidence}] — {match.description}"
                for match in ioc_matches
            ]
            parts.append("IOCs: " + " | ".join(ioc_bits))
        return " || ".join(parts) if parts else "No elevated triage signals."

    @staticmethod
    def _index_iocs(ioc_matches: list[IOCMatch]) -> dict[str, list[IOCMatch]]:
        """Group IOC matches by artefact ID."""
        indexed: dict[str, list[IOCMatch]] = {}
        for match in ioc_matches:
            indexed.setdefault(match.artefact_id, []).append(match)
        return indexed

    @staticmethod
    def _as_float(value: Any) -> Optional[float]:
        """Best-effort float coercion."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_comparable(value: Any) -> Any:
        """Normalise scalars for equality / list membership checks."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip()
            lowered = text.lower()
            if lowered in {"true", "false"}:
                return lowered == "true"
            try:
                if text.isdigit() or (
                    text.startswith("-") and text[1:].isdigit()
                ):
                    return int(text)
            except ValueError:
                pass
            return text
        return value
