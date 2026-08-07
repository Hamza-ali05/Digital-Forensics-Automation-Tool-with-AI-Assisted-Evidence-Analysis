"""Stage 3 — AI / rule-based artefact triage and summary generation."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from dfat.core.enums import PipelineStage
from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.pipeline import StageResult
from dfat.forensic_engine.processing.categoriser import ArtefactCategoriser
from dfat.forensic_engine.processing.correlator import ArtefactCorrelator
from dfat.forensic_engine.processing.deduplicator import ArtefactDeduplicator
from dfat.forensic_engine.processing.ioc_detector import IOCDetector, IOCMatch
from dfat.forensic_engine.processing.relationship_mapper import (
    RelationshipMap,
    RelationshipMapper,
)
from dfat.forensic_engine.processing.standardiser import ArtefactStandardiser
from dfat.forensic_engine.processing.timeline import Timeline, TimelineGenerator
from dfat.forensic_engine.triage.aggregator import TriageAggregator
from dfat.forensic_engine.triage.rule_engine import RuleBasedTriageEngine
from dfat.forensic_engine.triage.scoring import ScoringEngine
from dfat.pipeline.progress_tracker import ProgressNotFoundError, ProgressTracker
from dfat.pipeline.stage_interface import IPipelineStage, PipelineContext
from dfat.services.audit_service import AuditService
from dfat.settings import DFATSettings, PipelineSettings

logger = logging.getLogger(__name__)


class TriageStage(IPipelineStage):
    """Coordinate processing, IOC detection, rule triage, and LLM triage."""

    def __init__(
        self,
        ioc_detector: IOCDetector,
        scoring_engine: ScoringEngine,
        rule_engine: RuleBasedTriageEngine,
        triage_aggregator: TriageAggregator,
        llm_analyzer: IArtefactAnalyzer,
        fallback_analyzer: IArtefactAnalyzer,
        progress_tracker: ProgressTracker,
        audit_service: AuditService,
        settings: DFATSettings,
        *,
        categoriser: Optional[ArtefactCategoriser] = None,
        standardiser: Optional[ArtefactStandardiser] = None,
        deduplicator: Optional[ArtefactDeduplicator] = None,
        correlator: Optional[ArtefactCorrelator] = None,
        relationship_mapper: Optional[RelationshipMapper] = None,
        timeline_generator: Optional[TimelineGenerator] = None,
    ) -> None:
        """Initialise the triage stage.

        Args:
            ioc_detector: IOC pattern scanner.
            scoring_engine: Numerical suspicion scoring engine.
            rule_engine: Declarative rule-based triage engine.
            triage_aggregator: Summary aggregator for reporting.
            llm_analyzer: Primary local LLM analyser.
            fallback_analyzer: Rule-based AI fallback analyser.
            progress_tracker: Job/stage progress tracker.
            audit_service: Dual-write audit trail service.
            settings: Application settings (pipeline + AI flags).
            categoriser: Optional categoriser override.
            standardiser: Optional standardiser override.
            deduplicator: Optional deduplicator override.
            correlator: Optional correlator override.
            relationship_mapper: Optional relationship mapper override.
            timeline_generator: Optional timeline generator override.
        """
        self._ioc_detector = ioc_detector
        self._scoring_engine = scoring_engine
        self._rule_engine = rule_engine
        self._aggregator = triage_aggregator
        self._llm = llm_analyzer
        self._fallback = fallback_analyzer
        self._progress = progress_tracker
        self._audit = audit_service
        self._settings = settings
        self._categoriser = categoriser or ArtefactCategoriser()
        self._standardiser = standardiser or ArtefactStandardiser()
        self._deduplicator = deduplicator or ArtefactDeduplicator()
        self._correlator = correlator or ArtefactCorrelator()
        self._relationship_mapper = relationship_mapper or RelationshipMapper()
        self._timeline_generator = timeline_generator or TimelineGenerator()

    @property
    def stage_name(self) -> PipelineStage:
        """Return ``PipelineStage.AI_TRIAGE``."""
        return PipelineStage.AI_TRIAGE

    @property
    def description(self) -> str:
        """Return a human-readable description of this stage."""
        return "Triage artefacts with IOC detection, rules, and LLM/fallback analysis"

    async def validate_preconditions(self, context: PipelineContext) -> bool:
        """Require a non-empty parsed artefact set."""
        if context.artefact_set is None:
            return False
        return context.artefact_set.total_count >= 0

    async def execute(self, context: PipelineContext) -> StageResult:
        """Run processing, triage, aggregation, and update ``context``.

        Args:
            context: Shared pipeline context (must include ``artefact_set``).

        Returns:
            ``StageResult`` for the AI triage stage.
        """
        started = time.perf_counter()
        errors: list[str] = []

        if context.artefact_set is None:
            return StageResult(
                stage=self.stage_name,
                success=False,
                duration_seconds=time.perf_counter() - started,
                errors=["No artefact_set available for triage"],
            )

        job_id = context.job.job_id
        evidence_id = (
            context.evidence.evidence_id
            if context.evidence is not None
            else context.artefact_set.evidence_id
        )
        self._ensure_progress_job(job_id)
        self._progress.start_stage(job_id, self.stage_name, parser_count=0)

        await self._audit.log_action(
            stage=self.stage_name,
            action="TRIAGE_STAGE_STARTED",
            evidence_id=evidence_id,
            user_id=context.job.user_id,
            details={
                "job_id": job_id,
                "artefact_count": context.artefact_set.total_count,
                "use_fallback_analyzer": context.job.use_fallback_analyzer,
            },
        )

        try:
            processed, relationship_map, timeline, ioc_matches = await asyncio.to_thread(
                self._run_processing_pipeline,
                context.artefact_set,
            )
            context.artefact_set = processed

            rule_ranked = await asyncio.to_thread(
                self._rule_engine.evaluate,
                processed,
                ioc_matches,
                relationship_map,
            )

            ranked, summary_text, triage_source = await asyncio.to_thread(
                self._run_ai_triage,
                processed,
                rule_ranked,
                use_fallback=bool(context.job.use_fallback_analyzer),
            )

            summary = await asyncio.to_thread(
                self._aggregator.aggregate,
                ranked,
                timeline,
                ioc_matches,
            )

            context.ranked_artefacts = ranked
            context.summary_text = summary_text
            context.metadata["triage_summary"] = summary.model_dump(mode="json")
            context.metadata["triage_source"] = triage_source
            context.metadata["ioc_count"] = len(ioc_matches)
            context.metadata["relationship_count"] = relationship_map.total_relationships
            context.job.artefact_count = max(context.job.artefact_count, len(ranked))

            duration = time.perf_counter() - started
            context.stage_timings[self.stage_name.value] = duration
            self._progress.complete_stage(
                job_id,
                self.stage_name,
                artefacts_found=len(ranked),
            )

            await self._audit.log_action(
                stage=self.stage_name,
                action="TRIAGE_STAGE_COMPLETED",
                evidence_id=evidence_id,
                user_id=context.job.user_id,
                details={
                    "job_id": job_id,
                    "ranked_count": len(ranked),
                    "ioc_count": len(ioc_matches),
                    "triage_source": triage_source,
                    "summary_chars": len(summary_text or ""),
                },
            )

            return StageResult(
                stage=self.stage_name,
                success=True,
                duration_seconds=duration,
                output_data={
                    "ranked_count": len(ranked),
                    "ioc_count": len(ioc_matches),
                    "triage_source": triage_source,
                    "triage_summary": summary.model_dump(mode="json"),
                    "summary_preview": (summary_text or "")[:500],
                },
                errors=errors,
            )
        except Exception as exc:  # noqa: BLE001 — stage-level failure
            duration = time.perf_counter() - started
            errors.append(str(exc))
            logger.exception("Triage stage failed for job %s", job_id)
            await self._audit.log_action(
                stage=self.stage_name,
                action="TRIAGE_STAGE_FAILED",
                evidence_id=evidence_id,
                user_id=context.job.user_id,
                details={"job_id": job_id, "error": str(exc)},
            )
            return StageResult(
                stage=self.stage_name,
                success=False,
                duration_seconds=duration,
                output_data=None,
                errors=errors,
            )

    def _run_processing_pipeline(
        self,
        artefact_set: ArtefactSet,
    ) -> tuple[ArtefactSet, RelationshipMap, Timeline, list[IOCMatch]]:
        """Run categorise → standardise → dedupe → correlate → map → timeline → IOC."""
        pipeline: PipelineSettings = self._settings.pipeline

        current = self._categoriser.categorise(artefact_set)
        current = self._standardiser.standardise(current)
        current = self._deduplicator.deduplicate(current)

        if pipeline.enable_artefact_correlation:
            current = self._correlator.correlate(current)
            relationship_map = self._relationship_mapper.build_map(current)
        else:
            relationship_map = RelationshipMap(edges=[], clusters=[])

        if pipeline.enable_timeline_generation:
            timeline = self._timeline_generator.generate(current)
        else:
            timeline = Timeline(entries=[], windows=[], earliest=None, latest=None)

        if pipeline.enable_ioc_detection:
            ioc_matches = self._ioc_detector.detect(current)
        else:
            ioc_matches = []

        return current, relationship_map, timeline, ioc_matches

    def _run_ai_triage(
        self,
        artefact_set: ArtefactSet,
        rule_ranked: list[RankedArtefact],
        *,
        use_fallback: bool,
    ) -> tuple[list[RankedArtefact], str, str]:
        """Select LLM or fallback triage and produce ranked artefacts + summary.

        Returns:
            ``(ranked, summary_text, triage_source)``.
        """
        force_fallback = use_fallback or not self._llm.is_available()

        if not force_fallback:
            try:
                ranked = self._llm.analyze(artefact_set)
                if not ranked:
                    ranked = rule_ranked
                summary = self._llm.summarize(ranked)
                return ranked, summary, "llm"
            except Exception as exc:  # noqa: BLE001 — fall back to rules
                logger.warning(
                    "LLM triage failed (%s); falling back to rule-based results",
                    exc,
                )

        # Forced fallback or LLM failure: prefer forensic rule-engine ranking,
        # summarise with the AI fallback analyser.
        ranked = rule_ranked
        source = "rule_engine+fallback_summary"
        if use_fallback or not ranked:
            try:
                fallback_ranked = self._fallback.analyze(artefact_set)
                if fallback_ranked:
                    ranked = fallback_ranked
                    source = "fallback_analyzer"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fallback analyzer failed: %s", exc)
                ranked = rule_ranked
                source = "rule_engine"

        try:
            summary = self._fallback.summarize(ranked)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fallback summarize failed: %s", exc)
            summary = self._default_summary(ranked)

        return ranked, summary, source

    @staticmethod
    def _default_summary(ranked: list[RankedArtefact]) -> str:
        """Build a minimal summary when analysers cannot summarise."""
        if not ranked:
            return "No artefacts were available for triage."
        critical = sum(
            1 for item in ranked if item.suspicion_level.value == "critical"
        )
        high = sum(1 for item in ranked if item.suspicion_level.value == "high")
        return (
            f"Triage complete for {len(ranked)} artefacts "
            f"({critical} critical, {high} high)."
        )

    def _ensure_progress_job(self, job_id: str) -> None:
        """Ensure progress tracking has been initialised for ``job_id``."""
        try:
            self._progress.get_progress(job_id)
        except ProgressNotFoundError:
            self._progress.start_job(job_id, total_stages=5)
