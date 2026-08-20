#!/usr/bin/env python3
"""Verify the dissertation research objectives against the DFAT implementation."""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, Field

from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.ai_engine.llm.config import FORENSIC_SYSTEM_PROMPT, LLMConfig, PROMPT_VERSION
from dfat.ai_engine.llm.connection import LLMConnectionManager
from dfat.ai_engine.validation.hallucination_guard import HallucinationGuard
from dfat.container import build_application_container
from dfat.core.enums import ArtefactCategory, EvidenceType, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.core.models.evaluation import BenchmarkResult, UsabilityResponse
from dfat.core.models.evidence import CaseMetadata
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.evaluation.benchmark.performance import PerformanceAnalyzer, SpeedupResult
from dfat.evaluation.usability.questionnaire import QuestionnaireInstrument
from dfat.evaluation.usability.response_analyzer import ResponseAnalyzer
from dfat.evaluation.usability.response_collector import ResponseCollector
from dfat.evaluation.usability.tobin_comparison import TobinComparison
from dfat.forensic_engine.normalizer import ArtefactNormalizer
from dfat.forensic_engine.orchestrator import ForensicOrchestrator
from dfat.pipeline.parser_registry import ParserRegistry
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.narrative import NarrativeAssembler


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "dfat"


class VerificationResult(BaseModel):
    """Result of one research-question verification run."""

    rq: str
    passed: bool
    checks_total: int
    checks_passed: int
    details: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class _NullAuditLogger:
    def log_action(self, *args: Any, **kwargs: Any) -> None:
        return None


class _NullAuditService:
    async def log_action(self, *args: Any, **kwargs: Any) -> None:
        return None


class _NullBenchmarkRepo:
    async def save(self, result: BenchmarkResult) -> None:
        return None

    async def get_by_dataset(self, dataset_name: str) -> list[BenchmarkResult]:
        return []


class _NullUsabilityRepo:
    async def delete_all_responses(self) -> int:
        return 0


