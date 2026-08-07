"""Unit tests for narrative formatting (Prompt 5.9)."""

from __future__ import annotations

from datetime import UTC, datetime

from dfat.ai_engine.summarization import NarrativeFormatter, SummaryResult
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import RankedArtefact


def test_formatted_narrative_has_disclaimer_scanlon_and_sections() -> None:
    summary = SummaryResult(
        full_text="raw",
        executive_summary="Possible injection activity observed.",
        key_findings=["RWX region with MZ header"],
        timeline_narrative="Process created then network egress.",
        iocs_identified=["MZ header", "8.8.8.8"],
        recommended_actions=["Validate process dump"],
        model_used="llama3",
        prompt_version="1.0.0",
        generation_params={"temperature": 0.1},
        confidence_score=0.82,
        generated_at=datetime.now(UTC),
    )
    ranked = [
        RankedArtefact(
            artefact_id="art-1",
            category=ArtefactCategory.INJECTED_CODE,
            source_evidence_id="ev-1",
            raw_data={"pid": 1},
            suspicion_level=SuspicionLevel.CRITICAL,
            relevance_score=0.95,
            classification_reasoning="Injected code",
        )
    ]

    narrative = NarrativeFormatter().format_narrative(
        summary,
        ranked,
        case_name="Case Alpha",
        evidence_id="ev-1",
    )

    assert "Scanlon et al., 2023" in narrative.disclaimer
    assert "82%" in narrative.disclaimer or "confidence: 82%" in narrative.disclaimer
    assert narrative.confidence_score == 0.82
    assert narrative.model_used == "llama3"
    assert narrative.has_required_sections is True
    for key in (
        "title",
        "disclaimer",
        "executive_summary",
        "findings_by_category",
        "timeline",
        "ioc_table",
        "recommended_actions",
        "statistics",
        "metadata",
    ):
        assert key in narrative.sections
        assert narrative.sections[key].strip()
    assert "Scanlon et al., 2023" in narrative.full_text
    assert narrative.word_count > 0
