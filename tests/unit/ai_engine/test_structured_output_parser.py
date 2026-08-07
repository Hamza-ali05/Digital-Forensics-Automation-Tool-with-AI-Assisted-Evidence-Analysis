"""Unit tests for StructuredOutputParser (Prompt 5.13)."""

from __future__ import annotations

from dfat.ai_engine.llm.response_parser import StructuredOutputParser


def test_parse_clean_classification_json() -> None:
    parser = StructuredOutputParser()
    text = (
        '[{"artefact_id":"a1","suspicion_level":"HIGH",'
        '"reasoning":"RWX","ioc_indicators":["MZ"]}]'
    )
    items = parser.parse_classification_array(text)
    assert len(items) == 1
    assert items[0]["artefact_id"] == "a1"
    assert items[0]["ioc_indicators"] == ["MZ"]


def test_parse_markdown_wrapped_ranking_json() -> None:
    parser = StructuredOutputParser()
    text = """Here you go:
```json
[
  {"artefact_id": "a1", "relevance_score": 0.9, "priority_reasoning": "IOC heavy"}
]
```
"""
    items = parser.parse_ranking_array(text)
    assert items[0]["relevance_score"] == 0.9
    assert items[0]["priority_reasoning"] == "IOC heavy"


def test_parse_partial_json_with_repair() -> None:
    parser = StructuredOutputParser()
    text = '[{"artefact_id": "a1", "suspicion_level": "LOW", "reasoning": "ok",}'
    items = parser.parse_classification_array(text)
    assert items[0]["artefact_id"] == "a1"


def test_parse_embedded_json_in_prose() -> None:
    parser = StructuredOutputParser()
    text = (
        "Analysis complete. Results: "
        '[{"artefact_id":"a2","relevance_score":0.4,"priority_reasoning":"low"}] '
        "End of message."
    )
    items = parser.parse_ranking_array(text)
    assert items[0]["artefact_id"] == "a2"


def test_summary_section_extraction_varied_formatting() -> None:
    parser = StructuredOutputParser()
    text = """
## Executive Summary
Overview of the case.

2) KEY FINDINGS
- Finding one

### Timeline of Events
Day 1 then day 2.

4. INDICATORS OF COMPROMISE:
* hash abc

Recommended Next Steps
Validate findings.
"""
    sections = parser.parse_summary_sections(text)
    assert "Overview" in sections["executive_summary"]
    assert "Finding one" in sections["key_findings"]
    assert "Day 1" in sections["timeline"]
    assert "hash" in sections["iocs"].lower()
    assert "Validate" in sections["recommended_actions"]


def test_validate_schema() -> None:
    parser = StructuredOutputParser()
    assert parser._validate_schema({"a": 1, "b": 2}, ["a", "b"]) is True
    assert parser._validate_schema({"a": 1}, ["a", "b"]) is False
    assert parser._validate_schema("nope", ["a"]) is False
