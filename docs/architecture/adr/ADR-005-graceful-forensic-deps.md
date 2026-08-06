# ADR-005: Graceful Degradation on Library Absence

## Status
Accepted

## Context
Native forensic libraries (`pytsk3`, `volatility3`, `python-registry`, `python-evtx`) are heavy, platform-sensitive optional dependencies.

## Decision
Import forensic libraries lazily. On absence, raise clear `ImportError` messages or skip failing parsers rather than crashing the whole application at import time.

## Consequences
- Core package installs without `[forensic]` extras.
- `ForensicOrchestrator` logs parser failures and continues with remaining parsers.
- CLI/API remain usable for wiring, reporting, evaluation, and rule-based triage without forensic libs.
