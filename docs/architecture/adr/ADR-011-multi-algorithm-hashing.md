# ADR-011: Multi-Algorithm Hashing

## Status
Accepted

## Context
Single-algorithm integrity checks (SHA-256 via `shared.hashing`) are necessary
but insufficient for defence-in-depth forensic verification. Investigators and
court processes commonly expect MD5 and SHA-1 alongside SHA-256 for cross-tool
interoperability, while still treating SHA-256 as the primary hash.

## Decision
Add `MultiHashService` that computes MD5 + SHA-1 + SHA-256 in a **single
read-only file pass**, returning a `HashSet`. Verification compares all three
digests and raises `IntegrityVerificationError` with per-algorithm mismatch
details. The existing `shared.hashing` helpers remain untouched and continue to
serve Prompt 1 acquisition paths.

Evidence validation, custody recording, and integrity verification APIs consume
`MultiHashService` / `HashSet` without writing digests back to evidence files.

## Consequences
- Additional CPU cost is bounded by one sequential read (no triple I/O).
- Progress callbacks support large-image UX without loading files into memory.
- Stored metadata mirrors all three digests for later re-verification.
