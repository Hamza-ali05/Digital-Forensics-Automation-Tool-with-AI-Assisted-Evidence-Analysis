"""Unit tests for usability questionnaire instrument."""

from __future__ import annotations

import pytest

from dfat.core.exceptions import EvaluationError
from dfat.evaluation.usability.questionnaire import QuestionnaireInstrument


def test_create_response_accepts_valid_ratings() -> None:
    """Verify valid 1–5 ratings produce a UsabilityResponse."""
    # Arrange
    instrument = QuestionnaireInstrument()
    participant = instrument.generate_participant_id()

    # Act
    response = instrument.create_response(
        participant,
        {"usefulness": 4, "accuracy": 5, "clarity": 3},
        free_text="Clear output",
    )

    # Assert
    assert response.usefulness_rating == 4
    assert response.accuracy_rating == 5
    assert response.clarity_rating == 3
    assert response.free_text_feedback == "Clear output"


def test_create_response_rejects_out_of_range_rating() -> None:
    """Verify ratings outside 1–5 raise EvaluationError."""
    # Arrange
    instrument = QuestionnaireInstrument()

    # Act / Assert
    with pytest.raises(EvaluationError):
        instrument.create_response(
            "participant-1",
            {"usefulness": 6, "accuracy": 5, "clarity": 3},
        )


def test_create_response_rejects_missing_rating_key() -> None:
    """Verify missing required rating keys raise EvaluationError."""
    # Arrange
    instrument = QuestionnaireInstrument()

    # Act / Assert
    with pytest.raises(EvaluationError):
        instrument.create_response(
            "participant-1",
            {"usefulness": 4, "accuracy": 5},
        )


def test_export_questionnaire_json_contains_five_questions() -> None:
    """Verify JSON export includes the five ethics-locked questions."""
    # Arrange
    instrument = QuestionnaireInstrument()

    # Act
    payload = instrument.export_questionnaire("json")

    # Assert
    assert "Q1" in payload
    assert "Q5" in payload
