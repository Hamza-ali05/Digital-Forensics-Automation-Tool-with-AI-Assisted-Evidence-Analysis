"""Integration tests for pipeline intelligence sources (Prompt 12.14)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.core.models.pipeline import StageResult
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.forensic_engine.triage.rule_engine import RuleBasedTriageEngine
from dfat.forensic_engine.triage.scoring import ScoringEngine, _LLM_WEIGHT_ML, _ML_WEIGHT, _RULE_WEIGHT_ML
from dfat.knowledge.rag.rag_analyzer import RAGEnhancedAnalyzer
from dfat.knowledge.rag.rag_prompts import RAGPromptTemplates
from dfat.pipeline.models import PipelineJob
from dfat.pipeline.stage_interface import PipelineContext
from dfat.pipeline.stages.triage_stage import TriageStage
from dfat.threat_intel.feed_manager import ThreatFeedManager
from dfat.threat_intel.mitre_mapper import MITREMapper
from dfat.threat_intel.sigma_engine import SigmaEngine
from dfat.threat_intel.stix_handler import STIXHandler
from dfat.threat_intel.yara_engine import YARAEngine


def _process_artefact(**raw: object) -> Artefact:
    return Artefact(
        artefact_id="art-intel-1",
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev-intel",
        raw_data=dict(raw),
    )


def _artefact_set() -> ArtefactSet:
    return ArtefactSet(
        evidence_id="ev-intel",
        artefacts=[
            _process_artefact(
                name="cmd.exe",
                pid=4242,
                CommandLine="C:\\tools\\mimikatz.exe sekurlsa::logonpasswords",
            )
        ],
        categories_present=[ArtefactCategory.RUNNING_PROCESS],
    )


def _write_sigma_rule(path: Path) -> None:
    rule = {
        "id": "pipeline-sigma-001",
        "title": "Mimikatz Process Creation",
        "level": "high",
        "description": "Detects mimikatz execution",
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {
            "selection": {"CommandLine|contains": "mimikatz"},
            "condition": "selection",
        },
        "tags": ["attack.credential_access", "attack.t1003"],
    }
    path.write_text(yaml.dump(rule), encoding="utf-8")


@pytest.mark.asyncio
async def test_pipeline_uses_rag_when_available() -> None:
    """RAG context is injected into AI output and source attribution is audited."""
    llm = MagicMock()
    llm.is_available = MagicMock(return_value=True)
    llm.analyzer_name = "LocalLLM"
    ranked = [
        RankedArtefact(
            **_process_artefact(name="cmd.exe").model_dump(),
            suspicion_level=SuspicionLevel.HIGH,
            relevance_score=0.9,
            classification_reasoning="Suspicious process",
        )
    ]
    llm.analyze_async = AsyncMock(return_value=ranked)
    llm._classifier = MagicMock()
    llm._classifier._prompt_builder = MagicMock()
    llm._classifier._prompt_builder._templates = MagicMock()
    llm._summarizer = MagicMock()
    llm._summarizer._prompt_builder = MagicMock()
    llm._summarizer._prompt_builder._templates = MagicMock()

    context_builder = AsyncMock()
    context_builder.build_classification_context_with_sources = AsyncMock(
        return_value=("Known credential dumping context from test-knowledge", ["test-knowledge"])
    )
    audit = AsyncMock()
    audit.log_action = AsyncMock()
    analyzer = RAGEnhancedAnalyzer(
        llm,
        context_builder,
        RAGPromptTemplates(),
        audit,
    )

    result = await analyzer.analyze_async(_artefact_set())

    assert result
    assert "[rag_sources: test-knowledge]" in result[0].classification_reasoning
    audit.log_action.assert_awaited()
    details = audit.log_action.await_args.kwargs.get("details") or audit.log_action.await_args.args[3]
    assert details["rag_used"] is True
    assert "test-knowledge" in details["contributing_datasets"]


@pytest.mark.asyncio
async def test_pipeline_uses_threat_intel(tmp_path: Path) -> None:
    """Loaded YARA/Sigma rules produce IOC-style matches and MITRE mappings."""
    yara_dir = tmp_path / "yara"
    sigma_dir = tmp_path / "sigma"
    yara_dir.mkdir()
    sigma_dir.mkdir()
    _write_sigma_rule(sigma_dir / "mimi.yml")

    yara_engine = YARAEngine(yara_dir)
    sigma_engine = SigmaEngine(sigma_dir)
    sigma_engine.load_rules()

    try:
        import yara  # noqa: F401

        rule_file = yara_dir / "mimi.yar"
        rule_file.write_text(
            'rule MimikatzRule { strings: $s = "mimikatz" condition: $s }',
            encoding="utf-8",
        )
        yara_engine.load_rules()
    except ImportError:
        pass

    ioc_kb = MagicMock(
        lookup_process_name=AsyncMock(return_value=[]),
        lookup_hash=AsyncMock(return_value=[]),
        lookup_ip=AsyncMock(return_value=[]),
        lookup_domain=AsyncMock(return_value=[]),
        lookup_registry_key=AsyncMock(return_value=[]),
        search=AsyncMock(return_value=[]),
    )
    graph = MagicMock(add_ioc_relationships=MagicMock(), save=MagicMock())
    audit = MagicMock(log_action=AsyncMock())

    manager = ThreatFeedManager(
        dataset_registry=MagicMock(),
        ioc_kb=ioc_kb,
        yara_engine=yara_engine,
        sigma_engine=sigma_engine,
        mitre_mapper=MITREMapper(),
        knowledge_graph=graph,
        audit_service=audit,
        stix_handler=STIXHandler(),
    )

    scan = await manager.scan_artefacts_against_intel(_artefact_set())

    assert scan.sigma_matches or scan.mitre_mappings
    if scan.sigma_matches:
        assert scan.sigma_matches[0].rule_name == "Mimikatz Process Creation"
        assert any("t1003" in tag.lower() for tag in scan.sigma_matches[0].mitre_techniques)
    assert scan.mitre_mappings
    assert any(mapping.technique_id for mapping in scan.mitre_mappings)


@pytest.mark.asyncio
async def test_pipeline_uses_ml_predictions(tmp_path: Path) -> None:
    """Trained ML models contribute scores and use the three-way weighting."""
    pytest.importorskip("sklearn")

    from dfat.ml.config import MLSettings
    from dfat.ml.dataset_builder import TrainingDataset
    from dfat.ml.experiment_tracker import ExperimentTracker
    from dfat.ml.feature_engineering import ALL_FEATURE_NAMES, ForensicFeatureExtractor
    from dfat.ml.model_registry import ModelRegistry
    from dfat.ml.models import MalwareClassifier
    from dfat.ml.predictor import MLPredictor
    from dfat.ml.trainer import ModelTrainer

    extractor = ForensicFeatureExtractor()

    def _row(name: str) -> list[float]:
        artefact = _process_artefact(name=name, pid=100)
        features = extractor.extract_all(artefact)
        return [float(features[name]) for name in ALL_FEATURE_NAMES]

    dataset = TrainingDataset(
        name="MalwareClassifier",
        feature_matrix=[
            _row("mimikatz.exe"),
            _row("notepad.exe"),
            _row("cmd.exe"),
            _row("explorer.exe"),
        ],
        labels=[1, 0, 1, 0],
        feature_names=list(ALL_FEATURE_NAMES),
        train_indices=[0, 1, 2],
        val_indices=[3],
        test_indices=[3],
        class_distribution={"0": 2, "1": 2},
        total_samples=4,
    )

    settings = MLSettings(
        models_dir=tmp_path / "models",
        experiments_dir=tmp_path / "experiments",
        random_seed=42,
        cross_validation_folds=2,
    )
    trainer = ModelTrainer(ExperimentTracker(settings.experiments_dir), settings)
    registry = ModelRegistry(settings.models_dir)
    trained = await trainer.train(MalwareClassifier, dataset)
    registry.register(trained)

    predictor = MLPredictor(registry, extractor)
    scoring_engine = ScoringEngine(ml_predictor=predictor)
    assert scoring_engine.ml_enabled()

    ml_score = await scoring_engine.ml_score_for(_process_artefact(name="mimikatz.exe"))
    assert ml_score is not None
    assert 0.0 <= ml_score <= 1.0

    combined = scoring_engine.combine_scores(
        rule_score=1.0,
        llm_score=0.0,
        ml_score=0.0,
    )
    assert combined == pytest.approx(_RULE_WEIGHT_ML)
    assert _RULE_WEIGHT_ML + _LLM_WEIGHT_ML + _ML_WEIGHT == pytest.approx(1.0)

    rule_engine = RuleBasedTriageEngine(scoring_engine)
    ranked = rule_engine.evaluate(_artefact_set(), [], relationship_map=MagicMock(edges=[], clusters=[]))
    assert ranked
    assert ranked[0].relevance_score >= 0.0


@pytest.mark.asyncio
async def test_pipeline_falls_back_completely(
    tmp_path: Path,
    sample_artefact_set: ArtefactSet,
    sample_ground_truth,
) -> None:
    """Without Ollama, knowledge, or ML the rule-based pipeline still triages and benchmarks."""
    from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
    from dfat.core.models.report import JSONReport, NarrativeReport
    from dfat.forensic_engine.processing.ioc_detector import IOCDetector
    from dfat.forensic_engine.triage.aggregator import TriageAggregator
    from dfat.pipeline.progress_tracker import ProgressTracker
    from dfat.settings import DFATSettings

    llm = MagicMock()
    llm.is_available = MagicMock(return_value=False)
    fallback = RuleBasedAnalyzer()
    scoring_engine = ScoringEngine(ml_predictor=None)
    rule_engine = RuleBasedTriageEngine(scoring_engine)
    audit = AsyncMock()
    audit.log_action = AsyncMock()

    triage_stage = TriageStage(
        ioc_detector=IOCDetector(),
        scoring_engine=scoring_engine,
        rule_engine=rule_engine,
        triage_aggregator=TriageAggregator(),
        llm_analyzer=llm,
        fallback_analyzer=fallback,
        progress_tracker=ProgressTracker(),
        audit_service=audit,
        settings=DFATSettings(),
    )

    job = PipelineJob(
        evidence_id=sample_artefact_set.evidence_id,
        case_id="case-fallback",
        user_id="user-fallback",
        mode="full",
        use_fallback_analyzer=True,
    )
    context = PipelineContext(job=job, artefact_set=sample_artefact_set)

    result: StageResult = await triage_stage.execute(context)

    assert result.success is True
    assert context.ranked_artefacts
    assert context.metadata.get("triage_source") in {
        "rule_engine+fallback_summary",
        "fallback_analyzer",
        "rule_engine",
    }
    assert context.metadata.get("ioc_count", 0) >= 0

    report = JSONReport(
        evidence_id=sample_artefact_set.evidence_id,
        artefact_data=[
            {
                "artefact_id": item.artefact_id,
                "category": item.category.value,
                "suspicion_level": item.suspicion_level.value,
                "relevance_score": item.relevance_score,
            }
            for item in context.ranked_artefacts
        ],
        integrity_hash="c" * 64,
    )
    narrative = NarrativeReport(
        evidence_id=sample_artefact_set.evidence_id,
        summary_text=context.summary_text or "Rule-based fallback summary",
        llm_model_used="RuleBasedFallback",
    )
    assert report.artefact_data
    assert narrative.summary_text

    from datetime import UTC, datetime

    from dfat.evaluation.benchmark.comparator import BenchmarkComparator
    from dfat.evaluation.benchmark.cfreds_handler import CFReDSHandler
    from dfat.evaluation.benchmark.dfrws_handler import DFRWSHandler
    from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader

    recovered = ArtefactSet(
        evidence_id=sample_artefact_set.evidence_id,
        artefacts=[
            Artefact(
                category=item.category,
                source_evidence_id=sample_artefact_set.evidence_id,
                raw_data=dict(item.raw_data),
            )
            for item in context.ranked_artefacts
        ],
        categories_present=sample_artefact_set.categories_present,
    )
    loader = GroundTruthLoader(
        tmp_path,
        DFRWSHandler(tmp_path),
        CFReDSHandler(tmp_path),
    )
    comparator = BenchmarkComparator(
        metrics=MetricsCalculator(),
        ground_truth_loader=loader,
        audit_service=AsyncMock(),
        benchmark_repo=AsyncMock(),
        thresholds={"precision_min": 0.0, "recall_min": 0.0, "f1_min": 0.0},
    )
    start = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
    end = datetime(2024, 1, 15, 12, 0, 30, tzinfo=UTC)
    benchmark = await comparator.compare(
        recovered=recovered,
        ground_truth=sample_ground_truth,
        pipeline_start=start,
        pipeline_end=end,
        dataset_name=sample_ground_truth.dataset_name,
        persist=False,
        audit=False,
    )
    assert 0.0 <= benchmark.precision <= 1.0
    assert 0.0 <= benchmark.recall <= 1.0
    assert 0.0 <= benchmark.f1_score <= 1.0
    assert benchmark.time_to_triage_seconds == pytest.approx(30.0)
