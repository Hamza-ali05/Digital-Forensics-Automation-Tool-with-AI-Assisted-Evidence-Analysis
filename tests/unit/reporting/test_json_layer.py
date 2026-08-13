"""Unit tests for structured JSON report export (Prompt 6.2)."""

from __future__ import annotations

import pytest

from dfat.core.enums import ArtefactCategory, HashAlgorithm, SuspicionLevel
from dfat.core.exceptions import JSONSchemaValidationError
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.reporting.json_layer import StructuredJSONExporter
from dfat.reporting.schema import ReportSchemaValidator


def _exporter() -> StructuredJSONExporter:
    """Build exporter using the packaged report schema validator."""
    return StructuredJSONExporter(
        schema_validator=ReportSchemaValidator(),
        hash_algorithm=HashAlgorithm.SHA256,
    )


def _timings() -> dict[str, float]:
    """Return canonical *_seconds stage timings."""
    return {
        "acquisition_seconds": 1.0,
        "parsing_seconds": 1.0,
        "triage_seconds": 1.0,
        "reporting_seconds": 0.5,
    }


def test_export_produces_integrity_hash(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify export produces a non-empty integrity hash."""
    exporter = _exporter()
    report = exporter.export(
        sample_artefact_set,
        sample_ranked_artefacts,
        sample_case_metadata,
        _timings(),
        ai_metadata={"analysis_mode": "rule_based"},
        evidence_hash="e" * 64,
    )
    assert report.integrity_hash
    assert len(report.integrity_hash) == 64


def test_export_hash_is_deterministic_for_same_artefacts(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify identical artefact inputs yield identical integrity hashes."""
    exporter = _exporter()
    first = exporter.export(
        sample_artefact_set,
        sample_ranked_artefacts,
        sample_case_metadata,
        _timings(),
        ai_metadata={},
        evidence_hash="abc",
    )
    second = exporter.export(
        sample_artefact_set,
        sample_ranked_artefacts,
        sample_case_metadata,
        {
            "acquisition_s": 9.0,
            "parsing_s": 9.0,
            "triage_s": 9.0,
            "reporting_s": 9.0,
        },
        ai_metadata={"model_used": "other"},
        evidence_hash="different-evidence-hash",
    )
    assert first.integrity_hash == second.integrity_hash
    assert first.report_id != second.report_id


def test_export_sorts_artefacts_by_category_then_id(
    sample_artefact_set: ArtefactSet,
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify artefact_data is sorted by (category, artefact_id)."""
    ranked = [
        RankedArtefact(
            artefact_id="z-proc",
            category=ArtefactCategory.RUNNING_PROCESS,
            source_evidence_id=sample_artefact_set.evidence_id,
            raw_data={"name": "a.exe"},
            suspicion_level=SuspicionLevel.HIGH,
            relevance_score=0.8,
            classification_reasoning="proc",
        ),
        RankedArtefact(
            artefact_id="a-browser",
            category=ArtefactCategory.BROWSER_HISTORY,
            source_evidence_id=sample_artefact_set.evidence_id,
            raw_data={"url": "http://example"},
            suspicion_level=SuspicionLevel.LOW,
            relevance_score=0.2,
            classification_reasoning="browser",
        ),
        RankedArtefact(
            artefact_id="m-browser",
            category=ArtefactCategory.BROWSER_HISTORY,
            source_evidence_id=sample_artefact_set.evidence_id,
            raw_data={"url": "http://other"},
            suspicion_level=SuspicionLevel.MEDIUM,
            relevance_score=0.4,
            classification_reasoning="browser",
        ),
    ]
    report = _exporter().export(
        sample_artefact_set,
        ranked,
        sample_case_metadata,
        _timings(),
    )
    ids = [row["artefact_id"] for row in report.artefact_data]
    categories = [row["category"] for row in report.artefact_data]
    assert categories == [
        "browser_history",
        "browser_history",
        "running_process",
    ]
    assert ids == ["a-browser", "m-browser", "z-proc"]


def test_export_summary_statistics_include_zero_counts(
    sample_artefact_set: ArtefactSet,
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify summary stats count every category/suspicion with zeros."""
    ranked = [
        RankedArtefact(
            artefact_id="inj-1",
            category=ArtefactCategory.INJECTED_CODE,
            source_evidence_id=sample_artefact_set.evidence_id,
            raw_data={"pid": 1},
            suspicion_level=SuspicionLevel.CRITICAL,
            relevance_score=0.99,
            classification_reasoning="RWX",
        )
    ]
    exporter = _exporter()
    # Recompute summary via private helper to assert shape (export validates).
    stats = exporter._compute_summary_statistics(ranked)
    assert stats["total_artefacts"] == 1
    assert stats["by_category"]["injected_code"] == 1
    assert stats["by_category"]["browser_history"] == 0
    assert stats["by_suspicion_level"]["critical"] == 1
    assert stats["by_suspicion_level"]["informational"] == 0
    assert set(stats["by_category"]) == {c.value for c in ArtefactCategory}
    assert set(stats["by_suspicion_level"]) == {s.value for s in SuspicionLevel}

    report = exporter.export(
        sample_artefact_set,
        ranked,
        sample_case_metadata,
        _timings(),
        evidence_hash="",
    )
    assert len(report.artefact_data) == 1


def test_export_document_validates_against_schema(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify a successful export implies a schema-valid document."""
    exporter = _exporter()
    report = exporter.export(
        sample_artefact_set,
        sample_ranked_artefacts,
        sample_case_metadata,
        _timings(),
        ai_metadata={
            "model_used": "none",
            "analysis_mode": "rule_based",
            "confidence_score": 0.0,
            "prompt_version": "1.0.0",
            "disclaimer": "Advisory.",
        },
        evidence_hash="f" * 64,
    )
    document = {
        "schema_version": report.schema_version,
        "report_id": report.report_id,
        "evidence_id": report.evidence_id,
        "case_metadata": {
            "case_id": sample_case_metadata.case_id,
            "case_name": sample_case_metadata.case_name,
            "investigator": sample_case_metadata.investigator,
        },
        "generated_at": report.generated_at.isoformat(),
        "integrity_hash": report.integrity_hash,
        "pipeline_stage_timings": _timings(),
        "artefacts": report.artefact_data,
        "summary_statistics": exporter._compute_summary_statistics(
            sample_ranked_artefacts
        ),
        "ai_metadata": {
            "model_used": "none",
            "analysis_mode": "rule_based",
            "confidence_score": 0.0,
            "prompt_version": "1.0.0",
            "disclaimer": "Advisory.",
        },
        "reproducibility": {
            "artefact_data_hash": report.integrity_hash,
            "input_evidence_hash": "f" * 64,
            "tool_version": "0.0.0",
            "schema_version": report.schema_version,
        },
    }
    result = ReportSchemaValidator().validate(document)
    assert result.is_valid, result.errors


def test_validate_against_schema_raises_on_invalid() -> None:
    """Verify exporter raises JSONSchemaValidationError for invalid docs."""
    exporter = _exporter()
    with pytest.raises(JSONSchemaValidationError):
        exporter.validate_against_schema({"schema_version": "1.0.0"})


def test_export_artefact_data_matches_ranked_count(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify exported artefact_data length matches ranked artefacts."""
    report = _exporter().export(
        sample_artefact_set,
        sample_ranked_artefacts,
        sample_case_metadata,
        {"acquisition_s": 0.1, "parsing_s": 0.1, "triage_s": 0.1, "reporting_s": 0.1},
    )
    assert len(report.artefact_data) == len(sample_ranked_artefacts)


# Prompt 6.20 named coverage aliases / extensions
test_export_deterministic_hash = test_export_hash_is_deterministic_for_same_artefacts
test_artefacts_sorted_deterministically = test_export_sorts_artefacts_by_category_then_id
test_summary_statistics_correct = test_export_summary_statistics_include_zero_counts
test_validates_against_schema = test_export_document_validates_against_schema


def test_export_different_input_different_hash(
    sample_artefact_set: ArtefactSet,
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify different artefact payloads produce different integrity hashes."""
    exporter = _exporter()
    first = exporter.export(
        sample_artefact_set,
        sample_ranked_artefacts,
        sample_case_metadata,
        _timings(),
    )
    altered = [
        RankedArtefact(
            **{**item.model_dump(), "relevance_score": round(item.relevance_score * 0.5, 4)}
        )
        for item in sample_ranked_artefacts
    ]
    second = exporter.export(
        sample_artefact_set,
        altered,
        sample_case_metadata,
        _timings(),
    )
    assert first.integrity_hash != second.integrity_hash

