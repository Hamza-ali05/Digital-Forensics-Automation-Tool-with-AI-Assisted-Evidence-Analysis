# ADR-013: Lazy Forensic Library Imports

## Status
Accepted

## Context
Forensic libraries (`pytsk3`, `volatility3`, `python-registry`, `python-evtx`)
are optional, large, and platform-sensitive. Eager imports at module load time
would prevent the system from starting, running tests, or operating without all
libraries installed.

## Decision
Forensic libraries are optional runtime dependencies imported inside method
bodies (lazy imports), not at module top level:

- `BaseParser._safe_import()` uses `importlib.import_module` with a helpful
  install hint on `ImportError`.
- Concrete parsers import native deps only from `_do_parse` (or helpers it calls).
- `ParserRegistry` probes availability via `is_available()` or test-imports
  (`_PARSER_LIBRARY_PROBES`) without requiring libraries at process start.

This allows the system to start, run tests, and operate in degraded mode without
all libraries installed.

## Consequences
- Core install (`pip install -e ".[dev]"`) does not require `[forensic]` extras.
- Missing libraries surface as clear `ImportError` / `ParserStatus.UNAVAILABLE`
  rather than import-time crashes (see ADR-005, ADR-014).
- Parser unit tests mock accessors / `PluginExecutor` without native binaries.
