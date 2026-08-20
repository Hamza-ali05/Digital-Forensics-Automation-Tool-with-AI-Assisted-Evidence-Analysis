"""Unit tests for MITREMapper."""

from __future__ import annotations

from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import RankedArtefact
from dfat.threat_intel.mitre_mapper import MITREMapper


def _ranked(
    artefact_id: str,
    category: ArtefactCategory,
    *,
    suspicion: SuspicionLevel = SuspicionLevel.MEDIUM,
    **raw: object,
) -> RankedArtefact:
    return RankedArtefact(
        artefact_id=artefact_id,
        category=category,
        source_evidence_id="ev-1",
        raw_data=dict(raw),
        suspicion_level=suspicion,
        relevance_score=0.5,
    )


def test_registry_run_key_maps_to_t1547() -> None:
    mapper = MITREMapper()
    artefact = _ranked(
        "reg-1",
        ArtefactCategory.REGISTRY_KEY,
        key_path=r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run\malware",
    )
    mappings = mapper.map_artefact(artefact)
    assert len(mappings) == 1
    assert mappings[0].technique_id == "T1547.001"
    assert mappings[0].tactic == "Persistence"


def test_injected_code_maps_to_t1055() -> None:
    mapper = MITREMapper()
    artefact = _ranked(
        "inj-1",
        ArtefactCategory.INJECTED_CODE,
        process_name="explorer.exe",
    )
    mappings = mapper.map_artefact(artefact)
    assert any(item.technique_id == "T1055" for item in mappings)


def test_suspicious_port_maps_to_t1071() -> None:
    mapper = MITREMapper()
    artefact = _ranked(
        "net-1",
        ArtefactCategory.NETWORK_CONNECTION,
        remote_address="203.0.113.10",
        remote_port=4444,
        is_external=True,
    )
    mappings = mapper.map_artefact(artefact)
    assert any(item.technique_id == "T1071" for item in mappings)


def test_service_event_maps_to_t1543() -> None:
    mapper = MITREMapper()
    artefact = _ranked(
        "evt-1",
        ArtefactCategory.EVENT_LOG,
        EventID="7045",
        ServiceName="EvilSvc",
    )
    mappings = mapper.map_artefact(artefact)
    assert any(item.technique_id == "T1543.003" for item in mappings)


def test_get_tactic_coverage_groups_techniques() -> None:
    mapper = MITREMapper()
    ranked = [
        _ranked(
            "reg-1",
            ArtefactCategory.REGISTRY_KEY,
            key_path=r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run\x",
        ),
        _ranked(
            "net-1",
            ArtefactCategory.NETWORK_CONNECTION,
            remote_address="10.0.0.5",
            remote_port=4444,
            is_external=True,
        ),
    ]
    mappings = mapper.map_artefact_set(ranked)
    coverage = mapper.get_tactic_coverage(mappings)
    assert "Persistence" in coverage
    assert "Command and Control" in coverage
    assert "T1547.001" in coverage["Persistence"]


def test_get_technique_info_unknown_id() -> None:
    mapper = MITREMapper()
    info = mapper.get_technique_info("T9999")
    assert info["technique_id"] == "T9999"
    assert info["technique_name"] == "Unknown technique"
