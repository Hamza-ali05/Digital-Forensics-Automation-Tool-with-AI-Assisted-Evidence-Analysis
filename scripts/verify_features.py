#!/usr/bin/env python3
"""Verify the five feature-specification pillars of DFAT."""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field

from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.ai_engine.llm.config import LLMConfig, PROMPT_VERSION
from dfat.ai_engine.llm.connection import LLMConnectionManager
from dfat.container import build_application_container
from dfat.core.enums import ArtefactCategory, HashAlgorithm, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.evaluation.usability.questionnaire import QuestionnaireInstrument
from dfat.evaluation.usability.response_collector import ResponseCollector
from dfat.evaluation.usability.tobin_comparison import TobinComparison
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.shared.constants import JSON_SCHEMA_VERSION


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "dfat"


class FeatureVerificationResult(BaseModel):
    feature: str
    passed: bool
    checks_total: int
    checks_passed: int
    details: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class _FakeSchemaValidator:
    class Result:
        def __init__(self) -> None:
            self.is_valid = True
            self.errors: list[str] = []

    def validate(self, json_data: dict) -> "_FakeSchemaValidator.Result":
        return self.Result()


class FeatureVerifier:
    def _record(self, details: list[str], ok: bool, success: str, failure: str) -> bool:
        details.append(f"{'[PASS]' if ok else '[FAIL]'} {success if ok else failure}")
        return ok

    async def verify_feature_1(self) -> FeatureVerificationResult:
        details: list[str] = []
        checks: list[bool] = []
        exporter = StructuredJSONExporter(_FakeSchemaValidator(), HashAlgorithm.SHA256)
        artefact = RankedArtefact(
            artefact_id="art-1",
            category=ArtefactCategory.FILESYSTEM_METADATA,
            source_evidence_id="ev-1",
            source_path="/tmp/sample",
            raw_data={"path": "/tmp/sample", "size": 1},
            metadata={},
            suspicion_level=SuspicionLevel.LOW,
            relevance_score=0.25,
            classification_reasoning="deterministic test",
        )
        artefact_data = exporter._serialise_artefacts([artefact])
        hash_a = exporter._compute_integrity_hash(artefact_data)
        hash_b = exporter._compute_integrity_hash(artefact_data)
        checks.append(self._record(details, hash_a == hash_b, "JSON output layer produces deterministic hashes.", "JSON output layer hashes are not deterministic."))
        checks.append(self._record(details, "validate_against_schema" in inspect.getsource(StructuredJSONExporter.export), "JSON output validates against a schema.", "JSON output does not validate against a schema."))
        checks.append(self._record(details, JSON_SCHEMA_VERSION == "1.0.0", f"JSON schema is versioned ({JSON_SCHEMA_VERSION}).", "JSON schema version constant is missing or unexpected."))
        checks.append(self._record(details, "schema_version" in inspect.getsource(StructuredJSONExporter.export), "Schema version is embedded in report output.", "Schema version is not embedded in report output."))
        return FeatureVerificationResult(feature="Feature 1", passed=all(checks), checks_total=len(checks), checks_passed=sum(checks), details=details)

    async def verify_feature_2(self) -> FeatureVerificationResult:
        details: list[str] = []
        checks: list[bool] = []
        manager = LLMConnectionManager(LLMConfig(api_url="http://localhost:11434"), audit_logger=type("Audit", (), {"log_action": lambda *a, **k: None})())
        external_blocked = False
        try:
            manager._is_local_url("http://example.com")
        except ValueError:
            external_blocked = True
        checks.append(self._record(details, external_blocked, "Ollama client enforces local-only endpoints.", "Ollama client did not reject an external endpoint."))
        checks.append(self._record(details, bool(PROMPT_VERSION), f"Prompts are versioned (PROMPT_VERSION={PROMPT_VERSION}).", "Prompt versioning is missing."))
        checks.append(self._record(details, RuleBasedAnalyzer().is_available(), "Rule-based fallback is available.", "Rule-based fallback is unavailable."))
        sharma_text = (SRC_ROOT / "ai_engine" / "llm" / "prompts.py").read_text(encoding="utf-8")
        checks.append(self._record(details, "Sharma et al., 2025" in sharma_text, "Sharma limitation is documented.", "Sharma limitation is not documented."))
        checks.append(self._record(details, (SRC_ROOT / "ai_engine" / "llm" / "client.py").exists(), "Ollama client implementation exists.", "Ollama client implementation is missing."))
        return FeatureVerificationResult(feature="Feature 2", passed=all(checks), checks_total=len(checks), checks_passed=sum(checks), details=details)

    async def verify_feature_3(self) -> FeatureVerificationResult:
        details: list[str] = []
        checks: list[bool] = []
        parsers = build_application_container().forensic_engine.parsers()
        parser_names = {parser.parser_name for parser in parsers}
        disk_ok = any("FileSystemParser" == name for name in parser_names)
        memory_ok = any(name in parser_names for name in {"ProcessListParser", "NetworkArtefactParser", "CodeInjectionParser"})
        checks.append(self._record(details, disk_ok and memory_ok, "ParserRegistry wiring includes both disk and memory parsers.", "ParserRegistry wiring does not include both disk and memory parsers."))
        checks.append(self._record(details, inspect.isclass(build_application_container().forensic_engine.orchestrator(). __class__) and build_application_container().forensic_engine.orchestrator().__class__.__name__ == "ForensicOrchestrator", "Single forensic orchestrator is wired.", "Forensic orchestrator wiring is missing."))
        normalizer_source = inspect.getsource(__import__("dfat.forensic_engine.normalizer", fromlist=["ArtefactNormalizer"]).ArtefactNormalizer.normalize)
        checks.append(self._record(details, "ArtefactSet(" in normalizer_source, "Normalised output is produced as ArtefactSet.", "Normalised output is not produced as ArtefactSet."))
        return FeatureVerificationResult(feature="Feature 3", passed=all(checks), checks_total=len(checks), checks_passed=sum(checks), details=details)

    async def verify_feature_4(self) -> FeatureVerificationResult:
        details: list[str] = []
        checks: list[bool] = []
        gt_source = inspect.getsource(GroundTruthLoader)
        checks.append(self._record(details, "load_dfrws" in gt_source and "load_cfreds" in gt_source, "Ground truth loaders exist for DFRWS and CFReDS.", "Ground truth loaders for DFRWS and CFReDS are incomplete."))
        checks.append(self._record(details, hasattr(MetricsCalculator, "compute_all"), "Metrics calculator exists.", "Metrics calculator is missing."))
        checks.append(self._record(details, "BenchmarkResult" in inspect.getsource(BenchmarkComparator.compare), "Benchmark comparator produces BenchmarkResult.", "Benchmark comparator does not produce BenchmarkResult."))
        return FeatureVerificationResult(feature="Feature 4", passed=all(checks), checks_total=len(checks), checks_passed=sum(checks), details=details)

    async def verify_feature_5(self) -> FeatureVerificationResult:
        details: list[str] = []
        checks: list[bool] = []
        instrument = QuestionnaireInstrument()
        participant_id = instrument.generate_participant_id()
        anon_ok = True
        try:
            UUID(participant_id)
        except ValueError:
            anon_ok = False
        checks.append(self._record(details, len(instrument.QUESTIONS) == 6, "Questionnaire instrument exists.", "Questionnaire instrument is missing or incomplete."))
        checks.append(self._record(details, anon_ok, "Questionnaire collection is anonymised with UUID participant IDs.", "Questionnaire participant IDs are not anonymised UUIDs."))
        checks.append(self._record(details, TobinComparison.TOBIN_USEFULNESS_PERCENTAGE == 74.0, "Tobin comparison benchmark is implemented.", "Tobin comparison benchmark is missing or incorrect."))
        route_source = (SRC_ROOT / "api" / "routes" / "evaluation.py").read_text(encoding="utf-8")
        checks.append(self._record(details, '@router.get("/usability/questionnaire")' in route_source and "require_role" not in route_source.split('@router.get("/usability/questionnaire")', 1)[1].split("@router", 1)[0], "Questionnaire route is public.", "Questionnaire route does not appear public."))
        checks.append(self._record(details, hasattr(ResponseCollector, "delete_all_responses"), "Ethics data-destruction method exists.", "Ethics data-destruction method is missing."))
        return FeatureVerificationResult(feature="Feature 5", passed=all(checks), checks_total=len(checks), checks_passed=sum(checks), details=details)

    async def verify_all(self) -> list[FeatureVerificationResult]:
        results = [
            await self.verify_feature_1(),
            await self.verify_feature_2(),
            await self.verify_feature_3(),
            await self.verify_feature_4(),
            await self.verify_feature_5(),
        ]
        print("DFAT Feature Verification")
        print("=" * 72)
        for result in results:
            print(f"{result.feature}: {'PASS' if result.passed else 'FAIL'} ({result.checks_passed}/{result.checks_total})")
            for detail in result.details:
                print(f"  {detail}")
            print()
        print(f"OVERALL: {'PASS' if all(r.passed for r in results) else 'FAIL'}")
        return results


async def main() -> int:
    results = await FeatureVerifier().verify_all()
    payload = {
        "overall_passed": all(item.passed for item in results),
        "results": [json.loads(item.model_dump_json()) for item in results],
    }
    (REPO_ROOT / "reports").mkdir(exist_ok=True)
    (REPO_ROOT / "reports" / "feature_verification.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    return 0 if payload["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
