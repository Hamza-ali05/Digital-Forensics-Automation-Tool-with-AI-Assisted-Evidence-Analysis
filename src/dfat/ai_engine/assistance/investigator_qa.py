"""Investigator natural-language Q&A grounded in forensic artefact evidence.

Answers must be based only on provided artefact data. Hallucination checks run
on every response (Scanlon et al., 2023).
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.llm.client import OllamaClient
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.ai_engine.preprocessing.truncator import TokenTruncator
from dfat.ai_engine.validation.hallucination_guard import (
    HallucinationGuard,
    HallucinationReport,
)
from dfat.core.enums import PipelineStage, SuspicionLevel
from dfat.core.models.artefact import ArtefactSet, RankedArtefact
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_ART_ID_RE = re.compile(r"\b(?:art|artefact)[-_][\w-]+\b", re.IGNORECASE)

_HIGH_PLUS = frozenset({SuspicionLevel.CRITICAL, SuspicionLevel.HIGH})


class ResponseCache(Protocol):
    """Minimal cache protocol for Q&A responses."""

    def get(self, key: str) -> Optional[Any]:
        """Return a cached value or ``None``."""

    def set(self, key: str, value: Any) -> None:
        """Store a value under ``key``."""


class QAResponse(BaseModel):
    """Grounded answer to an investigator question."""

    model_config = ConfigDict(frozen=False)

    answer: str
    confidence: float = 0.0
    referenced_artefact_ids: list[str] = Field(default_factory=list)
    hallucination_check: HallucinationReport
    model_used: str
    question: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InvestigatorQAAssistant:
    """Answer investigator questions using local LLM + artefact context."""

    def __init__(
        self,
        ollama_client: OllamaClient,
        templates: ForensicPromptTemplates,
        serializer: ArtefactSerializer,
        hallucination_guard: HallucinationGuard,
        response_cache: ResponseCache,
        audit_logger: ForensicAuditLogger,
        *,
        truncator: Optional[TokenTruncator] = None,
    ) -> None:
        """Initialise the Q&A assistant.

        Args:
            ollama_client: Low-level Ollama HTTP client.
            templates: Forensic prompt templates (includes QA).
            serializer: Artefact text serializer.
            hallucination_guard: Response hallucination detector.
            response_cache: Cache for identical Q&A prompts.
            audit_logger: Forensic audit logger (metadata only).
            truncator: Optional token truncator for context windows.
        """
        self._ollama = ollama_client
        self._templates = templates
        self._serializer = serializer
        self._guard = hallucination_guard
        self._cache = response_cache
        self._audit_logger = audit_logger
        self._truncator = truncator or TokenTruncator(max_tokens=6000)

    async def ask(
        self,
        question: str,
        artefact_set: ArtefactSet,
        ranked: Optional[list[RankedArtefact]] = None,
        conversation_history: Optional[list[dict[str, str]]] = None,
    ) -> QAResponse:
        """Answer a natural-language question grounded in artefact evidence.

        Args:
            question: Investigator question.
            artefact_set: Parsed artefacts available as context.
            ranked: Optional triage ranking to prioritise HIGH+ context.
            conversation_history: Optional prior ``role``/``content`` messages.

        Returns:
            ``QAResponse`` with answer, confidence, IDs, and hallucination report.
        """
        started = time.perf_counter()
        context_text = self._build_context(artefact_set, ranked)
        context_text = self._truncator.truncate(context_text, reserve_tokens=2000)
        prompt = self._templates.render(
            "qa",
            context_text=context_text,
            question=question,
        )

        cache_key = self._cache_key(question, context_text, conversation_history)
        cached = self._cache.get(cache_key)
        if isinstance(cached, QAResponse):
            return cached
        if isinstance(cached, dict):
            return QAResponse.model_validate(cached)

        model_used = "unknown"
        answer_text = ""
        try:
            if conversation_history:
                messages = self._build_chat_messages(
                    conversation_history,
                    context_text,
                    question,
                )
                response = await self._ollama.chat(messages)
            else:
                response = await self._ollama.generate(prompt)
            answer_text = response.text
            model_used = response.model or model_used
        except Exception as exc:  # noqa: BLE001 — soft failure
            logger.warning("Investigator Q&A LLM call failed: %s", exc)
            answer_text = (
                "Insufficient data to answer reliably: the local LLM is "
                "unavailable. Please consult the structured JSON artefact layer."
            )

        valid_ids = {item.artefact_id for item in artefact_set.artefacts}
        if ranked:
            valid_ids.update(item.artefact_id for item in ranked)
        guard = HallucinationGuard(
            valid_artefact_ids=valid_ids | set(getattr(self._guard, "_valid_ids", set())),
            valid_categories=set(getattr(self._guard, "_valid_categories", set())),
            valid_suspicion_levels=set(getattr(self._guard, "_valid_levels", set())),
            known_facts=set(getattr(self._guard, "_known_facts", set())),
        )
        report = guard.check_response(answer_text)
        referenced = self._extract_referenced_ids(answer_text, valid_ids)
        confidence = self._score_answer(answer_text, referenced, report)

        result = QAResponse(
            answer=report.clean_response or answer_text,
            confidence=confidence,
            referenced_artefact_ids=referenced,
            hallucination_check=report,
            model_used=model_used,
            question=question,
            timestamp=datetime.now(UTC),
        )
        self._cache.set(cache_key, result)

        duration_ms = (time.perf_counter() - started) * 1000.0
        self._audit_logger.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="LLM_QA",
            evidence_id=artefact_set.evidence_id,
            details={
                "question_chars": len(question),
                "context_chars": len(context_text),
                "referenced_count": len(referenced),
                "confidence": confidence,
                "risk_level": report.risk_level,
                "model": model_used,
                "used_chat": bool(conversation_history),
                "duration_ms": round(duration_ms, 2),
            },
        )
        return result

    async def suggest_questions(
        self,
        ranked: list[RankedArtefact],
    ) -> list[str]:
        """Suggest 3–5 investigative questions from ranked artefacts (no LLM).

        Args:
            ranked: Triaged artefacts.

        Returns:
            Suggested natural-language questions.
        """
        if not ranked:
            return [
                "What artefacts were recovered from this evidence?",
                "Are there any CRITICAL findings requiring immediate attention?",
                "What follow-up acquisition steps are recommended?",
            ]

        high_plus = [item for item in ranked if item.suspicion_level in _HIGH_PLUS]
        focus = high_plus[:3] or ranked[:3]
        suggestions: list[str] = []
        for item in focus:
            suggestions.append(
                f"What is the forensic significance of artefact {item.artefact_id} "
                f"({item.category.value}, {item.suspicion_level.value})?"
            )
        categories = sorted({item.category.value for item in ranked})
        if categories:
            suggestions.append(
                "How do the "
                + ", ".join(categories[:3])
                + " artefacts relate temporally?"
            )
        suggestions.append(
            "Which HIGH or CRITICAL artefacts suggest persistence or lateral movement?"
        )
        # Deduplicate while preserving order; cap at 5
        unique: list[str] = []
        for question in suggestions:
            if question not in unique:
                unique.append(question)
        return unique[:5]

    def _build_context(
        self,
        artefact_set: ArtefactSet,
        ranked: Optional[list[RankedArtefact]],
    ) -> str:
        """Serialise artefact context, preferring ranked HIGH+ detail."""
        if ranked:
            # Ranked path includes suspicion; put HIGH+ first via summary serializer
            detailed = self._serializer.serialize_for_summary(ranked)
            compact = self._serializer.serialize_for_classification(
                list(artefact_set.artefacts)[:100]
            )
            return detailed + "\n\nAll artefacts (compact):\n" + compact
        return self._serializer.serialize_artefact_set(
            artefact_set,
            max_artefacts=200,
        )

    def _build_chat_messages(
        self,
        history: list[dict[str, str]],
        context_text: str,
        question: str,
    ) -> list[dict[str, str]]:
        """Build Ollama chat messages including truncated history."""
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You are a digital forensics assistant. Answer ONLY from the "
                    "provided artefact data. Mark uncertainty with [UNCERTAIN]. "
                    "Reference artefact IDs when making claims."
                ),
            },
            {
                "role": "user",
                "content": f"Artefact context:\n{context_text}",
            },
        ]
        for item in history[-8:]:
            role = str(item.get("role", "user"))
            content = str(item.get("content", ""))
            if role in {"user", "assistant", "system"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": question})
        return messages

    @staticmethod
    def _extract_referenced_ids(text: str, valid_ids: set[str]) -> list[str]:
        """Return valid artefact IDs referenced in the answer text."""
        found: list[str] = []
        found.extend(_UUID_RE.findall(text))
        found.extend(_ART_ID_RE.findall(text))
        for artefact_id in valid_ids:
            if artefact_id and artefact_id in text and artefact_id not in found:
                found.append(artefact_id)
        referenced: list[str] = []
        for item in found:
            if item in valid_ids and item not in referenced:
                referenced.append(item)
        return referenced

    @staticmethod
    def _score_answer(
        text: str,
        referenced: list[str],
        report: HallucinationReport,
    ) -> float:
        """Heuristic confidence for a Q&A answer."""
        if not text.strip():
            return 0.1
        score = 0.4
        if referenced:
            score += min(0.3, 0.1 * len(referenced))
        if "[UNCERTAIN]" in text.upper() or "insufficient" in text.lower():
            score -= 0.1
        if report.risk_level == "high":
            score = min(score, 0.3)
        elif report.risk_level == "medium":
            score = min(score, 0.55)
        else:
            score += 0.15
        if report.hallucinated_ids:
            score -= 0.15 * len(report.hallucinated_ids)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _cache_key(
        question: str,
        context_text: str,
        history: Optional[list[dict[str, str]]],
    ) -> str:
        """Build a stable cache key for Q&A prompts."""
        hist = ""
        if history:
            hist = "|".join(
                f"{item.get('role','')}:{item.get('content','')[:80]}"
                for item in history[-4:]
            )
        payload = f"{question}|{context_text[:2000]}|{hist}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
        return f"qa:{digest}"
