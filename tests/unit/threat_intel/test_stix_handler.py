"""Unit tests for STIXHandler."""

from __future__ import annotations

import json
from pathlib import Path

from dfat.threat_intel.stix_handler import STIXHandler


def _write_bundle(path: Path) -> None:
    payload = {
        "type": "bundle",
        "id": "bundle--test",
        "objects": [
            {
                "type": "indicator",
                "id": "indicator--1",
                "name": "Evil domain",
                "description": "Known C2 domain",
                "labels": ["high"],
                "pattern": "[domain-name:value = 'evil.example.com']",
                "external_references": [
                    {
                        "source_name": "mitre-attack",
                        "external_id": "T1071",
                    }
                ],
            },
            {
                "type": "attack-pattern",
                "id": "attack-pattern--1",
                "name": "Application Layer Protocol",
                "description": "C2 over application protocol",
                "external_references": [
                    {
                        "source_name": "mitre-attack",
                        "external_id": "T1071",
                    }
                ],
                "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "command-and-control"}],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_parse_bundle_and_extract_indicators(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    _write_bundle(bundle)

    handler = STIXHandler()
    objects = handler.parse_bundle(bundle)
    assert len(objects) == 2

    indicators = handler.extract_indicators(objects)
    assert len(indicators) == 1
    assert indicators[0].value == "evil.example.com"
    assert indicators[0].ioc_type == "domain"
    assert "T1071" in indicators[0].mitre_techniques


def test_extract_attack_patterns_from_cached_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    _write_bundle(bundle)

    handler = STIXHandler()
    handler.parse_bundle(bundle)
    patterns = handler.extract_attack_patterns()

    assert len(patterns) == 1
    assert patterns[0]["name"] == "Application Layer Protocol"
    assert "T1071" in patterns[0]["technique_ids"]
    assert "Command And Control" in patterns[0]["tactics"]


def test_parse_bundle_missing_file_returns_empty(tmp_path: Path) -> None:
    handler = STIXHandler()
    assert handler.parse_bundle(tmp_path / "missing.json") == []
