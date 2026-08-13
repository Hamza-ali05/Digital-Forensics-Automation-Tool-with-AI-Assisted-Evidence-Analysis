"""Secure, anonymised collection and storage of usability questionnaire responses."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from dfat.core.enums import PipelineStage
from dfat.core.models.evaluation import UsabilityResponse
from dfat.database.repositories.evaluation_repo import SQLAlchemyUsabilityRepository
from dfat.evaluation.usability.questionnaire import QuestionnaireInstrument
from dfat.services.audit_service import AuditService

# Simple PII redaction patterns for free-text export (ethics / anonymity).
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)
_NAME_INTRO_PATTERN = re.compile(
    r"\b(?:my name is|i am|i'm|signed,?|regards,?|thanks,?)\s+"
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b",
    re.IGNORECASE,
)
_PROPER_NAME_PATTERN = re.compile(r"\b[A-Z][a-z]{1,30}\s+[A-Z][a-z]{1,30}\b")


class ResponseCollector:
    """Collect and store anonymised usability questionnaire responses."""

    def __init__(
        self,
        questionnaire: QuestionnaireInstrument,
        usability_repo: SQLAlchemyUsabilityRepository,
        audit_service: AuditService,
    ) -> None:
        """Initialise the response collector.

        Args:
            questionnaire: Ethics-locked questionnaire instrument.
            usability_repo: Persistence repository for usability responses.
            audit_service: Dual-write forensic audit service.
        """
        self._questionnaire = questionnaire
        self._usability_repo = usability_repo
        self._audit_service = audit_service

    async def collect_response(
        self,
        ratings: dict[str, int],
        free_text: Optional[str] = None,
    ) -> str:
        """Collect, persist, and audit an anonymised questionnaire response.

        Steps:
            1. Generate anonymous ``participant_id``.
            2. Create ``UsabilityResponse`` via the questionnaire instrument.
            3. Save to ``usability_repo``.
            4. Log ``USABILITY_RESPONSE_COLLECTED`` (participant id only — no content).
            5. Return ``participant_id``.

        Args:
            ratings: Likert ratings keyed by question id or dimension.
            free_text: Optional free-text feedback (Q6).

        Returns:
            Anonymised UUID participant identifier.
        """
        participant_id = self._questionnaire.generate_participant_id()
        response = self._questionnaire.create_response(
            participant_id=participant_id,
            ratings=ratings,
            free_text=free_text,
        )
        await self._usability_repo.save(response)
        await self._audit_service.log_action(
            stage=PipelineStage.EVALUATION,
            action="USABILITY_RESPONSE_COLLECTED",
            evidence_id="usability",
            details={
                "participant_id": participant_id,
                "instrument_version": self._questionnaire.INSTRUMENT_VERSION,
                # Intentionally omit ratings and free_text to preserve anonymity.
            },
        )
        return participant_id

    async def get_response_count(self) -> int:
        """Return the number of stored usability responses."""
        return await self._usability_repo.count_responses()

    async def get_all_responses(self) -> list[UsabilityResponse]:
        """Return all stored anonymised usability responses."""
        return await self._usability_repo.get_all_responses()

    async def export_responses_anonymised(self, format: str = "json") -> str:
        """Export all responses with redacted free-text PII.

        Args:
            format: Export format (``json`` only currently).

        Returns:
            Serialised anonymised response payload.

        Raises:
            ValueError: If the format is unsupported.
        """
        normalised = format.strip().lower()
        if normalised != "json":
            raise ValueError(f"Unsupported usability export format: {format}")

        responses = await self.get_all_responses()
        payload: list[dict[str, Any]] = []
        for response in responses:
            free_text = response.free_text_feedback
            payload.append(
                {
                    "participant_id": response.participant_id,
                    "usefulness_rating": response.usefulness_rating,
                    "accuracy_rating": response.accuracy_rating,
                    "clarity_rating": response.clarity_rating,
                    "free_text_feedback": (
                        self._redact_identifying_text(free_text)
                        if free_text
                        else None
                    ),
                    "submitted_at": response.submitted_at.isoformat(),
                }
            )
        return json.dumps(
            {
                "instrument_version": self._questionnaire.INSTRUMENT_VERSION,
                "response_count": len(payload),
                "responses": payload,
            },
            indent=2,
        )

    async def delete_all_responses(self) -> int:
        """Destroy all stored usability responses (ethics data destruction).

        Logs ``USABILITY_DATA_DESTROYED`` with the deleted count only.

        Returns:
            Number of responses deleted.
        """
        deleted = await self._usability_repo.delete_all_responses()
        await self._audit_service.log_action(
            stage=PipelineStage.EVALUATION,
            action="USABILITY_DATA_DESTROYED",
            evidence_id="usability",
            details={"deleted_count": deleted},
        )
        return deleted

    @staticmethod
    def _redact_identifying_text(text: str) -> str:
        """Remove email addresses and simple name patterns from free text.

        Args:
            text: Raw free-text feedback.

        Returns:
            Redacted text safe for anonymised export.
        """
        redacted = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
        redacted = _NAME_INTRO_PATTERN.sub("[REDACTED_NAME]", redacted)
        redacted = _PROPER_NAME_PATTERN.sub("[REDACTED_NAME]", redacted)
        return redacted
