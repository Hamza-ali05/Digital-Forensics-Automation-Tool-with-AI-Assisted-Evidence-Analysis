# DFAT Five-Stage Forensic Pipeline

This document describes the end-to-end evidence processing pipeline: stages,
parsers, `Artefact.raw_data` contracts, configuration, and error handling.

Related:

- API reference: [`docs/api/PIPELINE_API.md`](../api/PIPELINE_API.md)
- ADRs: [013](adr/ADR-013-parser-lazy-imports.md)–[016](adr/ADR-016-rule-based-triage-first.md)

## Stage overview

```text
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ 1.Acquire   │──▶│ 2.Parsing   │──▶│ 3.AI Triage │──▶│ 4.Reporting │──▶│ 5.Evaluate  │
│ acquisition │   │ parsing     │   │ ai_triage   │   │ reporting   │   │ evaluation  │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
       │                 │                 │                 │                 │
  validate hash    disk + memory     rule-first +      dual JSON +         DFRWS /
  custody→ACQUIRED parsers →         optional LLM      narrative           CFReDS metrics
                   ArtefactSet       ranked triage     ForensicReport
```

| Stage | Enum value | Responsibility |
|-------|------------|----------------|
| 1 Acquisition | `acquisition` | Load evidence metadata, verify integrity hashes, advance chain-of-custody to acquired/processing states |
| 2 Parsing | `parsing` | Route evidence type to registered parsers; emit normalised `ArtefactSet` |
| 3 AI Triage | `ai_triage` | Correlate, timeline, IOC detect, score; rule-based triage first, LLM when available |
| 4 Reporting | `reporting` | Persist dual-output forensic report (JSON evidential + narrative) |
| 5 Evaluation | `evaluation` | Optional benchmark metrics against ground truth (non-blocking on failure) |

Job modes:

| Mode | Stages run |
|------|------------|
| `full` | 1 → 5 |
| `parse-only` | Acquisition + Parsing |
| `triage-only` | Assumes artefacts available; runs triage (+ reporting when configured) |

Orchestration lives in `PipelineOrchestrator` (`src/dfat/pipeline/orchestrator.py`).
Stages implement `IPipelineStage` and share a `PipelineContext`.

## Parsers

Parsers implement `IArtefactParser` via `BaseParser`. Registration and availability
checks use `ParserRegistry` (`src/dfat/pipeline/parser_registry.py`).

### Disk image parsers (`EvidenceType.DISK_IMAGE`)

| Parser | Category | Primary libraries |
|--------|----------|-------------------|
| `FileSystemParser` | `FILESYSTEM_METADATA` | `pytsk3` |
| `RegistryParser` | `REGISTRY_KEY` | `pytsk3`, `python-registry` |
| `BrowserHistoryParser` | `BROWSER_HISTORY` | `pytsk3`, stdlib `sqlite3` |
| `EventLogParser` | `EVENT_LOG` | `pytsk3`, `python-evtx` |

### Memory dump parsers (`EvidenceType.MEMORY_DUMP`)

| Parser | Category | Primary libraries |
|--------|----------|-------------------|
| `ProcessListParser` | `RUNNING_PROCESS` | Volatility3 `pslist` / `pstree` |
| `NetworkArtefactParser` | `NETWORK_CONNECTION` | Volatility3 `netscan` |
| `CodeInjectionParser` | `INJECTED_CODE` | Volatility3 `malfind` |
| `MemoryRegistryParser` | `REGISTRY_KEY` | Volatility3 registry plugins |

Native forensic libraries are optional (`pip install -e ".[forensic]"`). Missing
dependencies mark a parser **unavailable** without aborting the whole process
(see [ADR-014](adr/ADR-014-graceful-parser-degradation.md)).

## `raw_data` schema contracts

Every `Artefact` carries a category-specific `raw_data` dict. Contracts are the
source of truth for frontend and report consumers
([ADR-015](adr/ADR-015-artefact-raw-data-contracts.md)).

### `FILESYSTEM_METADATA`

```json
{
  "filename": "string",
  "path": "string",
  "size": 0,
  "created_time": "ISO-8601 | null",
  "modified_time": "ISO-8601 | null",
  "accessed_time": "ISO-8601 | null",
  "changed_time": "ISO-8601 | null",
  "is_deleted": false,
  "is_allocated": true,
  "file_type": "file | directory | deleted | unknown",
  "inode": 0
}
```

### `REGISTRY_KEY`

