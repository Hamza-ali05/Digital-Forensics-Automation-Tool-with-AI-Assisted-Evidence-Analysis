"""Unit tests for DatasetClassifier."""

from __future__ import annotations

from pathlib import Path

from dfat.dataset_intelligence.classifier import DatasetClassifier
from dfat.dataset_intelligence.enums import DatasetCategory, DatasetFormat, DatasetStatus
from dfat.dataset_intelligence.models import DatasetRecord


def _record(
    name: str,
    *,
    file_path: Path | None = None,
    fmt: DatasetFormat = DatasetFormat.UNKNOWN,
) -> DatasetRecord:
    path = file_path or Path("/data") / name
    return DatasetRecord(
        name=name,
        file_path=path,
        category=DatasetCategory.USER_UPLOADED,
        format=fmt,
        status=DatasetStatus.DISCOVERED,
        file_size_bytes=100,
        hash_sha256="a" * 64,
        parent_directory=str(path.parent),
    )


def test_dfrws_path_classified_as_benchmark() -> None:
    classifier = DatasetClassifier()
    dataset = _record("challenge.json", file_path=Path("/datasets/dfrws/challenge.json"))
    result = classifier.classify(dataset)
    assert result.category == DatasetCategory.BENCHMARK
    assert "forensic_challenge" in result.tags
    assert "RQ4" in result.associated_research_objectives


def test_malware_samples_classified_for_ml_and_threat_intel() -> None:
    classifier = DatasetClassifier()
    dataset = _record(
        "samples.csv",
        file_path=Path("/feeds/malware/samples.csv"),
        fmt=DatasetFormat.CSV,
    )
    result = classifier.classify(dataset)
    assert result.category == DatasetCategory.MACHINE_LEARNING
    assert "threat_intelligence" in result.tags


def test_yara_rules_format_maps_to_threat_intel() -> None:
    classifier = DatasetClassifier()
    dataset = _record(
        "rules.yar",
        file_path=Path("/intel/yara/rules.yar"),
        fmt=DatasetFormat.YARA_RULES,
    )
    result = classifier.classify(dataset)
    assert result.category == DatasetCategory.THREAT_INTELLIGENCE
    assert "IOCRuleMatching" in result.supported_forensic_modules


def test_pcap_maps_to_forensic_operational() -> None:
    classifier = DatasetClassifier()
    dataset = _record(
        "traffic.pcap",
        file_path=Path("/ops/traffic.pcap"),
        fmt=DatasetFormat.PCAP,
    )
    result = classifier.classify(dataset)
    assert result.category == DatasetCategory.FORENSIC_OPERATIONAL


def test_classify_batch_preserves_order() -> None:
    classifier = DatasetClassifier()
    datasets = [
        _record("a.pcap", fmt=DatasetFormat.PCAP),
        _record("b.csv", fmt=DatasetFormat.CSV),
    ]
    results = classifier.classify_batch(datasets)
    assert len(results) == 2
    assert results[0].format == DatasetFormat.PCAP
    assert results[1].format == DatasetFormat.CSV
