"""Unit tests for YARAEngine."""

from __future__ import annotations

from pathlib import Path

import pytest

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact
from dfat.threat_intel.yara_engine import YARAEngine


def _yara_installed() -> bool:
    try:
        import yara  # noqa: F401

        return True
    except ImportError:
        return False


def _artefact(
    artefact_id: str = "a1",
    category: ArtefactCategory = ArtefactCategory.FILESYSTEM_METADATA,
    **raw: object,
) -> Artefact:
    return Artefact(
        artefact_id=artefact_id,
        category=category,
        source_evidence_id="ev-1",
        raw_data=dict(raw),
    )


def test_load_rules_returns_zero_with_empty_dir(tmp_path: Path) -> None:
    engine = YARAEngine(tmp_path / "rules")
    assert engine.load_rules() == 0
    assert engine.get_loaded_rules_count() == 0


def test_scan_bytes_returns_empty_when_no_rules(tmp_path: Path) -> None:
    engine = YARAEngine(tmp_path / "rules")
    engine.load_rules()
    assert engine.scan_bytes(b"hello world") == []


def test_scan_artefact_skips_non_scannable_category(tmp_path: Path) -> None:
    engine = YARAEngine(tmp_path / "rules")
    engine.load_rules()
    artefact = _artefact(category=ArtefactCategory.BROWSER_HISTORY)
    assert engine.scan_artefact(artefact) == []


@pytest.mark.skipif(
    not _yara_installed(),
    reason="yara-python not installed",
)
def test_load_and_scan_bytes(tmp_path: Path) -> None:
    rule_file = tmp_path / "rules" / "test.yar"
    rule_file.parent.mkdir()
    rule_file.write_text(
        'rule TestRule { strings: $s1 = "evil_payload" condition: $s1 }'
    )
    engine = YARAEngine(tmp_path / "rules")
    assert engine.load_rules() == 1
    matches = engine.scan_bytes(b"this contains evil_payload inside")
    assert len(matches) == 1
    assert matches[0].rule_name == "TestRule"
