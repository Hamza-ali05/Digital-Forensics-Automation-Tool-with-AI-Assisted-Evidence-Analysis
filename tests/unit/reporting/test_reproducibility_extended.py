"""Extended report reproducibility and schema-validation tests."""

from __future__ import annotations

from copy import deepcopy

from dfat.reporting.reproducibility import ReproducibilityVerifier
from dfat.reporting.schema import ReportSchemaValidator


def _artefacts() -> list[dict]:
    return [
        {
            "artefact_id": "art-2",
            "category": "event_log",
            "suspicion_level": "low",
            "raw_data": {"b": 2, "a": 1},
        },
        {
            "artefact_id": "art-1",
            "category": "event_log",
            "suspicion_level": "high",
            "raw_data": {"z": 3},
        },
        {
            "artefact_id": "art-3",
            "category": "registry_key",
            "suspicion_level": "low",
            "raw_data": {},
        },
    ]


def test_metadata_differences_do_not_change_reproducibility_hash() -> None:
    # Arrange
    artefacts = _artefacts()
    report_a = {
        "report_id": "run-a",
        "generated_at": "2024-01-01T00:00:00Z",
        "artefacts": artefacts,
    }
    report_b = {
        "report_id": "run-b",
        "generated_at": "2025-01-01T00:00:00Z",
        "artefacts": deepcopy(artefacts),
    }

    # Act
    result = ReproducibilityVerifier().compare_reports(report_a, report_b)

    # Assert
    assert result.hash_a == result.hash_b
    assert result.is_reproducible is True


def test_duplicate_categories_have_deterministic_hash_and_distribution() -> None:
    # Arrange
    report = {"artefacts": _artefacts()}
    verifier = ReproducibilityVerifier()

    # Act
    first = verifier.compare_reports(report, deepcopy(report))
    second = verifier.compare_reports(report, deepcopy(report))

    # Assert
    assert first.hash_a == second.hash_a
    assert first.category_distribution_match is True
    assert first.is_reproducible is second.is_reproducible is True


def test_schema_validator_returns_invalid_result_for_malformed_data() -> None:
    # Arrange
    malformed = {
        "schema_version": 123,
        "report_id": None,
        "artefacts": "not-an-array",
    }

    # Act
    result = ReportSchemaValidator().validate(malformed)

    # Assert
    assert result.is_valid is False
    assert result.errors
