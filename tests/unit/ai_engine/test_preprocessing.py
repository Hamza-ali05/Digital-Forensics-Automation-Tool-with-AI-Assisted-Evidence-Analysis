"""Unit tests for AI engine artefact preprocessing."""

from __future__ import annotations

from dfat.ai_engine.preprocessing import (
    ArtefactBatcher,
    ArtefactSerializer,
    TokenTruncator,
)
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact


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


def test_serialize_artefact_includes_id_category_raw_data() -> None:
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
    assert "Category: network_connection" in text
    assert "local_port: 443" in text
    assert "protocol: tcp" in text
    assert "remote_address: 8.8.8.8" in text
    # Stable key ordering
    assert text.index("local_port") < text.index("protocol") < text.index("remote_address")


def test_serialize_artefact_set_prioritises_injected_code() -> None:
    serializer = ArtefactSerializer()
    artefacts = [
        _artefact(f"fs-{i}", ArtefactCategory.FILESYSTEM_METADATA)
        for i in range(5)
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
    assert "net-1" in text
    # Filesystem should be dropped first under the limit of 3
    fs_kept = sum(1 for i in range(5) if f"fs-{i}" in text)
    assert fs_kept <= 1


def test_truncation_preserves_start_and_end() -> None:
    truncator = TokenTruncator(max_tokens=100)
    head = "START_" + ("A" * 200)
    tail = ("Z" * 200) + "_END"
    text = head + ("M" * 4000) + tail
    result = truncator.truncate(text, reserve_tokens=50)
    assert result.startswith("START_")
    assert result.endswith("_END")
    assert "TRUNCATED" in result
    assert truncator.estimate_tokens(result) <= truncator.estimate_tokens(text)


def test_batches_respect_token_budget_and_category_grouping() -> None:
    serializer = ArtefactSerializer()
    batcher = ArtefactBatcher(max_tokens_per_batch=40, serializer=serializer)
    artefacts = [
        _artefact(
            f"inj-{i}",
            ArtefactCategory.INJECTED_CODE,
            process_name="malware.exe",
            protection="PAGE_EXECUTE_READWRITE",
            hex_dump_preview="90909090" * 8,
        )
        for i in range(6)
    ] + [
        _artefact(f"fs-{i}", ArtefactCategory.FILESYSTEM_METADATA, path=f"/tmp/{i}")
        for i in range(6)
    ]
    batches = batcher.create_batches(artefacts)
    assert batches
    for batch in batches:
        assert batcher.estimate_batch_tokens(batch) <= 40 or len(batch) == 1
    # First batch should prefer injected_code artefacts
    assert all(
        item.category is ArtefactCategory.INJECTED_CODE for item in batches[0]
    )


def test_serialize_for_summary_details_high_plus_only() -> None:
    serializer = ArtefactSerializer()
    ranked = [
        RankedArtefact(
            **_artefact("c1", ArtefactCategory.INJECTED_CODE).model_dump(),
            suspicion_level=SuspicionLevel.CRITICAL,
            relevance_score=0.95,
        ),
        RankedArtefact(
            **_artefact("l1", ArtefactCategory.BROWSER_HISTORY).model_dump(),
            suspicion_level=SuspicionLevel.LOW,
            relevance_score=0.1,
        ),
    ]
    text = serializer.serialize_for_summary(ranked)
    assert "c1" in text
    assert "suspicion_level: critical" in text
    assert "browser_history: 1" in text
    assert "[l1]" not in text
