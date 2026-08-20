"""Unit tests for SigmaEngine."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact
from dfat.threat_intel.sigma_engine import SigmaEngine, _detection_matches


def _event_log_artefact(**raw: object) -> Artefact:
    return Artefact(
        artefact_id="ev-log-1",
        category=ArtefactCategory.EVENT_LOG,
        source_evidence_id="ev-1",
        raw_data=dict(raw),
    )


def _process_artefact(**raw: object) -> Artefact:
    return Artefact(
        artefact_id="proc-1",
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev-1",
        raw_data=dict(raw),
    )


def _write_sigma_rule(path: Path, **overrides: object) -> Path:
    rule = {
        "id": "test-rule-001",
        "title": "Test Sigma Rule",
        "level": "high",
        "description": "Detects test pattern",
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {
            "selection": {"CommandLine|contains": "mimikatz"},
            "condition": "selection",
        },
        "tags": ["attack.credential_access", "attack.t1003"],
    }
    rule.update(overrides)
    path.write_text(yaml.dump(rule), encoding="utf-8")
    return path


def test_load_rules_empty_dir(tmp_path: Path) -> None:
    engine = SigmaEngine(tmp_path / "rules")
    assert engine.load_rules() == 0


def test_load_and_match_process(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    _write_sigma_rule(rules_dir / "mimi.yml")

    engine = SigmaEngine(rules_dir)
    assert engine.load_rules() == 1

    artefact = _process_artefact(
        name="cmd.exe",
        pid=1234,
        CommandLine="C:\\tools\\mimikatz.exe sekurlsa::logonpasswords",
    )
    matches = engine.match_process(artefact)
    assert len(matches) == 1
    assert matches[0].rule_name == "Test Sigma Rule"
    assert matches[0].level == "high"
    assert "attack.t1003" in matches[0].mitre_techniques
    assert matches[0].artefact_id == "proc-1"


def test_no_match_when_pattern_absent(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    _write_sigma_rule(rules_dir / "mimi.yml")

    engine = SigmaEngine(rules_dir)
    engine.load_rules()

    artefact = _process_artefact(
        name="notepad.exe",
        pid=5678,
        CommandLine="notepad.exe readme.txt",
    )
    assert engine.match_process(artefact) == []


def test_match_event_log(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    _write_sigma_rule(
        rules_dir / "svchost.yml",
        id="rule-002",
        title="Suspicious svchost",
        detection={
            "selection": {"Image|endswith": "\\svchost.exe", "ParentImage|contains": "cmd"},
            "condition": "selection",
        },
        logsource={"product": "windows", "service": "sysmon"},
    )
    engine = SigmaEngine(rules_dir)
    engine.load_rules()

    artefact = _event_log_artefact(
        Image="C:\\Windows\\System32\\svchost.exe",
        ParentImage="C:\\Windows\\cmd.exe",
        EventID=1,
    )
    matches = engine.match_event_log(artefact)
    assert len(matches) == 1
    assert matches[0].rule_name == "Suspicious svchost"


def test_wrong_category_returns_empty(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    _write_sigma_rule(rules_dir / "r.yml")

    engine = SigmaEngine(rules_dir)
    engine.load_rules()

    browser = Artefact(
        artefact_id="b1",
        category=ArtefactCategory.BROWSER_HISTORY,
        source_evidence_id="ev-1",
        raw_data={"url": "https://example.com"},
    )
    assert engine.match_event_log(browser) == []
    assert engine.match_process(browser) == []


def test_detection_matches_keyword_list() -> None:
    detection = {
        "keywords": ["evil", "bad"],
        "condition": "keywords",
    }
    assert _detection_matches(detection, {"cmd": "this is evil"})
    assert not _detection_matches(detection, {"cmd": "this is good"})
