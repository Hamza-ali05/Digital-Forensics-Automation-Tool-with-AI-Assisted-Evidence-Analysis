"""Unit tests for classification response parsing (Prompt 5.6)."""

from __future__ import annotations

from dfat.ai_engine.classification.parser import ClassificationResponseParser
from dfat.ai_engine.llm.response_parser import LLMResponseParser
from dfat.core.enums import SuspicionLevel


def test_parse_clean_json_array() -> None:
    parser = ClassificationResponseParser()
    text = (
        '[{"artefact_id":"a1","suspicion_level":"HIGH",'
        '"reasoning":"Suspicious RWX region","ioc_indicators":["MZ"]}]'
    )
    results = parser.parse(text, ["a1", "a2"])
    assert len(results) == 2
    assert results[0].artefact_id == "a1"
    assert results[0].suspicion_level is SuspicionLevel.HIGH
    assert results[1].artefact_id == "a2"
    assert results[1].suspicion_level is SuspicionLevel.INFORMATIONAL
    assert results[1].reasoning == "Not classified by AI"


def test_parse_json_in_markdown_code_block() -> None:
    parser = ClassificationResponseParser()
    text = """Here are the results:
```json
[
  {"artefact_id": "a1", "suspicion_level": "MEDIUM", "reasoning": "Odd registry run key"}
]
```
Hope this helps.
"""
    results = parser.parse(text, ["a1"])
    assert len(results) == 1
    assert results[0].suspicion_level is SuspicionLevel.MEDIUM


def test_parse_partial_json_with_repair() -> None:
    parser = ClassificationResponseParser()
    # Missing closing bracket / trailing comma
    text = '[{"artefact_id": "a1", "suspicion_level": "LOW", "reasoning": "Benign",}'
    results = parser.parse(text, ["a1"])
    assert results[0].artefact_id == "a1"
    assert results[0].suspicion_level is SuspicionLevel.LOW


def test_discards_hallucinated_ids() -> None:
    parser = ClassificationResponseParser()
    text = (
        '[{"artefact_id":"real","suspicion_level":"CRITICAL","reasoning":"Injected"},'
        '{"artefact_id":"fake-hallucinated","suspicion_level":"CRITICAL","reasoning":"Nope"}]'
    )
    results = parser.parse(text, ["real"])
    assert len(results) == 1
    assert results[0].artefact_id == "real"
    assert all(r.artefact_id != "fake-hallucinated" for r in results)


def test_llm_response_parser_extract_helpers() -> None:
    helper = LLMResponseParser()
    cleaned = helper.clean_response("```json\n{\"a\": 1}\n```")
    assert cleaned.startswith("{")
    assert helper.extract_json_object('prefix {"x": 2} suffix') == {"x": 2}
    assert helper.extract_between_markers("aaSTARTvalueEND", "START", "END") == "value"
