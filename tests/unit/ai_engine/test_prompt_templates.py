"""Unit tests for ForensicPromptTemplates (Prompt 5.4)."""

from __future__ import annotations

import pytest
from jinja2 import UndefinedError

from dfat.ai_engine.llm.prompts import PROMPT_VERSION, ForensicPromptTemplates


_ANTI_HALLUCINATION_MARKERS = (
    "do not fabricate",
    "only",
    "uncertain",
    "insufficient",
)


def test_prompt_version_is_100() -> None:
    templates = ForensicPromptTemplates()
    assert PROMPT_VERSION == "1.0.0"
    assert templates.get_template_version() == "1.0.0"
    assert ForensicPromptTemplates.PROMPT_VERSION == "1.0.0"


def test_list_templates_includes_all() -> None:
    names = ForensicPromptTemplates().list_templates()
    assert names == [
        "classification",
        "explanation",
        "qa",
        "ranking",
        "summary",
    ]


@pytest.mark.parametrize(
    ("name", "context"),
    [
        ("classification", {"artefact_text": "[a1] Category: injected_code"}),
        ("ranking", {"artefact_text": "[a1] suspicion=high"}),
        (
            "summary",
            {
                "artefact_text": "[a1] detail",
                "total_count": 1,
                "critical_count": 0,
                "high_count": 1,
                "categories": "injected_code",
            },
        ),
        (
            "explanation",
            {
                "artefact_text": "[a1] pid=1",
                "suspicion_level": "HIGH",
            },
        ),
        (
            "qa",
            {
                "context_text": "[a1] network",
                "question": "What IOCs are present?",
            },
        ),
    ],
)
def test_templates_render_with_valid_context(name: str, context: dict) -> None:
    rendered = ForensicPromptTemplates().render(name, **context)
    assert "{{" not in rendered
    assert "---END---" in rendered


def test_strict_undefined_raises_on_missing_variables() -> None:
    with pytest.raises(UndefinedError):
        ForensicPromptTemplates().render("classification")


def test_all_templates_contain_anti_hallucination_instructions() -> None:
    templates = [
        ForensicPromptTemplates.CLASSIFICATION_TEMPLATE,
        ForensicPromptTemplates.RANKING_TEMPLATE,
        ForensicPromptTemplates.SUMMARY_TEMPLATE,
        ForensicPromptTemplates.EXPLANATION_TEMPLATE,
        ForensicPromptTemplates.QA_TEMPLATE,
    ]
    for template in templates:
        lowered = template.lower()
        assert any(marker in lowered for marker in _ANTI_HALLUCINATION_MARKERS), template[:80]


def test_legacy_artefacts_context_still_renders() -> None:
    artefacts = [
        {
            "artefact_id": "art-1",
            "category": "network_connection",
            "raw_data": {"protocol": "tcp"},
            "suspicion_level": "high",
            "relevance_score": 0.8,
        }
    ]
    text = ForensicPromptTemplates().render("classification", artefacts=artefacts)
    assert "art-1" in text
    assert "Do not fabricate" in text or "do not fabricate" in text.lower()
