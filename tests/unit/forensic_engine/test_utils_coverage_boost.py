"""Coverage boost for forensic_engine utils with mocked pytsk3/volatility3."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from dfat.core.enums import ArtefactCategory
from dfat.core.exceptions import DiskParsingError, MemoryParsingError
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.parsers._tsk_utils import (
    find_files,
    iter_directory,
    meta_timestamp,
    open_filesystem,
    open_image,
    read_file_bytes,
    require_pytsk3,
    walk_filesystem,
)
from dfat.forensic_engine.parsers.disk_access import DiskImageAccessor
from dfat.forensic_engine.parsers.memory._volatility_utils import (
    _resolve_plugin_class,
    iter_plugin_rows,
    require_volatility3,
)
from dfat.forensic_engine.parsers.memory.volatility_runner import VolatilityRunner
from dfat.forensic_engine.processing.relationship_mapper import RelationshipMapper
from dfat.forensic_engine.processing.standardiser import ArtefactStandardiser


def _make_entry(name: bytes, *, is_dir: bool, addr: int = 1, nest: bool = True):
    meta = SimpleNamespace(
        type=1 if is_dir else 0,
        TYPE_DIR=1,
        size=10,
        addr=addr,
        flags=0,
        crtime=1700000000,
        mtime=1700000001,
        atime=0,
        ctime=None,
    )
    child = []
    if is_dir and nest:
        child = [_make_entry(b"nested.bin", is_dir=False, addr=addr + 10, nest=False)]
    entry = SimpleNamespace(
        info=SimpleNamespace(name=SimpleNamespace(name=name), meta=meta),
        as_directory=MagicMock(return_value=child),
    )
    return entry


def _install_fake_pytsk3(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    fake = ModuleType("pytsk3")

    class Img_Info:
        def __init__(self, path: str) -> None:
            self.path = path

        def close(self) -> None:
            self.closed = True

    class FS_Info:
        def __init__(self, img, offset: int = 0) -> None:
            self.img = img
            self.offset = offset

        def open_dir(self, path: str = "/"):
            return [
                _make_entry(b"file.txt", is_dir=False, addr=1),
                _make_entry(b"subdir", is_dir=True, addr=2),
            ]

        def open(self, path: str):
            return SimpleNamespace(
                info=SimpleNamespace(meta=SimpleNamespace(size=4)),
                read_random=lambda offset, size: b"data",
            )

        def open_meta(self, inode: int):
            return SimpleNamespace(
                info=SimpleNamespace(meta=SimpleNamespace(size=3)),
                read_random=lambda offset, size: b"abc",
            )

    class Volume_Info:
        def __init__(self, img) -> None:
            self.info = SimpleNamespace(block_size=512)

        def __iter__(self):
            yield SimpleNamespace(flags=1, start=0, len=100)

    fake.Img_Info = Img_Info
    fake.FS_Info = FS_Info
    fake.Volume_Info = Volume_Info
    fake.TSK_VS_PART_FLAG_ALLOC = 1
    monkeypatch.setitem(sys.modules, "pytsk3", fake)
    return fake


# --- _tsk_utils ---


def test_require_pytsk3_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pytsk3", None)
    real_import = __import__

    def _import(name, *args, **kwargs):
        if name == "pytsk3":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_import):
        with pytest.raises(ImportError, match="pytsk3"):
            require_pytsk3()


def test_tsk_utils_open_walk_read_find(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_pytsk3(monkeypatch)
    img_path = tmp_path / "disk.dd"
    img_path.write_bytes(b"x")

    img = open_image(img_path)
    fs = open_filesystem(img, offset=0)
    entries = list(iter_directory(fs, fs.open_dir(path="/"), "/"))
    assert any(path.endswith("file.txt") for path, _ in entries)

    walked = list(walk_filesystem(img_path))
    assert walked

    data = read_file_bytes(fs, "/file.txt")
    assert data == b"data"

    found = find_files(img_path, lambda p: p.endswith(".txt"), limit=5)
    assert found and found[0][1] == b"data"

    # skip dirs / non-matching / error on read
    find_files(img_path, lambda p: False, limit=1)

    entry = _make_entry(b"x", is_dir=False)
    assert meta_timestamp(entry, "crtime") is not None
    assert meta_timestamp(entry, "atime") is None
    assert meta_timestamp(SimpleNamespace(info=SimpleNamespace(meta=None)), "mtime") is None
    assert meta_timestamp(SimpleNamespace(info=SimpleNamespace(meta=object())), "bad") is None


def test_iter_directory_skips_dot_and_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_pytsk3(monkeypatch)
    bad_dir = SimpleNamespace(
        info=SimpleNamespace(
            name=SimpleNamespace(name=b"bad"),
            meta=SimpleNamespace(type=1, TYPE_DIR=1),
        ),
        as_directory=MagicMock(side_effect=RuntimeError("nope")),
    )
    dots = [
        SimpleNamespace(info=SimpleNamespace(name=SimpleNamespace(name=b"."), meta=None)),
        SimpleNamespace(info=SimpleNamespace(name=SimpleNamespace(name=b".."), meta=None)),
        bad_dir,
    ]
    assert list(iter_directory(MagicMock(), dots, "/"))


# --- volatility utils ---


def test_require_volatility3_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = __import__

    def _import(name, *args, **kwargs):
        if name == "volatility3" or name.startswith("volatility3"):
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_import):
        with pytest.raises(ImportError, match="volatility3"):
            require_volatility3()


def test_resolve_plugin_class_success_and_failure() -> None:
    plugins = SimpleNamespace(get_plugin=MagicMock(return_value="CLS"))
    assert _resolve_plugin_class("windows.pslist.PsList", plugins) == "CLS"

    plugins_fail = SimpleNamespace(get_plugin=MagicMock(side_effect=RuntimeError("x")))
    with pytest.raises(RuntimeError, match="Invalid Volatility"):
        _resolve_plugin_class("NoDots", plugins_fail)

    with pytest.raises(RuntimeError, match="Unable to load"):
        _resolve_plugin_class("windows.missing.Missing", SimpleNamespace())


def test_iter_plugin_rows_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dump = tmp_path / "mem.raw"
    dump.write_bytes(b"mem")

    class FakePlugin:
        def run(self):
            grid = MagicMock()
            col = SimpleNamespace(name="PID")
            grid.columns = [col]

            def populate(visitor, rows):
                visitor(SimpleNamespace(values=(1,)), rows)

            grid.populate = populate
            return grid

    contexts = SimpleNamespace(Context=MagicMock(return_value=SimpleNamespace(config={})))
    automagic = SimpleNamespace(available=MagicMock(return_value=[]))
    plugins = SimpleNamespace(
        get_plugin=MagicMock(return_value=FakePlugin),
        construct_plugin=MagicMock(return_value=FakePlugin()),
    )

    vol = ModuleType("volatility3")
    framework = ModuleType("volatility3.framework")
    monkeypatch.setitem(sys.modules, "volatility3", vol)
    monkeypatch.setitem(sys.modules, "volatility3.framework", framework)
    monkeypatch.setitem(sys.modules, "volatility3.framework.contexts", contexts)
    monkeypatch.setitem(sys.modules, "volatility3.framework.automagic", automagic)
    monkeypatch.setitem(sys.modules, "volatility3.framework.plugins", plugins)

    rows = list(iter_plugin_rows(dump, "windows.pslist.PsList"))
    assert rows and rows[0]["PID"] == 1


def test_iter_plugin_rows_construct_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dump = tmp_path / "mem.raw"
    dump.write_bytes(b"mem")
    contexts = SimpleNamespace(Context=MagicMock(return_value=SimpleNamespace(config={})))
    automagic = SimpleNamespace(available=MagicMock(return_value=[]))
    plugins = SimpleNamespace(
        get_plugin=MagicMock(return_value=object),
        construct_plugin=MagicMock(side_effect=RuntimeError("fail")),
    )
    monkeypatch.setitem(sys.modules, "volatility3", ModuleType("volatility3"))
    monkeypatch.setitem(sys.modules, "volatility3.framework", ModuleType("volatility3.framework"))
    monkeypatch.setitem(sys.modules, "volatility3.framework.contexts", contexts)
    monkeypatch.setitem(sys.modules, "volatility3.framework.automagic", automagic)
    monkeypatch.setitem(sys.modules, "volatility3.framework.plugins", plugins)
    with pytest.raises(RuntimeError, match="failed"):
        list(iter_plugin_rows(dump, "windows.pslist.PsList"))


# --- DiskImageAccessor ---


def test_disk_image_accessor_methods(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_pytsk3(monkeypatch)
    audit = MagicMock()
    accessor = DiskImageAccessor(audit)
    img_path = tmp_path / "disk.E01"
    img_path.write_bytes(b"img")

    img = accessor.open_image(img_path)
    fs = accessor.get_filesystem(img, offset=0)
    entries = list(accessor.walk_filesystem(fs, path="/", max_depth=2))
    assert entries
    content = accessor.extract_file_content(fs, inode=1)
    assert content == b"abc"
    out = accessor.extract_file_to_temp(fs, inode=1, dest_dir=tmp_path / "out")
    assert out is not None and out.exists()
    assert accessor.extract_file_content(fs, inode=1, max_size=1) is None
    accessor.close(img)
    audit.log_action.assert_called()

    # volume fallback path when offset 0 FS open fails
    with patch.object(accessor, "_open_fs_at", side_effect=[DiskParsingError("x"), MagicMock()]):
        accessor.get_filesystem(img, offset=0)

    with pytest.raises(DiskParsingError):
        with patch.object(
            accessor,
            "_require_pytsk3",
            return_value=SimpleNamespace(
                Img_Info=MagicMock(side_effect=RuntimeError("bad"))
            ),
        ):
            accessor.open_image(img_path)


# --- standardiser / relationship mapper ---


def test_artefact_standardiser_and_relationship_mapper() -> None:
    a1 = Artefact(
        artefact_id="a1",
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev",
        raw_data={
            "CreateTime": 1700000000,
            "ImagePath": "C:\\Windows\\evil.exe",
            " NestedKey ": "  value  ",
            "blob": b"bytes",
            "items": [{"Path": "/tmp/x"}],
            "none": None,
        },
        source_path="C:\\Windows\\evil.exe",
        metadata={},
    )
    a2 = Artefact(
        artefact_id="a2",
        category=ArtefactCategory.NETWORK_CONNECTION,
        source_evidence_id="ev",
        raw_data={"pid": 1},
        metadata={"correlated_artefact_ids": ["a1", "missing", "a2"]},
    )
    a3 = Artefact(
        artefact_id="a3",
        category=ArtefactCategory.REGISTRY_KEY,
        source_evidence_id="ev",
        raw_data={},
        metadata={"correlated_artefact_ids": "not-a-list"},
    )
    aset = ArtefactSet(
        evidence_id="ev",
        artefacts=[a1, a2, a3],
        categories_present=[
            ArtefactCategory.RUNNING_PROCESS,
            ArtefactCategory.NETWORK_CONNECTION,
            ArtefactCategory.REGISTRY_KEY,
        ],
    )
    standardised = ArtefactStandardiser().standardise(aset)
    assert standardised.artefacts[0].metadata["standardised"] is True
    assert "create_time" in standardised.artefacts[0].raw_data

    rel = RelationshipMapper().build_map(aset)
    assert rel.total_relationships >= 1
    assert any(c for c in rel.clusters if "a1" in c and "a2" in c)


# --- volatility_runner ---


def test_volatility_runner_available_and_treegrid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit = MagicMock()
    runner = VolatilityRunner(symbols_path=tmp_path / "symbols", audit_logger=audit)
    monkeypatch.setitem(sys.modules, "volatility3", ModuleType("volatility3"))
    assert runner.is_available() is True

    # is_available false
    real_import = __import__

    def _import(name, *args, **kwargs):
        if name == "volatility3":
            raise ImportError("x")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_import):
        assert VolatilityRunner(None, audit).is_available() is False

    grid = MagicMock()
    grid.columns = [SimpleNamespace(name="PID")]

    def populate(visitor, rows):
        visitor(SimpleNamespace(values=(SimpleNamespace(__class__=type("UnreadableValue", (), {})),)), rows)
        visitor(SimpleNamespace(values=(42,)), rows)

    grid.populate = populate
    rows = runner._treegrid_to_dicts(grid)
    assert any(r.get("PID") == 42 for r in rows)

    # children fallback
    grid2 = MagicMock(spec=[])
    grid2.columns = []
    grid2.children = [SimpleNamespace(values=("x",))]
    assert runner._treegrid_to_dicts(grid2)

    with pytest.raises(MemoryParsingError):
        bad = MagicMock()
        bad.columns = []
        bad.populate = MagicMock(side_effect=RuntimeError("bad grid"))
        runner._treegrid_to_dicts(bad)


def test_volatility_runner_init_and_run_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dfat.core.enums import HashAlgorithm
    from dfat.core.models.evidence import CaseMetadata, EvidenceImage, MemoryDump

    audit = MagicMock()
    symbols = tmp_path / "symbols"
    symbols.mkdir()
    runner = VolatilityRunner(symbols_path=symbols, audit_logger=audit)
    dump = tmp_path / "mem.raw"
    dump.write_bytes(b"memory")

    constants = SimpleNamespace(SYMBOL_BASEPATHS=[])
    contexts = SimpleNamespace(Context=MagicMock(return_value=SimpleNamespace(config={})))
    automagic = SimpleNamespace(available=MagicMock(return_value=["auto"]))
    framework = ModuleType("volatility3.framework")
    monkeypatch.setitem(sys.modules, "volatility3", ModuleType("volatility3"))
    monkeypatch.setitem(sys.modules, "volatility3.framework", framework)
    monkeypatch.setitem(sys.modules, "volatility3.framework.constants", constants)
    monkeypatch.setitem(sys.modules, "volatility3.framework.contexts", contexts)
    monkeypatch.setitem(sys.modules, "volatility3.framework.automagic", automagic)

    ctx = runner._init_context(dump)
    assert "automagic.LayerStacker.single_location" in ctx.config

    class Plugin:
        def run(self):
            grid = MagicMock()
            grid.columns = [SimpleNamespace(name="PID")]

            def populate(visitor, rows):
                visitor(SimpleNamespace(values=(7,)), rows)

            grid.populate = populate
            return grid

    plugin_mod = ModuleType("fake.plugins.pslist")
    plugin_mod.PsList = Plugin
    monkeypatch.setitem(sys.modules, "fake.plugins.pslist", plugin_mod)
    plugins = SimpleNamespace(
        construct_plugin=MagicMock(return_value=Plugin()),
    )
    monkeypatch.setitem(sys.modules, "volatility3.framework.plugins", plugins)
    rows = runner.run_plugin(dump, "PsList", "fake.plugins.pslist", config={"offset": 1})
    assert rows and rows[0]["PID"] == 7

    with pytest.raises(MemoryParsingError):
        runner.run_plugin(dump, "Missing", "fake.plugins.missing")


def test_deduplicator_aggregator_handlers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from dfat.core.enums import HashAlgorithm, SuspicionLevel
    from dfat.core.models.artefact import RankedArtefact
    from dfat.core.models.evidence import CaseMetadata, EvidenceImage, MemoryDump
    from dfat.forensic_engine.acquisition.image_handler import DiskImageHandler
    from dfat.forensic_engine.acquisition.memory_handler import MemoryDumpHandler
    from dfat.forensic_engine.processing.deduplicator import ArtefactDeduplicator
    from dfat.forensic_engine.processing.ioc_detector import IOCMatch
    from dfat.forensic_engine.processing.timeline import Timeline
    from dfat.forensic_engine.triage.aggregator import TriageAggregator

    a1 = Artefact(
        artefact_id="d1",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        source_evidence_id="ev",
        raw_data={"path": "/a", "tags": {"b", "a"}, "blob": b"\x00\x01", "cat": ArtefactCategory.FILESYSTEM_METADATA},
    )
    a2 = Artefact(
        artefact_id="d2",
        category=ArtefactCategory.FILESYSTEM_METADATA,
        source_evidence_id="ev",
        raw_data={"path": "/a", "tags": {"b", "a"}, "blob": b"\x00\x01", "cat": ArtefactCategory.FILESYSTEM_METADATA},
    )
    aset = ArtefactSet(
        evidence_id="ev",
        artefacts=[a1, a2],
        categories_present=[ArtefactCategory.FILESYSTEM_METADATA],
    )
    deduped = ArtefactDeduplicator().deduplicate(aset)
    assert deduped.total_count == 1
    ArtefactDeduplicator().deduplicate(
        ArtefactSet(evidence_id="ev", artefacts=[a1], categories_present=[])
    )

    ranked = [
        RankedArtefact(
            artefact_id="r1",
            category=ArtefactCategory.RUNNING_PROCESS,
            source_evidence_id="ev",
            raw_data={"process_name": "evil.exe"},
            suspicion_level=SuspicionLevel.CRITICAL,
            relevance_score=0.99,
            classification_reasoning="x" * 300,
            source_path="/evil",
        ),
        RankedArtefact(
            artefact_id="r2",
            category=ArtefactCategory.NETWORK_CONNECTION,
            source_evidence_id="ev",
            raw_data={},
            suspicion_level=SuspicionLevel.HIGH,
            relevance_score=0.5,
        ),
        RankedArtefact(
            artefact_id="r3",
            category=ArtefactCategory.BROWSER_HISTORY,
            source_evidence_id="ev",
            raw_data={"url": "http://x"},
            suspicion_level=SuspicionLevel.LOW,
            relevance_score=0.1,
        ),
    ]
    now = datetime.now(UTC)
    timeline = Timeline(entries=[], windows=[], earliest=now, latest=now)
    summary = TriageAggregator().aggregate(
        ranked,
        timeline,
        [
            IOCMatch(
                artefact_id="r1",
                ioc_type="process",
                indicator="evil.exe",
                confidence="high",
                description="bad",
                matched_rule="r1",
            )
        ],
    )
    assert summary.total_artefacts == 3
    assert summary.ioc_count == 1
    assert summary.timeline_range is not None
    empty_tl = Timeline(entries=[], windows=[], earliest=None, latest=None)
    assert TriageAggregator().aggregate([], empty_tl, []).timeline_range is None

    # handlers
    _install_fake_pytsk3(monkeypatch)
    integrity = MagicMock()
    integrity.compute_initial_hash = MagicMock(return_value="a" * 64)
    integrity.verify_integrity = MagicMock(return_value=True)
    integrity.hash_algorithm = HashAlgorithm.SHA256
    audit = MagicMock()
    storage = MagicMock(base_dir=tmp_path)
    disk = DiskImageHandler(integrity, audit, storage)
    case = CaseMetadata(case_id="c", case_name="C", investigator="I")
    img_path = tmp_path / "disk.dd"
    img_path.write_bytes(b"diskdata")
    evidence = disk.load_image(img_path, case)
    handle = disk.open_image(evidence)
    disk.get_filesystem(handle)
    disk.close_image(handle)

    mem_path = tmp_path / "mem.raw"
    mem_path.write_bytes(b"memdata")
    mem_handler = MemoryDumpHandler(integrity, audit, storage, volatility_symbols_path=tmp_path)
    dump = mem_handler.load_dump(mem_path, case, volatility_profile="Win10x64")
    assert mem_handler.validate_dump(dump) is True
    ctx = mem_handler.get_volatility_context(dump)
    assert ctx["profile"] == "Win10x64"
