"""Suspicious artefact scoring — IOC, correlation, and heuristic scoring."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.parsers.utils import convert_timestamp
from dfat.forensic_engine.processing.ioc_detector import IOCMatch
from dfat.forensic_engine.processing.relationship_mapper import RelationshipMap

if TYPE_CHECKING:
    from dfat.ml.predictor import MLPredictor

logger = logging.getLogger(__name__)

_RULE_WEIGHT_DEFAULT = 0.6
_LLM_WEIGHT_DEFAULT = 0.4
_RULE_WEIGHT_ML = 0.5
_LLM_WEIGHT_ML = 0.3
_ML_WEIGHT = 0.2

_IOC_WEIGHTS: dict[str, float] = {
    "high": 0.3,
    "medium": 0.15,
    "low": 0.05,
}

_CATEGORY_BASE_SCORE: dict[ArtefactCategory, float] = {
    ArtefactCategory.INJECTED_CODE: 0.5,
    ArtefactCategory.NETWORK_CONNECTION: 0.2,
    ArtefactCategory.REGISTRY_KEY: 0.15,
    ArtefactCategory.EVENT_LOG: 0.1,
    ArtefactCategory.RUNNING_PROCESS: 0.1,
    ArtefactCategory.FILESYSTEM_METADATA: 0.05,
    ArtefactCategory.BROWSER_HISTORY: 0.05,
}

_CORRELATION_PER_LINK = 0.1
_CORRELATION_MAX = 0.3
_TEMPORAL_BONUS = 0.1
_TEMPORAL_WINDOW = timedelta(hours=1)

_TIMESTAMP_FIELDS: frozenset[str] = frozenset(
    {
        "timestamp",
        "create_time",
        "created_time",
        "exit_time",
        "modified_time",
        "accessed_time",
        "changed_time",
        "last_modified",
        "last_write_time",
        "last_visit_time",
    }
)


class ScoredArtefact(BaseModel):
    """Artefact enriched with a numerical suspicion score and factors.

    Attributes:
        artefact: Source artefact.
        score: Suspicion score in ``[0.0, 1.0]``.
        suspicion_level: Mapped ``SuspicionLevel``.
        scoring_factors: Human-readable contributors to the score.
        ioc_matches: Indicator strings matched for this artefact.
    """

    model_config = ConfigDict(frozen=False)

    artefact: Artefact
    score: float = Field(ge=0.0, le=1.0)
    suspicion_level: SuspicionLevel
    scoring_factors: list[str] = Field(default_factory=list)
    ioc_matches: list[str] = Field(default_factory=list)


class ScoringEngine:
    """Assign numerical suspicion scores from IOCs, correlations, and heuristics."""

    def __init__(self, ml_predictor: Optional[MLPredictor] = None) -> None:
        """Initialise the scoring engine.

        Args:
            ml_predictor: Optional ML inference service. When trained models exist,
                final scores merge rule, LLM, and ML components with dedicated weights.
        """
        self._ml_predictor = ml_predictor

    def ml_enabled(self) -> bool:
        """Return whether trained ML models are available for score augmentation."""
        if self._ml_predictor is None:
            return False
        return self._ml_predictor.has_trained_models()

    def combine_scores(
        self,
        rule_score: float,
        llm_score: Optional[float] = None,
        ml_score: Optional[float] = None,
    ) -> float:
        """Merge rule, LLM, and optional ML scores into a final value in ``[0, 1]``.

        When ML models are unavailable, uses ``0.6 * rule + 0.4 * llm`` when both
        components are present. When ML is available and ``ml_score`` is provided,
        uses ``0.5 * rule + 0.3 * llm + 0.2 * ml``.
        """
        rule = max(0.0, min(1.0, float(rule_score)))
        llm = None if llm_score is None else max(0.0, min(1.0, float(llm_score)))
        ml = None if ml_score is None else max(0.0, min(1.0, float(ml_score)))

        if self.ml_enabled() and ml is not None:
            if llm is not None:
                final = (_RULE_WEIGHT_ML * rule) + (_LLM_WEIGHT_ML * llm) + (_ML_WEIGHT * ml)
            else:
                final = (_RULE_WEIGHT_ML * rule) + (_ML_WEIGHT * ml)
            return max(0.0, min(1.0, final))

        if llm is not None:
            final = (_LLM_WEIGHT_DEFAULT * llm) + (_RULE_WEIGHT_DEFAULT * rule)
            return max(0.0, min(1.0, final))
        return rule

    async def ml_score_for(self, artefact: Artefact) -> Optional[float]:
        """Return an ML suspicion score for ``artefact`` when models are trained."""
        if not self.ml_enabled() or self._ml_predictor is None:
            return None
        return await self._ml_predictor.score_artefact(artefact)

    async def combine_with_ml(
        self,
        rule_score: float,
        artefact: Artefact,
        llm_score: Optional[float] = None,
    ) -> float:
        """Merge rule and LLM scores with an on-demand ML score for ``artefact``."""
        ml_score = await self.ml_score_for(artefact)
        return self.combine_scores(rule_score, llm_score=llm_score, ml_score=ml_score)

    def score(
        self,
        artefact_set: ArtefactSet,
        ioc_matches: list[IOCMatch],
        relationship_map: RelationshipMap,
    ) -> list[ScoredArtefact]:
        """Score every artefact in ``artefact_set``.

        Scoring components (clamped to ``[0.0, 1.0]``):
            1. IOC matches (+0.3 high / +0.15 medium / +0.05 low each)
            2. Correlations (+0.1 per linked artefact, max +0.3)
            3. Category base score
            4. Temporal proximity to other IOC-bearing artefacts (+0.1)

        Args:
            artefact_set: Artefacts to score.
            ioc_matches: IOC detector results.
            relationship_map: Correlation graph from ``RelationshipMapper``.

        Returns:
            One ``ScoredArtefact`` per input artefact.
        """
        iocs_by_id = self._index_iocs(ioc_matches)
        degree = self._correlation_degree(relationship_map)
        suspicious_times = self._suspicious_timestamps_by_id(
            artefact_set.artefacts,
            iocs_by_id,
        )

        scored: list[ScoredArtefact] = []
        for artefact in artefact_set.artefacts:
            scored.append(
                self._score_one(
                    artefact,
                    iocs_by_id.get(artefact.artefact_id, []),
                    degree.get(artefact.artefact_id, 0),
                    suspicious_times,
                )
            )

        logger.info(
            "Scored %d artefacts for evidence %s "
            "(critical=%d high=%d medium=%d low=%d informational=%d)",
            len(scored),
            artefact_set.evidence_id,
            sum(1 for item in scored if item.suspicion_level is SuspicionLevel.CRITICAL),
            sum(1 for item in scored if item.suspicion_level is SuspicionLevel.HIGH),
            sum(1 for item in scored if item.suspicion_level is SuspicionLevel.MEDIUM),
            sum(1 for item in scored if item.suspicion_level is SuspicionLevel.LOW),
            sum(
                1
                for item in scored
                if item.suspicion_level is SuspicionLevel.INFORMATIONAL
            ),
        )
        return scored

    def _score_one(
        self,
        artefact: Artefact,
        matches: list[IOCMatch],
        correlation_count: int,
        suspicious_times: dict[str, list[datetime]],
    ) -> ScoredArtefact:
        """Compute score, factors, and suspicion level for one artefact."""
        score = 0.0
        factors: list[str] = []
        ioc_indicators: list[str] = []

        # 1. IOC matches
        for match in matches:
            weight = _IOC_WEIGHTS.get(match.confidence, 0.0)
            score += weight
            ioc_indicators.append(match.indicator)
            factors.append(
                f"ioc:{match.matched_rule}:{match.confidence}(+{weight:.2f})"
            )

        # 2. Correlations
        if correlation_count > 0:
            corr_bonus = min(_CORRELATION_MAX, correlation_count * _CORRELATION_PER_LINK)
            score += corr_bonus
            factors.append(
                f"correlations:{correlation_count}(+{corr_bonus:.2f})"
            )

        # 3. Category base score
        base = _CATEGORY_BASE_SCORE.get(artefact.category, 0.0)
        if base > 0:
            score += base
            factors.append(f"category:{artefact.category.value}(+{base:.2f})")

        # 4. Temporal proximity to other suspicious artefacts
        if self._has_temporal_proximity(artefact, suspicious_times):
            score += _TEMPORAL_BONUS
            factors.append(f"temporal_proximity(+{_TEMPORAL_BONUS:.2f})")

        score = max(0.0, min(1.0, score))
        level = self._to_suspicion_level(score)
        return ScoredArtefact(
            artefact=artefact,
            score=round(score, 4),
            suspicion_level=level,
            scoring_factors=factors,
            ioc_matches=ioc_indicators,
        )

    @staticmethod
    def _to_suspicion_level(score: float) -> SuspicionLevel:
        """Map a numeric score to ``SuspicionLevel``."""
        if score >= 0.8:
            return SuspicionLevel.CRITICAL
        if score >= 0.6:
            return SuspicionLevel.HIGH
        if score >= 0.4:
            return SuspicionLevel.MEDIUM
        if score >= 0.2:
            return SuspicionLevel.LOW
        return SuspicionLevel.INFORMATIONAL

    @staticmethod
    def _index_iocs(ioc_matches: list[IOCMatch]) -> dict[str, list[IOCMatch]]:
        """Group IOC matches by artefact ID."""
        indexed: dict[str, list[IOCMatch]] = {}
        for match in ioc_matches:
            indexed.setdefault(match.artefact_id, []).append(match)
        return indexed

    @staticmethod
    def _correlation_degree(relationship_map: RelationshipMap) -> dict[str, int]:
        """Count unique neighbours per artefact from relationship edges."""
        degree: dict[str, set[str]] = {}
        for left, right, _rel in relationship_map.edges:
            degree.setdefault(left, set()).add(right)
            degree.setdefault(right, set()).add(left)
        return {
            artefact_id: len(neighbours)
            for artefact_id, neighbours in degree.items()
        }

    def _suspicious_timestamps_by_id(
        self,
        artefacts: list[Artefact],
        iocs_by_id: dict[str, list[IOCMatch]],
    ) -> dict[str, list[datetime]]:
        """Map IOC-bearing artefact IDs to their extracted timestamps."""
        result: dict[str, list[datetime]] = {}
        for artefact in artefacts:
            if artefact.artefact_id not in iocs_by_id:
                continue
            times = self._artefact_timestamps(artefact)
            if times:
                result[artefact.artefact_id] = times
        return result

    def _has_temporal_proximity(
        self,
        artefact: Artefact,
        suspicious_times: dict[str, list[datetime]],
    ) -> bool:
        """Return whether ``artefact`` is within one hour of another IOC artefact."""
        own_times = self._artefact_timestamps(artefact)
        if not own_times or not suspicious_times:
            return False
        window = _TEMPORAL_WINDOW.total_seconds()
        for other_id, other_times in suspicious_times.items():
            if other_id == artefact.artefact_id:
                continue
            for own in own_times:
                for other in other_times:
                    if abs((own - other).total_seconds()) <= window:
                        return True
        return False

    def _artefact_timestamps(self, artefact: Artefact) -> list[datetime]:
        """Extract UTC timestamps from ``raw_data`` fields."""
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        times: list[datetime] = []
        for key, value in raw.items():
            if not self._is_timestamp_field(key):
                continue
            parsed = convert_timestamp(value)
            if parsed is None:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            else:
                parsed = parsed.astimezone(UTC)
            times.append(parsed)
        return times

    @staticmethod
    def _is_timestamp_field(field: str) -> bool:
        """Return whether ``field`` is a timestamp source."""
        if field in _TIMESTAMP_FIELDS:
            return True
        return field.endswith("_time") or field.endswith("_timestamp")
