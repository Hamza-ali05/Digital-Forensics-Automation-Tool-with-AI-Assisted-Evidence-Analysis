"""Unit tests for artefact serialisation (Prompt 5.20)."""

from __future__ import annotations

from dfat.ai_engine.preprocessing import ArtefactSerializer
from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet


def _artefact(
    artefact_id: str,
    category: ArtefactCategory,
    **raw: object,
) -> Artefact:
    return Artefact(
        artefact_id=artefact_id,
        category=category,
        source_evidence_id="ev-1",
        raw_data=dict(raw) if raw else {"name": artefact_id},
    )


def test_serialize_artefact_includes_all_fields() -> None:
    """Verify serialisation includes id, category, and raw_data fields."""
    serializer = ArtefactSerializer()
    artefact = _artefact(
        "art-1",
        ArtefactCategory.NETWORK_CONNECTION,
        local_port=443,
        remote_address="8.8.8.8",
        protocol="tcp",
    )
    text = serializer.serialize_artefact(artefact)
    assert "[art-1]" in text
    assert "network_connection" in text
    assert "local_port" in text
    assert "443" in text
    assert "remote_address" in text
    assert "8.8.8.8" in text
    assert "protocol" in text


def test_serialize_set_respects_limit() -> None:
    """Verify artefact-set serialisation respects max_artefacts."""
    serializer = ArtefactSerializer()
    artefacts = [
        _artefact(f"a-{i}", ArtefactCategory.FILESYSTEM_METADATA) for i in range(10)
    ]
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=artefacts,
        categories_present=[ArtefactCategory.FILESYSTEM_METADATA],
    )
    text = serializer.serialize_artefact_set(artefact_set, max_artefacts=3)
    kept = sum(1 for i in range(10) if f"a-{i}" in text)
    assert kept <= 3


def test_serialize_prioritises_injected_code() -> None:
    """Verify injected_code artefacts are preferred under size limits."""
    serializer = ArtefactSerializer()
    artefacts = [
        _artefact(f"fs-{i}", ArtefactCategory.FILESYSTEM_METADATA) for i in range(5)
    ] + [
        _artefact("inj-1", ArtefactCategory.INJECTED_CODE, pid=100),
        _artefact("net-1", ArtefactCategory.NETWORK_CONNECTION, protocol="tcp"),
    ]
    artefact_set = ArtefactSet(
        evidence_id="ev-1",
        artefacts=artefacts,
        categories_present=[
            ArtefactCategory.FILESYSTEM_METADATA,
            ArtefactCategory.INJECTED_CODE,
            ArtefactCategory.NETWORK_CONNECTION,
        ],
    )
    text = serializer.serialize_artefact_set(artefact_set, max_artefacts=3)
    assert "inj-1" in text


def test_serialize_for_classification_compact() -> None:
    """Verify compact one-line classification serialisation."""
    serializer = ArtefactSerializer()
    artefacts = [
        _artefact("art-1", ArtefactCategory.RUNNING_PROCESS, name="cmd.exe"),
        _artefact("art-2", ArtefactCategory.INJECTED_CODE, pid=42),
    ]
    text = serializer.serialize_for_classification(artefacts)
    assert "[art-1]" in text
    assert "running_process" in text
    assert "name=cmd.exe" in text or "cmd.exe" in text
    assert "[art-2]" in text
    assert "\n" in text
