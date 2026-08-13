"""Unit tests for usability questionnaire instrument (Prompt 6.16)."""

from __future__ import annotations

import json
import re
from uuid import UUID

import pytest

from dfat.evaluation.usability.questionnaire import QuestionnaireInstrument


def test_instrument_has_6_questions() -> None:
    """Verify ethics-locked instrument has 5 Likert + 1 open question."""
    instrument = QuestionnaireInstrument()
    assert len(instrument.QUESTIONS) == 6
    likert = [q for q in instrument.QUESTIONS if q["type"] == "likert"]
    open_qs = [q for q in instrument.QUESTIONS if q["type"] == "open"]
    assert len(likert) == 5
    assert len(open_qs) == 1
    assert instrument.INSTRUMENT_VERSION == "1.0.0"


test_instrument_has_six_questions_five_likert_one_open = test_instrument_has_6_questions


def test_ratings_validated_1_to_5() -> None:
    """Verify valid boundary ratings 1 and 5 are accepted."""
    instrument = QuestionnaireInstrument()
    low = instrument.create_response(
        instrument.generate_participant_id(),
        {"usefulness": 1, "accuracy": 1, "clarity": 1},
    )
    high = instrument.create_response(
        instrument.generate_participant_id(),
        {"usefulness": 5, "accuracy": 5, "clarity": 5},
    )
    assert low.usefulness_rating == 1
    assert high.clarity_rating == 5



def test_participant_id_is_uuid() -> None:
    """Verify participant IDs are anonymised UUID strings."""
    instrument = QuestionnaireInstrument()
    first = instrument.generate_participant_id()
    second = instrument.generate_participant_id()
    UUID(first)  # raises if not a valid UUID
    UUID(second)
    assert first != second
    assert not re.search(r"(name|email|@)", first, flags=re.IGNORECASE)


test_generate_participant_id_is_anonymised_uuid = test_participant_id_is_uuid



def test_create_response_accepts_valid_dimension_ratings() -> None:
    """Verify valid 1–5 dimension ratings produce a UsabilityResponse."""
    instrument = QuestionnaireInstrument()
    participant = instrument.generate_participant_id()

    response = instrument.create_response(
        participant,
        {"usefulness": 4, "accuracy": 5, "clarity": 3},
        free_text="Clear output",
    )

    assert response.participant_id == participant
    assert response.usefulness_rating == 4
    assert response.accuracy_rating == 5
    assert response.clarity_rating == 3
    assert response.free_text_feedback == "Clear output"


def test_create_response_accepts_question_id_ratings() -> None:
    """Verify Q1–Q5 ratings map into UsabilityResponse fields."""
    instrument = QuestionnaireInstrument()
    response = instrument.create_response(
        instrument.generate_participant_id(),
        {"Q1": 5, "Q2": 4, "Q3": 3, "Q4": 3, "Q5": 4},
        free_text="Solid triage aid",
    )
    # usefulness = round((5 + 3) / 2) = 4
    assert response.usefulness_rating == 4
    assert response.accuracy_rating == 4
    assert response.clarity_rating == 3


def test_invalid_rating_raises_error() -> None:
    """Verify ratings outside 1–5 raise ValueError."""
    instrument = QuestionnaireInstrument()
    with pytest.raises(ValueError):
        instrument.create_response(
            "participant-1",
            {"usefulness": 6, "accuracy": 5, "clarity": 3},
        )


test_create_response_rejects_out_of_range_rating = test_invalid_rating_raises_error



def test_create_response_rejects_missing_rating_key() -> None:
    """Verify missing required rating keys raise ValueError."""
    instrument = QuestionnaireInstrument()
    with pytest.raises(ValueError):
        instrument.create_response(
            "participant-1",
            {"usefulness": 4, "accuracy": 5},
        )


def test_export_json_contains_all_questions() -> None:
    """Verify JSON export is valid and includes all six questions."""
    instrument = QuestionnaireInstrument()
    payload = instrument.export_questionnaire("json")
    parsed = json.loads(payload)
    assert parsed["instrument_version"] == "1.0.0"
    assert len(parsed["questions"]) == 6
    ids = [question["id"] for question in parsed["questions"]]
    assert ids == ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]


test_export_questionnaire_produces_valid_json = test_export_json_contains_all_questions



def test_export_for_print_includes_all_questions() -> None:
    """Verify printable export lists every question id."""
    text = QuestionnaireInstrument().export_for_print()
    for question_id in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6"):
        assert question_id in text
    assert "1.0.0" in text


def test_get_dimension_questions_filters_usefulness() -> None:
    """Verify dimension lookup returns Q1 and Q4 for usefulness."""
    questions = QuestionnaireInstrument().get_dimension_questions("usefulness")
    assert [question["id"] for question in questions] == ["Q1", "Q4"]
