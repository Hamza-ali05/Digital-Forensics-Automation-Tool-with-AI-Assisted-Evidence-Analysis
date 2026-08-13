"""Human-readable narrative assembler (supplementary investigative aid).

Known limitation: LLM narratives are advisory. The structured JSON artefact
layer is the primary evidential record (Scanlon et al., 2023).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape

from dfat.ai_engine.llm.config import PROMPT_VERSION
from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.core.models.report import NarrativeReport


class NarrativeAssembler:
    """Assemble a disclaimer-wrapped investigative narrative report."""

    def __init__(self, template_dir: Path) -> None:
        """Initialise the narrative assembler.

        Args:
            template_dir: Directory containing ``narrative_template.j2``.
        """
        self._template_dir = template_dir
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(enabled_extensions=()),
        )

    def assemble(
        self,
        summary_result: SummaryResult,
        llm_model: str,
        generation_params: dict[str, Any],
        ranked_artefacts: list[RankedArtefact],
        case: CaseMetadata,
        confidence_score: float,
    ) -> NarrativeReport:
        """Assemble a structured narrative document from a summary result.

        Args:
            summary_result: Structured LLM (or fallback) summary sections.
            llm_model: Model identifier used for generation.
            generation_params: Generation parameter snapshot.
            ranked_artefacts: Triaged artefacts for findings and statistics.
            case: Case metadata for the title and metadata blocks.
            confidence_score: Overall narrative confidence in ``[0.0, 1.0]``.

        Returns:
            Populated ``NarrativeReport`` with the rendered narrative body.
        """
        model = llm_model or summary_result.model_used or "unknown"
        confidence = float(
            confidence_score
            if confidence_score is not None
            else summary_result.confidence_score
        )
        prompt_version = (
            str(generation_params.get("prompt_version") or summary_result.prompt_version)
            or PROMPT_VERSION
        )
        disclaimer = self._build_disclaimer(model, confidence, prompt_version)
        statistics_appendix = self._build_statistics_appendix(ranked_artefacts)
        statistics = self._compute_statistics(ranked_artefacts)
        key_findings = self._format_key_findings(list(summary_result.key_findings))
        findings_by_category = self._group_by_category(ranked_artefacts)
        timeline = self._resolve_timeline(summary_result, ranked_artefacts)
        iocs = list(summary_result.iocs_identified)
        actions = list(summary_result.recommended_actions)
        generated_at = datetime.now(UTC)
        report_id = str(uuid4())
        evidence_id = self._resolve_evidence_id(ranked_artefacts, generation_params)

        executive_summary = (
            summary_result.executive_summary.strip()
            or summary_result.full_text.strip()
            or "_No summary provided._"
        )

        # Prepend disclaimer into the rendered document (non-removable).
        template = self._env.get_template("narrative_template.j2")
        rendered = template.render(
            case_name=case.case_name,
            case_id=case.case_id,
            generated_at=generated_at.isoformat(),
            evidence_id=evidence_id,
            report_id=report_id,
            llm_model=model,
            confidence=confidence,
            prompt_version=prompt_version,
            disclaimer=disclaimer,
            executive_summary=executive_summary,
            key_findings=key_findings,
            key_findings_list=list(summary_result.key_findings),
            findings_by_category=findings_by_category,
            timeline=timeline,
            iocs=iocs,
            actions=actions,
            statistics=statistics,
            statistics_appendix=statistics_appendix,
            generation_params=generation_params or dict(summary_result.generation_params),
            artefact_count=len(ranked_artefacts),
            investigator=case.investigator,
        )

        # Guarantee disclaimer leads the stored narrative body.
        body = rendered.strip()
        if not body.lstrip().startswith("DISCLAIMER:") and disclaimer not in body[:500]:
            body = f"{disclaimer}\n\n{body}"

        # Append statistics appendix if the template omitted it.
        if statistics_appendix and statistics_appendix not in body:
            body = f"{body.rstrip()}\n\n## Statistics Appendix\n\n{statistics_appendix}\n"

        merged_params = dict(generation_params or {})
        merged_params.setdefault("prompt_version", prompt_version)
        merged_params.setdefault("confidence_score", confidence)

        return NarrativeReport(
            report_id=report_id,
            evidence_id=evidence_id,
            summary_text=body,
            llm_model_used=model,
            generation_parameters=merged_params,
            generated_at=generated_at,
        )

    def _build_disclaimer(
        self,
        model: str,
        confidence: float,
        prompt_version: str,
    ) -> str:
        """Build the non-removable LLM disclaimer (Scanlon et al., 2023).

        Args:
            model: Model identifier.
            confidence: Confidence score in ``[0.0, 1.0]``.
            prompt_version: Prompt catalogue version string.

        Returns:
            Disclaimer paragraph.
        """
        clamped = max(0.0, min(1.0, float(confidence)))
        return (
            f"DISCLAIMER: This investigative narrative was generated by {model} "
            f"(prompt version {prompt_version}, confidence: {clamped:.0%}). "
            "AI-generated content must be verified against the structured JSON "
            "artefact data, which serves as the primary evidential record. "
            "LLM outputs may contain inaccuracies (Scanlon et al., 2023). "
            "This summary is for investigative guidance only and does not "
            "constitute expert testimony."
        )

    def _build_statistics_appendix(self, ranked: list[RankedArtefact]) -> str:
        """Build a text-formatted statistics appendix.

        Args:
            ranked: Ranked artefacts.

        Returns:
            Multi-line statistics table as plain text.
        """
        stats = self._compute_statistics(ranked)
        lines = [
            f"Total artefacts: {stats['total_artefacts']}",
            "",
            "By category:",
        ]
        for key, count in sorted(stats["by_category"].items()):
            lines.append(f"  - {key}: {count}")
        lines.append("")
        lines.append("By suspicion level:")
        for key, count in sorted(stats["by_suspicion_level"].items()):
            lines.append(f"  - {key}: {count}")
        return "\n".join(lines)

    def _format_key_findings(self, findings: list[str]) -> str:
        """Format key findings as a markdown bullet list.

        Args:
            findings: Free-text finding lines from the summary.

        Returns:
            Markdown bullet list, or a placeholder when empty.
        """
        cleaned = [item.strip() for item in findings if item and str(item).strip()]
        if not cleaned:
            return "_No key findings were produced by the model._"
        return "\n".join(f"- {item}" for item in cleaned)

    @staticmethod
    def _compute_statistics(ranked: list[RankedArtefact]) -> dict[str, Any]:
        """Count artefacts by category and suspicion level (all enum members)."""
        by_category = {category.value: 0 for category in ArtefactCategory}
        by_suspicion = {level.value: 0 for level in SuspicionLevel}
        for artefact in ranked:
            by_category[artefact.category.value] = (
                by_category.get(artefact.category.value, 0) + 1
            )
            by_suspicion[artefact.suspicion_level.value] = (
                by_suspicion.get(artefact.suspicion_level.value, 0) + 1
            )
        return {
            "total_artefacts": len(ranked),
            "by_category": by_category,
            "by_suspicion_level": by_suspicion,
        }

    @staticmethod
    def _group_by_category(
        ranked: list[RankedArtefact],
    ) -> dict[str, list[RankedArtefact]]:
        """Group ranked artefacts by category name."""
        grouped: dict[str, list[RankedArtefact]] = defaultdict(list)
        for artefact in ranked:
            grouped[artefact.category.value].append(artefact)
        return dict(sorted(grouped.items()))

    def _resolve_timeline(
        self,
        summary_result: SummaryResult,
        ranked: list[RankedArtefact],
    ) -> list[str] | str:
        """Prefer the summary timeline narrative; else artefact timestamps."""
        narrative = (summary_result.timeline_narrative or "").strip()
        if narrative:
            return narrative
        return self._extract_timeline(ranked)

    @staticmethod
    def _extract_timeline(ranked: list[RankedArtefact]) -> list[str]:
        """Best-effort timeline lines from artefact raw_data timestamps."""
        events: list[str] = []
        for artefact in ranked:
            raw = artefact.raw_data
            stamp: Optional[Any] = (
                raw.get("timestamp")
                or raw.get("create_time")
                or raw.get("last_visit_time")
                or raw.get("modified_time")
            )
            if stamp is None:
                continue
            events.append(
                f"{stamp} | {artefact.category.value} | "
                f"{artefact.source_path or artefact.artefact_id}"
            )
        return events

    @staticmethod
    def _resolve_evidence_id(
        ranked: list[RankedArtefact],
        generation_params: dict[str, Any],
    ) -> str:
        """Resolve evidence_id from params or ranked artefact provenance."""
        from_params = generation_params.get("evidence_id")
        if isinstance(from_params, str) and from_params.strip():
            return from_params.strip()
        if ranked:
            return ranked[0].source_evidence_id
        return "unknown"