class ResearchObjectiveVerifier:
    """Automated verification that each research question is implemented."""

    def __init__(self) -> None:
        self.repo_root = REPO_ROOT
        self.src_root = SRC_ROOT
        self._container = None
        self._parser_registry_instance = None
        self._parsers = None

    def _record(
        self,
        details: list[str],
        condition: bool,
        success: str,
        failure: str,
    ) -> bool:
        details.append(f"{'[PASS]' if condition else '[FAIL]'} {success if condition else failure}")
        return condition

    def _source_contains(self, path: Path, needle: str) -> bool:
        return needle in path.read_text(encoding="utf-8")

    def _parser_registry(self) -> ParserRegistry:
        if self._parser_registry_instance is None:
            registry = ParserRegistry()
            for parser in self._parsers_from_container():
                registry.register(parser)
            self._parser_registry_instance = registry
        return self._parser_registry_instance

    def _parsers_from_container(self) -> list[Any]:
        if self._parsers is None:
            self._parsers = build_application_container().forensic_engine.parsers()
        return self._parsers

    def _artefact_sample(self) -> Artefact:
        return Artefact(
            artefact_id="art-001",
            category=ArtefactCategory.FILESYSTEM_METADATA,
            source_evidence_id="ev-001",
            source_path="/evidence/sample.txt",
            raw_data={"path": "/evidence/sample.txt", "size": 123},
        )

    async def verify_rq1(self) -> VerificationResult:
        """RQ1: Automated triage extracting and classifying artefacts."""
        details: list[str] = []
        parsers = self._parsers_from_container()
        registry = self._parser_registry()

        check_results = [
            self._record(
                details,
                len(registry.get_all_parsers()) >= 7,
                f"ParserRegistry exposes {len(registry.get_all_parsers())} registered parsers (>= 7).",
                f"ParserRegistry exposes only {len(registry.get_all_parsers())} parsers (< 7).",
            )
        ]

        covered_categories = set()
        for path in (self.src_root / "forensic_engine" / "parsers").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            covered_categories.update(re.findall(r"ArtefactCategory\.([A-Z_]+)", text))
        expected_categories = {category.name for category in ArtefactCategory}
        check_results.append(
            self._record(
                details,
                expected_categories.issubset(covered_categories),
                "Parser implementations cover all ArtefactCategory enum values.",
                f"Parser coverage missing categories: {sorted(expected_categories - covered_categories)}.",
            )
        )

        detector_source = inspect.getsource(ForensicOrchestrator._detect_evidence_type)
        routes_disk = "EvidenceType.DISK_IMAGE" in detector_source
        routes_memory = "EvidenceType.MEMORY_DUMP" in detector_source
        check_results.append(
            self._record(
                details,
                routes_disk and routes_memory,
                "ForensicOrchestrator routes both DISK_IMAGE and MEMORY_DUMP evidence types.",
                "ForensicOrchestrator does not clearly route both disk and memory evidence.",
            )
        )

        normalizer = ArtefactNormalizer()
        artefact = self._artefact_sample()
        merged = normalizer.normalize(
            [
                ArtefactSet(evidence_id="ev-001", artefacts=[artefact], categories_present=[artefact.category]),
                ArtefactSet(evidence_id="ev-001", artefacts=[artefact], categories_present=[artefact.category]),
            ],
            "ev-001",
        )
        check_results.append(
            self._record(
                details,
                isinstance(merged, ArtefactSet) and merged.total_count == 1,
                "ArtefactNormalizer returns a unified deduplicated ArtefactSet.",
                "ArtefactNormalizer did not return a deduplicated ArtefactSet.",
            )
        )

        parser_contract_ok = True
        parser_dir = self.src_root / "forensic_engine" / "parsers"
        for path in parser_dir.rglob("*.py"):
            if path.name == "base.py":
                continue
            text = path.read_text(encoding="utf-8")
            if "class " in text and "Parser" in text and "raw_data=" not in text:
                parser_contract_ok = False
                break
        adr_ok = (self.repo_root / "docs" / "architecture" / "adr" / "ADR-015-artefact-raw-data-contracts.md").exists()
        check_results.append(
            self._record(
                details,
                parser_contract_ok and adr_ok,
                "Parser output code and ADR-015 both enforce documented raw_data contracts.",
                "Parser raw_data contracts are incomplete in code or ADR-015 is missing.",
            )
        )

        return VerificationResult(
            rq="RQ1",
            passed=all(check_results),
            checks_total=len(check_results),
            checks_passed=sum(check_results),
            details=details,
        )

    async def verify_rq2(self) -> VerificationResult:
        """RQ2: Locally deployed LLM providing investigative summaries."""
        details: list[str] = []
        check_results: list[bool] = []

        host = (urlparse(LLMConfig().api_url).hostname or "").lower()
        check_results.append(
            self._record(
                details,
                host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"},
                f"LLMConfig default api_url is local-only ({LLMConfig().api_url}).",
                f"LLMConfig default api_url is not local-only ({LLMConfig().api_url}).",
            )
        )

        manager = LLMConnectionManager(LLMConfig(api_url="http://localhost:11434"), _NullAuditLogger())
        external_rejected = False
        try:
            manager._is_local_url("https://example.com")
        except ValueError:
            external_rejected = True
        check_results.append(
            self._record(
                details,
                external_rejected,
                "_is_local_url() rejects external LLM endpoints.",
                "_is_local_url() failed to reject an external LLM endpoint.",
            )
        )

        anti_hallucination = all(
            phrase in FORENSIC_SYSTEM_PROMPT
            for phrase in [
                "Never fabricate",
                "Only base conclusions on the artefact data provided",
                "Reference specific artefact IDs",
            ]
        )
        check_results.append(
            self._record(
                details,
                anti_hallucination,
                "FORENSIC_SYSTEM_PROMPT contains explicit anti-hallucination rules.",
                "FORENSIC_SYSTEM_PROMPT is missing one or more anti-hallucination rules.",
            )
        )

        guard = HallucinationGuard(
            valid_artefact_ids={"art-known"},
            valid_categories={c.value for c in ArtefactCategory},
            valid_suspicion_levels={s.value for s in SuspicionLevel},
        )
        report = guard.check_response("Artefact art-fabricated indicates malware.")
        check_results.append(
            self._record(
                details,
                "art-fabricated" in report.hallucinated_ids and report.risk_level in {"medium", "high"},
                "HallucinationGuard flags fabricated artefact identifiers.",
                "HallucinationGuard did not flag a fabricated artefact identifier.",
            )
        )

        disclaimer_source = inspect.getsource(NarrativeAssembler._build_disclaimer)
        check_results.append(
            self._record(
                details,
                "Scanlon et al., 2023" in disclaimer_source,
                "Narrative report generation embeds the Scanlon et al. disclaimer.",
                "Narrative report generation is missing the Scanlon et al. disclaimer.",
            )
        )

        prompt_tracking = (
            "prompt_version" in inspect.getsource(StructuredJSONExporter._normalise_ai_metadata)
            and "prompt_version" in inspect.getsource(NarrativeAssembler.assemble)
            and bool(PROMPT_VERSION)
        )
        check_results.append(
            self._record(
                details,
                prompt_tracking,
                f"Prompt versioning is tracked in report outputs (PROMPT_VERSION={PROMPT_VERSION}).",
                "Prompt versioning is not propagated into report outputs.",
            )
        )

        fallback = RuleBasedAnalyzer()
        check_results.append(
            self._record(
                details,
                fallback.is_available() and fallback.analyzer_name == "RuleBasedFallback",
                "RuleBasedAnalyzer is available as deterministic fallback.",
                "RuleBasedAnalyzer fallback is unavailable.",
            )
        )

        boot_sequencer = self.src_root / "bootstrap" / "boot_sequencer.py"
        recovery = self.src_root / "runtime" / "recovery_manager.py"
        check_results.append(
            self._record(
                details,
                boot_sequencer.exists()
                and "BOOT_SEQUENCE" in boot_sequencer.read_text(encoding="utf-8")
                and recovery.exists()
                and "attempt_recovery" in recovery.read_text(encoding="utf-8"),
                "Prompt 12 boot sequencer and recovery manager remain available for local LLM degradation.",
                "Prompt 12 boot/recovery components are missing or incomplete.",
            )
        )

        sharma_documented = all(
            "Sharma et al., 2025" in path.read_text(encoding="utf-8")
            for path in [
                self.src_root / "ai_engine" / "llm" / "config.py",
                self.src_root / "ai_engine" / "llm" / "prompts.py",
            ]
        )
        check_results.append(
            self._record(
                details,
                sharma_documented,
                "AI module docstrings document the Sharma et al. (2025) limitation.",
                "Sharma et al. (2025) limitation is not documented in the expected AI modules.",
            )
        )

        return VerificationResult(
            rq="RQ2",
            passed=all(check_results),
            checks_total=len(check_results),
            checks_passed=sum(check_results),
            details=details,
        )

    async def verify_rq3(self) -> VerificationResult:
        """RQ3: Time-to-triage measurement."""
        details: list[str] = []
        check_results: list[bool] = []

        timer_used = sum(
            "PerformanceTimer" in path.read_text(encoding="utf-8")
            for path in [
                self.src_root / "forensic_engine" / "orchestrator.py",
                self.src_root / "pipeline" / "job_runner.py",
            ]
        ) >= 2
        check_results.append(
            self._record(
                details,
                timer_used,
                "PerformanceTimer is used in orchestrator/pipeline execution code.",
                "PerformanceTimer usage was not found in the expected pipeline execution code.",
            )
        )

        calc = MetricsCalculator()
        ttt = calc.compute_time_to_triage(
            datetime.now(UTC),
            datetime.now(UTC) + timedelta(seconds=12),
        )
        check_results.append(
            self._record(
                details,
                abs(ttt - 12.0) < 0.5,
                "MetricsCalculator.compute_time_to_triage() exists and returns elapsed seconds.",
                "MetricsCalculator.compute_time_to_triage() did not return the expected elapsed time.",
            )
        )

        analyzer = PerformanceAnalyzer(_NullBenchmarkRepo())
        sample_results = [
            BenchmarkResult(
                dataset_name="demo",
                precision=0.8,
                recall=0.7,
                f1_score=0.746,
                time_to_triage_seconds=value,
                artefacts_expected=10,
                artefacts_recovered=9,
                false_positives=1,
                false_negatives=2,
            )
            for value in (10.0, 20.0, 30.0)
        ]
        stats = analyzer.compute_time_statistics(sample_results)
        check_results.append(
            self._record(
                details,
                stats.mean == 20.0 and stats.median == 20.0 and stats.p95 >= 29.0,
                "PerformanceAnalyzer computes mean/median/p95 statistics.",
                "PerformanceAnalyzer did not compute the expected descriptive statistics.",
            )
        )

        speedup = analyzer.compare_against_baseline(tool_ttt=10.0, baseline_ttt=20.0)
        check_results.append(
            self._record(
                details,
                isinstance(speedup, SpeedupResult) and speedup.speedup_factor == 2.0,
                "SpeedupResult baseline comparison is implemented and correct.",
                "Baseline speedup comparison did not return the expected result.",
            )
        )

        perf_dashboard = self.repo_root / "frontend" / "src" / "pages" / "evaluation" / "PerformanceDashboard.js"
        check_results.append(
            self._record(
                details,
                perf_dashboard.exists(),
                "Frontend PerformanceDashboard page exists.",
                "Frontend PerformanceDashboard page is missing.",
            )
        )

        return VerificationResult(
            rq="RQ3",
            passed=all(check_results),
            checks_total=len(check_results),
            checks_passed=sum(check_results),
            details=details,
        )

    async def verify_rq4(self) -> VerificationResult:
        """RQ4: Artefact recovery accuracy against benchmarks."""
        details: list[str] = []
        check_results: list[bool] = []

        gt_source = inspect.getsource(GroundTruthLoader)
        check_results.append(
            self._record(
                details,
                "load_dfrws" in gt_source and "load_cfreds" in gt_source,
                "GroundTruthLoader supports both DFRWS and CFReDS loaders.",
                "GroundTruthLoader does not expose both DFRWS and CFReDS loader paths.",
            )
        )

        calc = MetricsCalculator()
        precision = calc.compute_precision(8, 2)
        recall = calc.compute_recall(8, 4)
        f1 = calc.compute_f1(precision, recall)
        check_results.append(
            self._record(
                details,
                abs(precision - 0.8) < 1e-9 and abs(recall - (8 / 12)) < 1e-9 and abs(f1 - (2 * precision * recall / (precision + recall))) < 1e-9,
                "MetricsCalculator computes precision/recall/F1 correctly for known values.",
                "MetricsCalculator failed a known precision/recall/F1 calculation.",
            )
        )

        comparator_source = inspect.getsource(BenchmarkComparator.compare)
        check_results.append(
            self._record(
                details,
                "true_positives_set = recovered_ids & expected_ids" in comparator_source
                and "false_positives_set = recovered_ids - expected_ids" in comparator_source
                and "false_negatives_set = expected_ids - recovered_ids" in comparator_source,
                "BenchmarkComparator identifies TP/FP/FN via set comparison.",
                "BenchmarkComparator TP/FP/FN logic is missing or altered.",
            )
        )

        report_source = inspect.getsource(BenchmarkComparator.generate_comparison_report)
        check_results.append(
            self._record(
                details,
                "per_category" in report_source and "category_breakdown" in report_source,
                "Per-category benchmark breakdown is available in comparison reports.",
                "Per-category benchmark breakdown is missing from comparison reports.",
            )
        )

        zero_division_safe = (
            calc.compute_precision(0, 0) == 0.0
            and calc.compute_recall(0, 0) == 0.0
            and calc.compute_f1(0.0, 0.0) == 0.0
        )
        check_results.append(
            self._record(
                details,
                zero_division_safe,
                "Benchmark metric division-by-zero cases return 0.0 safely.",
                "One or more benchmark metric division-by-zero cases did not return 0.0.",
            )
        )

        return VerificationResult(
            rq="RQ4",
            passed=all(check_results),
            checks_total=len(check_results),
            checks_passed=sum(check_results),
            details=details,
        )

    async def verify_rq5(self) -> VerificationResult:
        """RQ5: Investigator usability experiences."""
        details: list[str] = []
        check_results: list[bool] = []

        instrument = QuestionnaireInstrument()
        check_results.append(
            self._record(
                details,
                len(instrument.QUESTIONS) == 6,
                "QuestionnaireInstrument contains 6 frozen questions.",
                f"QuestionnaireInstrument contains {len(instrument.QUESTIONS)} questions instead of 6.",
            )
        )

        check_results.append(
            self._record(
                details,
                instrument.INSTRUMENT_VERSION == "1.0.0",
                "Questionnaire instrument version is 1.0.0.",
                f"Questionnaire instrument version is {instrument.INSTRUMENT_VERSION}, expected 1.0.0.",
            )
        )

        participant_id = instrument.generate_participant_id()
        uuid_ok = False
        try:
            UUID(participant_id)
            uuid_ok = True
        except ValueError:
            uuid_ok = False
        check_results.append(
            self._record(
                details,
                uuid_ok,
                "Participant identifiers are anonymised UUIDs.",
                f"Participant identifier is not a valid UUID: {participant_id}",
            )
        )

        responses = [
            UsabilityResponse(
                participant_id=str(UUID(int=1)),
                usefulness_rating=5,
                accuracy_rating=4,
                clarity_rating=4,
                q1_rating=5,
                q4_rating=4,
                comparative_rating=4,
            ),
            UsabilityResponse(
                participant_id=str(UUID(int=2)),
                usefulness_rating=2,
                accuracy_rating=3,
                clarity_rating=3,
                q1_rating=2,
                q4_rating=2,
                comparative_rating=3,
            ),
        ]
        usefulness_pct = ResponseAnalyzer(responses).compute_usefulness_percentage()
        check_results.append(
            self._record(
                details,
                usefulness_pct == 50.0,
                "ResponseAnalyzer.compute_usefulness_percentage() works on mixed responses.",
                f"ResponseAnalyzer usefulness percentage returned {usefulness_pct}, expected 50.0.",
            )
        )

        check_results.append(
            self._record(
                details,
                TobinComparison.TOBIN_USEFULNESS_PERCENTAGE == 74.0,
                "Tobin benchmark usefulness percentage is fixed at 74.0.",
                f"Tobin benchmark usefulness percentage is {TobinComparison.TOBIN_USEFULNESS_PERCENTAGE}, expected 74.0.",
            )
        )

        route_source = inspect.getsource(
            __import__("dfat.api.routes.evaluation", fromlist=["get_usability_questionnaire"]).get_usability_questionnaire
        )
        no_auth = "require_role" not in route_source
        public_frontend_route = self._source_contains(
            self.repo_root / "frontend" / "e2e" / "questionnaire.spec.js",
            'page.goto("/questionnaire")',
        )
        check_results.append(
            self._record(
                details,
                no_auth and public_frontend_route,
                "Questionnaire is exposed publicly without authentication.",
                "Questionnaire route does not appear to be public end-to-end.",
            )
        )

        check_results.append(
            self._record(
                details,
                hasattr(ResponseCollector, "delete_all_responses"),
                "ResponseCollector.delete_all_responses() exists for ethics data destruction.",
                "ResponseCollector.delete_all_responses() is missing.",
            )
        )

        return VerificationResult(
            rq="RQ5",
            passed=all(check_results),
            checks_total=len(check_results),
            checks_passed=sum(check_results),
            details=details,
        )

    async def verify_all(self) -> list[VerificationResult]:
        results = [
            await self.verify_rq1(),
            await self.verify_rq2(),
            await self.verify_rq3(),
            await self.verify_rq4(),
            await self.verify_rq5(),
        ]
        self.print_report(results)
        self._assert_prompt12_docs_present()
        return results

    def _assert_prompt12_docs_present(self) -> None:
        """Print Prompt 12 documentation presence (does not alter RQ pass/fail)."""
        docs = [
            self.repo_root / "docs" / "architecture" / "adr" / "029-boot-sequence-dependency-order.md",
            self.repo_root / "docs" / "architecture" / "adr" / "030-graceful-degradation-philosophy.md",
            self.repo_root / "docs" / "architecture" / "adr" / "031-local-first-architecture.md",
            self.repo_root / "docs" / "architecture" / "SYSTEM_INITIALIZATION.md",
            self.repo_root / "docs" / "operations" / "TROUBLESHOOTING.md",
        ]
        print("Prompt 12 documentation")
        print("-" * 72)
        for path in docs:
            status = "PASS" if path.exists() else "FAIL"
            print(f"  [{status}] {path.relative_to(self.repo_root)}")
        print()

    @staticmethod
    def print_report(results: list[VerificationResult]) -> None:
        print("DFAT Research Objective Verification")
        print("=" * 72)
        for result in results:
            print(f"{result.rq}: {'PASS' if result.passed else 'FAIL'} "
                  f"({result.checks_passed}/{result.checks_total})")
            for line in result.details:
                print(f"  {line}")
            print()
        overall = all(result.passed for result in results)
        print(f"OVERALL: {'PASS' if overall else 'FAIL'}")


async def main() -> int:
    results = await ResearchObjectiveVerifier().verify_all()
    summary = {
        "overall_passed": all(item.passed for item in results),
        "results": [json.loads(item.model_dump_json()) for item in results],
    }
    (REPO_ROOT / "reports").mkdir(exist_ok=True)
    (REPO_ROOT / "reports" / "research_objectives_verification.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    return 0 if summary["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
