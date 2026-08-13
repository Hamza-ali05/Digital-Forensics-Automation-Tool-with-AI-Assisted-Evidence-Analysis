"""Unit tests for report schema validation (Prompt 6.1)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest

from dfat.reporting.schema import (
    SCHEMA_REGISTRY,
    ReportSchemaValidator,
    get_latest_version,
    get_schema,
)
from dfat.reporting.schema.schema_versions import get_schema_path


def _conforming_report() -> dict:
    """Return a minimal document that satisfies schema 1.0.0."""
    return {
        "schema_version": "1.0.0",
        "report_id": str(uuid4()),
        "evidence_id": "ev-test-001",
        "case_metadata": {
            "case_id": "case-1",
            "case_name": "Test Case",
            "investigator": "Analyst",
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "integrity_hash": "a" * 64,
        "pipeline_stage_timings": {
            "acquisition_seconds": 1.0,
            "parsing_seconds": 2.0,
            "triage_seconds": 3.0,
            "reporting_seconds": 0.5,
        },
        "artefacts": [
            {
                "artefact_id": "art-1",
                "category": "injected_code",
                "source_path": None,
                "suspicion_level": "critical",
                "relevance_score": 0.95,
                "raw_data": {"pid": 1},
                "classification_reasoning": "RWX region",
                "metadata": {},
            }
        ],
        "summary_statistics": {
            "total_artefacts": 1,
            "by_category": {"injected_code": 1},
            "by_suspicion_level": {"critical": 1},
        },
        "ai_metadata": {
            "model_used": "none",
            "prompt_version": "1.0.0",
            "confidence_score": 0.0,
            "analysis_mode": "rule_based",
            "disclaimer": "Advisory only.",
        },
    }


def test_schema_parses_as_valid_json_schema_draft07() -> None:
    """Verify the packaged schema loads and constructs a Draft7Validator."""
    schema = get_schema("1.0.0")
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema.get("version") == "1.0.0" or schema["properties"]["schema_version"][
        "const"
    ] == "1.0.0"
    validator = jsonschema.Draft7Validator(schema)
    assert validator.is_valid(_conforming_report())


def test_validator_accepts_conforming_report() -> None:
    """Verify ReportSchemaValidator accepts a conforming document."""
    result = ReportSchemaValidator().validate(_conforming_report())
    assert result.is_valid is True
    assert result.errors == []
    assert result.schema_version == "1.0.0"


def test_validator_rejects_missing_required_fields() -> None:
    """Verify missing required fields produce validation errors."""
    document = _conforming_report()
    del document["ai_metadata"]
    del document["integrity_hash"]
    result = ReportSchemaValidator().validate(document)
    assert result.is_valid is False
    assert result.errors
    joined = " ".join(result.errors).lower()
    assert "ai_metadata" in joined or "integrity_hash" in joined


def test_schema_version_is_1_0_0() -> None:
    """Verify registry and validator report schema_version 1.0.0."""
    assert get_latest_version() == "1.0.0"
    assert "1.0.0" in SCHEMA_REGISTRY
    assert ReportSchemaValidator().get_schema_version() == "1.0.0"
    assert "ai_metadata" in ReportSchemaValidator().get_required_fields()
    path = get_schema_path("1.0.0")
    assert path.exists()
    assert path.name == "report_schema.json"


def test_templates_schema_mirrors_canonical() -> None:
    """Verify templates/report_schema.json matches the canonical schema file."""
    canonical = Path(__file__).resolve().parents[3] / "src/dfat/reporting/schema/report_schema.json"
    template = (
        Path(__file__).resolve().parents[3]
        / "src/dfat/reporting/templates/report_schema.json"
    )
    assert canonical.read_text(encoding="utf-8") == template.read_text(encoding="utf-8")

