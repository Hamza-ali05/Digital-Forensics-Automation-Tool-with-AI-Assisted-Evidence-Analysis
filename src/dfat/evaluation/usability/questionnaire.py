"""Structured usability questionnaire instrument (ethics-locked).

WARNING: Questions, scales, and dimensions must not be changed after ethics
approval. This instrument supports RQ5 and comparison to Tobin et al. (2021).
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import uuid4

from dfat.core.exceptions import EvaluationError
from dfat.core.models.evaluation import UsabilityResponse


class QuestionnaireInstrument:
    """Anonymised Likert/free-text usability questionnaire definition."""

    QUESTIONS: list[dict[str, str]] = [
        {
            "id": "Q1",
            "text": (
                "How useful was the tool's output for identifying key evidence?"
            ),
            "scale": "1-5 Likert",
            "dimension": "usefulness",
        },
        {
            "id": "Q2",
            "text": (
                "How accurate were the identified artefacts compared to your "
                "manual analysis?"
            ),
            "scale": "1-5 Likert",
            "dimension": "accuracy",
        },
        {
            "id": "Q3",
            "text": "How clear and readable was the investigative summary?",
            "scale": "1-5 Likert",
            "dimension": "clarity",
        },
        {
            "id": "Q4",
            "text": "Would you use this tool in a real investigation?",
            "scale": "1-5 Likert",
            "dimension": "usefulness",
        },
        {
            "id": "Q5",
            "text": "Please provide any additional feedback on the tool.",
            "scale": "free_text",
            "dimension": "qualitative",
        },
    ]

    def generate_participant_id(self) -> str:
        """Return an anonymised UUID-based participant identifier.

        Returns:
            Opaque participant ID with no personally identifiable information.
        """
        return f"participant-{uuid4()}"

    def create_response(
        self,
        participant_id: str,
        ratings: dict[str, int],
        free_text: Optional[str] = None,
    ) -> UsabilityResponse:
        """Create a validated usability response.

        Args:
            participant_id: Anonymised participant identifier.
            ratings: Mapping containing ``usefulness``, ``accuracy``, and
                ``clarity`` integer ratings (1–5).
            free_text: Optional free-text feedback (Q5).

        Returns:
            Validated ``UsabilityResponse``.

        Raises:
            EvaluationError: If any rating is missing or outside 1–5.
        """
        usefulness = self._require_rating(ratings, "usefulness")
        accuracy = self._require_rating(ratings, "accuracy")
        clarity = self._require_rating(ratings, "clarity")
        return UsabilityResponse(
            participant_id=participant_id,
            usefulness_rating=usefulness,
            accuracy_rating=accuracy,
            clarity_rating=clarity,
            free_text_feedback=free_text,
        )

    def export_questionnaire(self, format: str = "json") -> str:
        """Export the questionnaire instrument definition.

        Args:
            format: ``json`` or ``text``.

        Returns:
            Serialised questionnaire definition.

        Raises:
            EvaluationError: If the format is unsupported.
        """
        normalised = format.strip().lower()
        if normalised == "json":
            return json.dumps({"questions": self.QUESTIONS}, indent=2)
        if normalised in {"text", "plain", "plain_text"}:
            lines = ["DFAT Usability Questionnaire", ""]
            for question in self.QUESTIONS:
                lines.append(
                    f"{question['id']} [{question['dimension']} | {question['scale']}]"
                )
                lines.append(question["text"])
                lines.append("")
            return "\n".join(lines).rstrip() + "\n"
        raise EvaluationError(
            f"Unsupported questionnaire export format: {format}",
            context={"format": format},
        )

    @staticmethod
    def _require_rating(ratings: dict[str, int], key: str) -> int:
        """Validate and return a 1–5 Likert rating."""
        if key not in ratings:
            raise EvaluationError(
                f"Missing required rating: {key}",
                context={"ratings": dict(ratings)},
            )
        value = ratings[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise EvaluationError(
                f"Rating '{key}' must be an integer between 1 and 5",
                context={"value": value},
            )
        if value < 1 or value > 5:
            raise EvaluationError(
                f"Rating '{key}' out of range (expected 1–5): {value}",
                context={"value": value},
            )
        return value
