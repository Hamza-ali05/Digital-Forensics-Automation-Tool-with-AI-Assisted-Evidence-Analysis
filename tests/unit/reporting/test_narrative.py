"""Unit tests for narrative report assembly (Prompt 6.4)."""

from __future__ import annotations

from pathlib import Path

from dfat.ai_engine.llm.config import PROMPT_VERSION
from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import RankedArtefact
from dfat.core.models.evidence import CaseMetadata
from dfat.reporting.narrative import NarrativeAssembler


def _template_dir() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "src"
        / "dfat"
        / "reporting"
        / "templates"
    )


def _summary() -> SummaryResult:
    return SummaryResult(
        full_text="Full investigative narrative body.",
        executive_summary="Suspicious injected code and persistence artefacts observed.",
        key_findings=[
            "RWX memory region in suspicious process",
            "Run key persistence entry present",
        ],
        timeline_narrative="T+0 acquisition; T+1 triage flagged injected_code.",
        iocs_identified=["evil.exe", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"],
        recommended_actions=["Preserve memory image", "Review autoruns"],
        model_used="llama3",
        prompt_version=PROMPT_VERSION,
        generation_params={"temperature": 0.1},
        confidence_score=0.72,
    )


def test_narrative_always_includes_disclaimer(
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify assembled narrative always includes the LLM disclaimer."""
    assembler = NarrativeAssembler(_template_dir())
    report = assembler.assemble(
        summary_result=_summary(),
        llm_model="llama3",
        generation_params={"evidence_id": sample_ranked_artefacts[0].source_evidence_id},
        ranked_artefacts=sample_ranked_artefacts,
        case=sample_case_metadata,
        confidence_score=0.72,
    )
    text = report.summary_text
    assert "DISCLAIMER:" in text
    assert "Scanlon et al." in text
    assert "primary evidential record" in text.lower() or "structured JSON" in text


def test_disclaimer_references_model_and_prompt_version(
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify disclaimer embeds model, prompt version, and confidence."""
    assembler = NarrativeAssembler(_template_dir())
    disclaimer = assembler._build_disclaimer("test-model", 0.5, "1.0.0")
    assert "test-model" in disclaimer
    assert "prompt version 1.0.0" in disclaimer
    assert "50%" in disclaimer
    assert "Scanlon et al., 2023" in disclaimer
    assert "expert testimony" in disclaimer

    report = assembler.assemble(
        summary_result=_summary(),
        llm_model="test-model",
        generation_params={"prompt_version": "1.0.0"},
        ranked_artefacts=sample_ranked_artefacts,
        case=sample_case_metadata,
        confidence_score=0.5,
    )
    assert "test-model" in report.summary_text
    assert "1.0.0" in report.summary_text


def test_statistics_are_accurate(
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify statistics appendix counts match ranked artefacts."""
    assembler = NarrativeAssembler(_template_dir())
    appendix = assembler._build_statistics_appendix(sample_ranked_artefacts)
    assert f"Total artefacts: {len(sample_ranked_artefacts)}" in appendix

    expected_categories: dict[str, int] = {c.value: 0 for c in ArtefactCategory}
    expected_levels: dict[str, int] = {level.value: 0 for level in SuspicionLevel}
    for artefact in sample_ranked_artefacts:
        expected_categories[artefact.category.value] += 1
        expected_levels[artefact.suspicion_level.value] += 1

    for name, count in expected_categories.items():
        assert f"{name}: {count}" in appendix
    for name, count in expected_levels.items():
        assert f"{name}: {count}" in appendix

    report = assembler.assemble(
        summary_result=_summary(),
        llm_model="llama3",
        generation_params={},
        ranked_artefacts=sample_ranked_artefacts,
        case=sample_case_metadata,
        confidence_score=0.72,
    )
    assert appendix in report.summary_text or "Statistics Appendix" in report.summary_text


def test_template_renders_without_errors(
    sample_ranked_artefacts: list[RankedArtefact],
    sample_case_metadata: CaseMetadata,
) -> None:
    """Verify Jinja2 template renders a complete multi-section narrative."""
    assembler = NarrativeAssembler(_template_dir())
    report = assembler.assemble(
        summary_result=_summary(),
        llm_model="llama3",
        generation_params={"evidence_id": "ev-narr-1"},
        ranked_artefacts=sample_ranked_artefacts,
        case=sample_case_metadata,
        confidence_score=0.72,
    )
    text = report.summary_text
    for section in (
        "LLM Disclaimer",
        "Executive Summary",
        "Key Findings",
        "Detailed Findings by Category",
        "Timeline of Events",
        "Indicators of Compromise",
        "Recommended Actions",
        "Statistics Appendix",
        "Report Metadata",
    ):
        assert section in text
    assert "Suspicious injected code" in text
    assert "evil.exe" in text
    assert report.llm_model_used == "llama3"
    assert report.evidence_id == "ev-narr-1"


# Prompt 6.20 named coverage aliases
test_disclaimer_always_present = test_narrative_always_includes_disclaimer
test_disclaimer_references_scanlon = test_disclaimer_references_model_and_prompt_version
test_statistics_appendix_accurate = test_statistics_are_accurate
test_template_renders_all_sections = test_template_renders_without_errors



def test_format_key_findings_empty_and_populated() -> None:
    """Verify key findings formatting for empty and non-empty lists."""
    assembler = NarrativeAssembler(_template_dir())
    assert "No key findings" in assembler._format_key_findings([])
    formatted = assembler._format_key_findings(["Finding A", "Finding B"])
    assert "- Finding A" in formatted
    assert "- Finding B" in formatted
