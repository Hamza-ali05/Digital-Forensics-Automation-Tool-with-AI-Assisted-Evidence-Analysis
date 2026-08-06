"""Top-level five-stage pipeline orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.core.enums import PipelineStage, SuspicionLevel
from dfat.core.exceptions import DFATError, EvidenceNotFoundError
from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evaluation import BenchmarkResult
from dfat.core.models.evidence import CaseMetadata, EvidenceImage
from dfat.core.models.pipeline import PipelineState, StageResult
from dfat.core.models.report import ForensicReport
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.forensic_engine.orchestrator import ForensicOrchestrator
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.infrastructure.repositories.evidence_repo import FileSystemEvidenceRepository
from dfat.infrastructure.repositories.report_repo import FileSystemReportRepository
from dfat.reporting.report_builder import DualOutputReportBuilder
from dfat.shared.timing import PerformanceTimer


class PipelineOrchestrator:
    """Coordinate Acquisition → Parsing → AI Triage → Reporting end-to-end."""

    def __init__(
        self,
        forensic_orchestrator: ForensicOrchestrator,
        analyzer: IArtefactAnalyzer,
        fallback_analyzer: RuleBasedAnalyzer,
        report_builder: DualOutputReportBuilder,
        evidence_repo: FileSystemEvidenceRepository,
        report_repo: FileSystemReportRepository,
        ground_truth_loader: GroundTruthLoader,
        benchmark_comparator: BenchmarkComparator,
        audit_logger: ForensicAuditLogger,
    ) -> None:
        """Initialise the top-level pipeline orchestrator.

        Args:
            forensic_orchestrator: Stage 1–2 forensic orchestrator.
            analyzer: Primary AI analyser (local LLM or selected).
            fallback_analyzer: Rule-based fallback analyser.
            report_builder: Dual-output report builder.
            evidence_repo: Evidence metadata repository.
            report_repo: Report repository.
            ground_truth_loader: Ground-truth loader.
            benchmark_comparator: Benchmark comparator.
            audit_logger: Forensic audit logger.
        """
        self._forensic = forensic_orchestrator
        self._analyzer = analyzer
        self._fallback = fallback_analyzer
        self._report_builder = report_builder
        self._evidence_repo = evidence_repo
        self._report_repo = report_repo
        self._ground_truth_loader = ground_truth_loader
        self._benchmark_comparator = benchmark_comparator
        self._audit_logger = audit_logger
        self._pipeline_states: dict[str, PipelineState] = {}
        self._pipeline_reports: dict[str, str] = {}
        self._benchmark_results: list[BenchmarkResult] = []
        self._artefact_cache: dict[str, ArtefactSet] = {}

    def run_full_pipeline(
        self,
        evidence_path: Path,
        case: CaseMetadata,
        *,
        use_fallback: bool = False,
    ) -> ForensicReport:
        """Run the full five-stage pipeline and return a forensic report.

        Args:
            evidence_path: Path to evidence image/dump.
            case: Case metadata.
            use_fallback: Force rule-based triage even if LLM is available.

        Returns:
            Persisted ``ForensicReport``.
        """
        state = PipelineState(
            case=case,
            current_stage=PipelineStage.ACQUISITION,
        )
        self._pipeline_states[state.pipeline_id] = state
        stage_timings: dict[str, float] = {}
        errors: list[str] = []
        pipeline_start = datetime.now(UTC)

        self._audit_logger.log_action(
            stage=PipelineStage.ACQUISITION,
            action="PIPELINE_START",
            evidence_id="pending",
            details={"pipeline_id": state.pipeline_id, "path": str(evidence_path)},
        )

        # Stages 1–2: acquisition + parsing via forensic orchestrator.
        with PerformanceTimer() as parse_timer:
            try:
                evidence, artefact_set = self._forensic.process_evidence(
                    evidence_path,
                    case,
                )
                self._evidence_repo.save(evidence)
                self._artefact_cache[evidence.evidence_id] = artefact_set
                self._record_stage(
                    state,
                    PipelineStage.ACQUISITION,
                    True,
                    parse_timer.elapsed_seconds / 2.0,
                    {"evidence_id": evidence.evidence_id},
                )
                self._record_stage(
                    state,
                    PipelineStage.PARSING,
                    True,
                    parse_timer.elapsed_seconds / 2.0,
                    {"artefact_count": artefact_set.total_count},
                )
                stage_timings["acquisition_s"] = parse_timer.elapsed_seconds / 2.0
                stage_timings["parsing_s"] = parse_timer.elapsed_seconds / 2.0
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
                self._record_stage(
                    state,
                    PipelineStage.ACQUISITION,
                    False,
                    parse_timer.elapsed_seconds,
                    {},
                    errors=[str(exc)],
                )
                raise

        # Stage 3: AI triage with optional fallback.
        state.current_stage = PipelineStage.AI_TRIAGE
        with PerformanceTimer() as triage_timer:
            ranked = self._run_triage(artefact_set, use_fallback=use_fallback)
            analyzer_name = (
                self._fallback.analyzer_name
                if use_fallback or not self._analyzer.is_available()
                else self._analyzer.analyzer_name
            )
            try:
                active = (
                    self._fallback
                    if use_fallback or not self._analyzer.is_available()
                    else self._analyzer
                )
                summary = active.summarize(ranked)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"summarize:{exc}")
                summary = self._fallback.summarize(ranked)
                analyzer_name = self._fallback.analyzer_name
        stage_timings["triage_s"] = triage_timer.elapsed_seconds
        self._record_stage(
            state,
            PipelineStage.AI_TRIAGE,
            True,
            triage_timer.elapsed_seconds,
            {"ranked_count": len(ranked), "analyzer": analyzer_name},
            errors=errors[-1:] if errors else [],
        )

        # Stage 4: reporting.
        state.current_stage = PipelineStage.REPORTING
        with PerformanceTimer() as report_timer:
            report = self._report_builder.build_complete_report(
                case=case,
                artefact_set=artefact_set,
                ranked_artefacts=ranked,
                summary_text=summary,
                llm_model=analyzer_name,
                generation_params={"use_fallback": use_fallback},
                stage_timings={
                    **stage_timings,
                    "reporting_s": 0.0,
                },
            )
        stage_timings["reporting_s"] = report_timer.elapsed_seconds
        report.stage_timings = dict(stage_timings)
        report.pipeline_duration_seconds = float(sum(stage_timings.values()))
        self._report_repo.save(report)
        self._pipeline_reports[state.pipeline_id] = report.report_id
        self._record_stage(
            state,
            PipelineStage.REPORTING,
            True,
            report_timer.elapsed_seconds,
            {"report_id": report.report_id},
        )

        # Stage 5 placeholder marker (evaluation is opt-in via API).
        self._record_stage(
            state,
            PipelineStage.EVALUATION,
            True,
            0.0,
            {"status": "skipped_optional"},
        )
        state.completed_at = datetime.now(UTC)
        state.current_stage = PipelineStage.EVALUATION

        self._audit_logger.log_action(
            stage=PipelineStage.REPORTING,
            action="PIPELINE_COMPLETE",
            evidence_id=evidence.evidence_id,
            details={
                "pipeline_id": state.pipeline_id,
                "report_id": report.report_id,
                "duration_seconds": (state.completed_at - pipeline_start).total_seconds(),
            },
        )
        return report

    def run_parse_only(
        self,
        evidence_path: Path,
        case: CaseMetadata,
    ) -> ArtefactSet:
        """Run acquisition and parsing only.

        Args:
            evidence_path: Evidence path.
            case: Case metadata.

        Returns:
            Normalised artefact set.
        """
        evidence, artefact_set = self._forensic.process_evidence(evidence_path, case)
        self._evidence_repo.save(evidence)
        self._artefact_cache[evidence.evidence_id] = artefact_set
        return artefact_set

    def run_triage_only(
        self,
        artefact_set: ArtefactSet,
        *,
        use_fallback: bool = False,
    ) -> list[RankedArtefact]:
        """Run AI triage only on an existing artefact set.

        Args:
            artefact_set: Parsed artefacts.
            use_fallback: Force rule-based analyser.

        Returns:
            Ranked artefacts.
        """
        return self._run_triage(artefact_set, use_fallback=use_fallback)

    def start_pipeline(
        self,
        evidence_id: str,
        *,
        mode: str = "full",
        use_fallback: bool = False,
    ) -> PipelineState:
        """Start a pipeline run for previously registered evidence.

        Args:
            evidence_id: Registered evidence identifier.
            mode: ``full``, ``parse-only``, or ``triage-only``.
            use_fallback: Force rule-based triage.

        Returns:
            Pipeline state snapshot.

        Raises:
            EvidenceNotFoundError: If evidence metadata is missing.
        """
        evidence = self._evidence_repo.get(evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(
                f"Evidence not found: {evidence_id}",
                context={"evidence_id": evidence_id},
            )
        case = evidence.case
        state = PipelineState(case=case, current_stage=PipelineStage.ACQUISITION)
        self._pipeline_states[state.pipeline_id] = state

        try:
            if mode == "parse-only":
                artefact_set = self.run_parse_only(evidence.file_path, case)
                self._record_stage(
                    state,
                    PipelineStage.PARSING,
                    True,
                    0.0,
                    {"artefact_count": artefact_set.total_count},
                )
                state.completed_at = datetime.now(UTC)
            elif mode == "triage-only":
                artefact_set = self._artefact_cache.get(evidence_id)
                if artefact_set is None:
                    artefact_set = self.run_parse_only(evidence.file_path, case)
                ranked = self.run_triage_only(artefact_set, use_fallback=use_fallback)
                self._record_stage(
                    state,
                    PipelineStage.AI_TRIAGE,
                    True,
                    0.0,
                    {"ranked_count": len(ranked)},
                )
                state.completed_at = datetime.now(UTC)
            else:
                report = self.run_full_pipeline(
                    evidence.file_path,
                    case,
                    use_fallback=use_fallback,
                )
                # run_full_pipeline creates its own state; copy report link.
                for pipeline_id, report_id in list(self._pipeline_reports.items()):
                    if report_id == report.report_id:
                        return self._pipeline_states[pipeline_id]
                self._pipeline_reports[state.pipeline_id] = report.report_id
                state.completed_at = datetime.now(UTC)
        except DFATError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._record_stage(
                state,
                state.current_stage,
                False,
                0.0,
                {},
                errors=[str(exc)],
            )
            raise
        return state

    def get_pipeline_state(self, pipeline_id: str) -> Optional[PipelineState]:
        """Return a pipeline state by ID."""
        return self._pipeline_states.get(pipeline_id)

    def list_benchmark_results(self) -> list[BenchmarkResult]:
        """Return stored benchmark results."""
        return list(self._benchmark_results)

    def run_benchmark(
        self,
        evidence_id: str,
        ground_truth_path: Path,
        dataset_name: str,
    ) -> BenchmarkResult:
        """Run benchmark comparison for recovered artefacts.

        Args:
            evidence_id: Evidence identifier.
            ground_truth_path: Path to ground-truth JSON.
            dataset_name: Dataset display name override.

        Returns:
            Benchmark result.
        """
        artefact_set = self._artefact_cache.get(evidence_id)
        if artefact_set is None:
            raise EvidenceNotFoundError(
                f"No cached artefacts for evidence: {evidence_id}",
                context={"evidence_id": evidence_id},
            )
        ground_truth = self._ground_truth_loader.load(ground_truth_path)
        ground_truth["dataset_name"] = dataset_name or ground_truth.get(
            "dataset_name",
            dataset_name,
        )
        end = datetime.now(UTC)
        start = end
        result = self._benchmark_comparator.compare(
            artefact_set,
            ground_truth,
            start,
            end,
        )
        self._benchmark_results.append(result)
        return result

    def get_report_id_for_pipeline(self, pipeline_id: str) -> Optional[str]:
        """Return report ID associated with a pipeline run."""
        return self._pipeline_reports.get(pipeline_id)

    def _run_triage(
        self,
        artefact_set: ArtefactSet,
        *,
        use_fallback: bool,
    ) -> list[RankedArtefact]:
        """Execute triage with LLM-or-fallback selection."""
        active: IArtefactAnalyzer
        if use_fallback or not self._analyzer.is_available():
            active = self._fallback
        else:
            active = self._analyzer
        try:
            ranked = active.analyze(artefact_set)
        except Exception:  # noqa: BLE001
            ranked = self._fallback.analyze(artefact_set)
        if not ranked and artefact_set.artefacts:
            # Ensure every artefact has at least INFORMATIONAL ranking.
            ranked = [
                RankedArtefact(
                    **artefact.model_dump(),
                    suspicion_level=SuspicionLevel.INFORMATIONAL,
                    relevance_score=0.0,
                    classification_reasoning="Defaulted by pipeline orchestrator",
                )
                for artefact in artefact_set.artefacts
            ]
        return ranked

    def _record_stage(
        self,
        state: PipelineState,
        stage: PipelineStage,
        success: bool,
        duration: float,
        metadata: dict[str, Any],
        errors: Optional[list[str]] = None,
    ) -> None:
        """Record a stage result on the pipeline state."""
        state.current_stage = stage
        state.stage_results[stage.value] = StageResult(
            stage=stage,
            success=success,
            duration_seconds=duration,
            output_data=metadata,
            errors=list(errors or []),
        )
