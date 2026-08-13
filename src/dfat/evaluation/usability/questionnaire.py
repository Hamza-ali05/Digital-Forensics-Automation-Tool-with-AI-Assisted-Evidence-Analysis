"""Structured usability questionnaire instrument (ethics-locked).

WARNING: Questions, scales, and dimensions must not be changed after ethics
approval. This instrument supports RQ5 and comparison to Tobin et al. (2021)
usefulness percentage (74%).
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import uuid4

from dfat.core.models.evaluation import UsabilityResponse


class QuestionnaireInstrument:
    """Structured usability questionnaire for simulated investigators.

    FROZEN after ethics approval — questions must not change.
    Produces a usefulness percentage comparable to Tobin et al. (2021) 74%.
    """

    QUESTIONS: list[dict[str, str]] = [
        {
            "id": "Q1",
            "text": (
                "How useful was the tool's output for identifying key evidence?"
            ),
            "scale": "1-5",
            "dimension": "usefulness",
            "type": "likert",
        },
        {
            "id": "Q2",
            "text": (
                "How accurate were the identified artefacts compared to your "
                "manual analysis?"
            ),
            "scale": "1-5",
            "dimension": "accuracy",
            "type": "likert",
        },
        {
            "id": "Q3",
            "text": "How clear and readable was the investigative summary?",
            "scale": "1-5",
            "dimension": "clarity",
            "type": "likert",
        },
        {
            "id": "Q4",
            "text": (
                "Would you use this tool in a real forensic investigation?"
            ),
            "scale": "1-5",
            "dimension": "usefulness",
            "type": "likert",
        },
        {
            "id": "Q5",
            "text": (
                "How does the tool's output compare to manual triage methods?"
            ),
            "scale": "1-5",
            "dimension": "comparative",
            "type": "likert",
        },
        {
            "id": "Q6",
            "text": (
                "Please provide any additional feedback on the tool's "
                "strengths or weaknesses."
            ),
            "scale": "free_text",
            "dimension": "qualitative",
            "type": "open",
        },
    ]
    INSTRUMENT_VERSION = "1.0.0"

    def generate_participant_id(self) -> str:
        """Return an anonymised UUID-based participant identifier.

        Returns:
            Opaque participant ID with no personally identifiable information.
        """
        return str(uuid4())

    def create_response(
        self,
        participant_id: str,
        ratings: dict[str, int],
        free_text: Optional[str] = None,
    ) -> UsabilityResponse:
        """Create a validated usability response.

        ``ratings`` may be keyed by question id (``Q1``–``Q5``) or by
        dimension name (``usefulness``, ``accuracy``, ``clarity``, and
        optionally ``comparative``). All Likert values must be integers 1–5.

        Usefulness on ``UsabilityResponse`` is the rounded mean of Q1 and Q4
        when question ids are supplied (both map to the usefulness dimension).

        Args:
            participant_id: Anonymised participant identifier.
            ratings: Likert ratings keyed by question id or dimension.
            free_text: Optional free-text feedback (Q6).

        Returns:
            Validated ``UsabilityResponse``.

        Raises:
            ValueError: If any Likert rating is missing or outside 1–5.
        """
        likert_by_id = {
            question["id"]: question
            for question in self.QUESTIONS
            if question["type"] == "likert"
        }

        if any(key in likert_by_id for key in ratings):
            resolved: dict[str, int] = {}
            for question_id, question in likert_by_id.items():
                resolved[question_id] = self._require_rating(
                    ratings,
                    question_id,
                    label=f"{question_id} ({question['dimension']})",
                )
            q1 = resolved["Q1"]
            q4 = resolved["Q4"]
            usefulness = round((q1 + q4) / 2)
            usefulness = min(5, max(1, int(usefulness)))
            accuracy = resolved["Q2"]
            clarity = resolved["Q3"]
            comparative = resolved["Q5"]
            return UsabilityResponse(
                participant_id=participant_id,
                usefulness_rating=usefulness,
                accuracy_rating=accuracy,
                clarity_rating=clarity,
                q1_rating=q1,
                q4_rating=q4,
                comparative_rating=comparative,
                free_text_feedback=free_text,
            )

        usefulness = self._require_rating(ratings, "usefulness")
        accuracy = self._require_rating(ratings, "accuracy")
        clarity = self._require_rating(ratings, "clarity")
        comparative = None
        if "comparative" in ratings:
            comparative = self._require_rating(ratings, "comparative")
        return UsabilityResponse(
            participant_id=participant_id,
            usefulness_rating=usefulness,
            accuracy_rating=accuracy,
            clarity_rating=clarity,
            comparative_rating=comparative,
            free_text_feedback=free_text,
        )

    def export_questionnaire(self, format: str = "json") -> str:
        """Export the questionnaire instrument definition.

        Args:
            format: ``json`` (default) or ``text`` / ``plain``.

        Returns:
            Serialised questionnaire definition.

        Raises:
            ValueError: If the format is unsupported.
        """
        normalised = format.strip().lower()
        if normalised == "json":
            return json.dumps(
                {
                    "instrument_version": self.INSTRUMENT_VERSION,
                    "tobin_et_al_2021_benchmark_percent": 74.0,
                    "questions": self.QUESTIONS,
                },
                indent=2,
            )
        if normalised in {"text", "plain", "plain_text"}:
            return self.export_for_print()
        raise ValueError(f"Unsupported questionnaire export format: {format}")

    def export_for_print(self) -> str:
        """Export a plain-text instrument suitable for paper administration.

        Returns:
            Human-readable questionnaire text.
        """
        lines = [
            "DFAT Usability Questionnaire",
            f"Instrument version: {self.INSTRUMENT_VERSION}",
            "Scale (Likert): 1 = strongly disagree / very poor, "
            "5 = strongly agree / excellent",
            "",
        ]
        for question in self.QUESTIONS:
            lines.append(
                f"{question['id']} [{question['dimension']} | "
                f"{question['scale']} | {question['type']}]"
            )
            lines.append(question["text"])
            if question["type"] == "likert":
                lines.append("Response: 1   2   3   4   5")
            else:
                lines.append("Response: ________________________________")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def get_dimension_questions(self, dimension: str) -> list[dict[str, Any]]:
        """Return questions belonging to a specific dimension.

        Args:
            dimension: Dimension name (e.g. ``usefulness``, ``accuracy``).

        Returns:
            Matching question definition dictionaries (possibly empty).
        """
        target = dimension.strip().lower()
        return [
            dict(question)
            for question in self.QUESTIONS
            if question["dimension"].lower() == target
        ]

    @staticmethod
    def _require_rating(
        ratings: dict[str, int],
        key: str,
        *,
        label: Optional[str] = None,
    ) -> int:
        """Validate and return a 1–5 Likert rating.

        Raises:
            ValueError: If the rating is missing or outside 1–5.
        """
        display = label or key
        if key not in ratings:
            raise ValueError(f"Missing required rating: {display}")
        value = ratings[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                f"Rating '{display}' must be an integer between 1 and 5"
            )
        if value < 1 or value > 5:
            raise ValueError(
                f"Rating '{display}' out of range (expected 1–5): {value}"
            )
        return value