```json
{
  "hive_name": "string",
  "key_path": "string",
  "value_name": "string",
  "value_data": "string",
  "value_type": "string",
  "last_modified": "ISO-8601 | null"
}
```

### `BROWSER_HISTORY`

```json
{
  "url": "string",
  "title": "string",
  "visit_count": 0,
  "last_visit_time": "ISO-8601 | null",
  "browser_type": "chrome | firefox | edge",
  "profile": "string"
}
```

### `EVENT_LOG`

```json
{
  "event_id": 0,
  "timestamp": "ISO-8601 | null",
  "channel": "string | null",
  "source": "string | null",
  "level": "string | null",
  "computer_name": "string | null",
  "message": "string",
  "event_data": {},
  "is_security_relevant": false
}
```

### `RUNNING_PROCESS`

```json
{
  "pid": 0,
  "ppid": 0,
  "name": "string",
  "create_time": "ISO-8601 | null",
  "exit_time": "ISO-8601 | null",
  "session_id": null,
  "handles": null,
  "threads": null,
  "wow64": null,
  "command_line": "string | null",
  "parent_name": "string | null"
}
```

### `NETWORK_CONNECTION`

```json
{
  "protocol": "string",
  "local_address": "string",
  "local_port": null,
  "remote_address": "string",
  "remote_port": null,
  "state": "string",
  "pid": null,
  "owner_process": "string | null",
  "created_time": "ISO-8601 | null",
  "is_external": false
}
```

### `INJECTED_CODE`

```json
{
  "pid": 0,
  "process_name": "string",
  "vad_start": "0x...",
  "vad_end": "0x...",
  "vad_tag": "string",
  "protection": "string",
  "hex_dump_preview": "string",
  "disassembly_preview": "string | null",
  "suspicious_indicators": ["MZ header", "shellcode patterns", "RWX memory region"]
}
```

## Configuration reference

Settings nest under `pipeline:` in YAML (`config/default.yaml`) and map to
`PipelineSettings` (`src/dfat/settings.py`). Override with
`DFAT_PIPELINE__<KEY>` environment variables.

| Key | Default | Description |
|-----|---------|-------------|
| `max_concurrent_jobs` | `1` | In-process concurrency cap for pipeline jobs |
| `stage_timeout_seconds` | `600` | Per-stage wall-clock timeout |
| `parser_timeout_seconds` | `300` | Per-parser timeout |
| `max_artefacts_per_category` | `10000` | Truncation cap per category / parse |
| `enable_artefact_correlation` | `true` | Cross-artefact correlation during triage |
| `enable_timeline_generation` | `true` | Build temporal timeline from timestamps |
| `enable_ioc_detection` | `true` | Run IOC detectors before scoring |
| `volatility_plugins_timeout` | `300` | Volatility plugin execution timeout |
| `enable_memory_registry` | `true` | Include `MemoryRegistryParser` when available |

Related AI / fallback knobs live under `ai_engine:` (e.g. `enable_fallback`).

## Error handling strategy

`PipelineErrorHandler` converts failures into recoverable outcomes instead of
crashing the job whenever possible.

### Parser level

- Missing optional libraries → `ParserStatus.UNAVAILABLE` (`ParserUnavailableError`).
- Runtime parse failure → `ParserStatus.FAILED`.
- Remaining parsers continue; partial `ArtefactSet` is assembled from successes.

### Stage abort policy

| Stage | On failure |
|-------|------------|
| Acquisition | Abort — no evidence to process |
| Parsing | Abort only if **zero** artefacts recovered; otherwise continue with partial results |
| AI triage | Continue — force / use rule-based fallback ([ADR-016](adr/ADR-016-rule-based-triage-first.md)) |
| Reporting | Abort — no deliverable without a report |
| Evaluation | Continue — metrics are optional |

### Job statuses

`queued` → `initialising` → `running` → `completed` | `failed` | `cancelled` | `timed_out`

API clients poll `GET /api/v1/pipeline/{job_id}/progress` for
`percent_complete`, `current_stage`, and `artefacts_found_so_far`.

## Frontend integration notes

1. Submit with `POST /api/v1/pipeline/run` → `202` + `PipelineJob`.
2. Poll progress until `status` is terminal.
3. Use `GET /api/v1/pipeline/parsers` to disable UI actions for unavailable parsers.
4. Render artefact detail panels from the `raw_data` contracts above (stable keys).
5. Prefer JSON report endpoints for structured UI; narrative is secondary display.
