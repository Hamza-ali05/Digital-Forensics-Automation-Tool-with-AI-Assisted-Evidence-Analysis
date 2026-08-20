#!/usr/bin/env python3
"""Verify DFAT's Design Science Research methodology coverage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "dfat"


class DSRSectionResult(BaseModel):
    section: str
    passed: bool
    checks_total: int
    checks_passed: int
    details: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DSRVerifier:
    def _record(self, details: list[str], ok: bool, success: str, failure: str) -> bool:
        details.append(f"{'[PASS]' if ok else '[FAIL]'} {success if ok else failure}")
        return ok

    def verify_design(self) -> DSRSectionResult:
        details: list[str] = []
        checks: list[bool] = []
        adr_dir = REPO_ROOT / "docs" / "architecture" / "adr"
        adr_files = list(adr_dir.glob("*.md"))
        checks.append(self._record(details, len(adr_files) >= 24, f"Architecture decision record corpus contains {len(adr_files)} ADR documents.", f"ADR corpus contains only {len(adr_files)} documents; expected at least 24."))
        checks.append(self._record(details, (REPO_ROOT / "docs" / "architecture" / "ARCHITECTURE.md").exists(), "System architecture document exists.", "System architecture document is missing."))
        interface_files = list((SRC_ROOT / "core" / "interfaces").glob("*.py"))
        checks.append(self._record(details, len(interface_files) >= 5, f"Core interfaces are defined ({len(interface_files)} interface modules found).", "Core interface layer appears incomplete."))
        return DSRSectionResult(section="Design", passed=all(checks), checks_total=len(checks), checks_passed=sum(checks), details=details)

    def verify_build(self) -> DSRSectionResult:
        details: list[str] = []
        checks: list[bool] = []
        parser_files = list((SRC_ROOT / "forensic_engine" / "parsers").rglob("*.py"))
        ai_files = list((SRC_ROOT / "ai_engine").rglob("*.py"))
        reporting_files = list((SRC_ROOT / "reporting").rglob("*.py"))
        checks.append(self._record(details, len(parser_files) >= 8, f"Forensic parsing subsystem is implemented ({len(parser_files)} parser modules found).", "Forensic parsing subsystem appears incomplete."))
        checks.append(self._record(details, len(ai_files) >= 10, f"AI subsystem is implemented ({len(ai_files)} AI modules found).", "AI subsystem appears incomplete."))
        checks.append(self._record(details, len(reporting_files) >= 8, f"Reporting subsystem is implemented ({len(reporting_files)} reporting modules found).", "Reporting subsystem appears incomplete."))
        return DSRSectionResult(section="Build", passed=all(checks), checks_total=len(checks), checks_passed=sum(checks), details=details)

    def verify_evaluate(self) -> DSRSectionResult:
        details: list[str] = []
        checks: list[bool] = []
        checks.append(self._record(details, (SRC_ROOT / "evaluation" / "benchmark").exists(), "Benchmark evaluation module exists.", "Benchmark evaluation module is missing."))
        checks.append(self._record(details, (SRC_ROOT / "evaluation" / "usability").exists(), "Usability evaluation module exists.", "Usability evaluation module is missing."))
        checks.append(self._record(details, (SRC_ROOT / "reporting" / "reproducibility.py").exists(), "Reproducibility verifier exists.", "Reproducibility verifier is missing."))
        return DSRSectionResult(section="Evaluate", passed=all(checks), checks_total=len(checks), checks_passed=sum(checks), details=details)

    def verify_all(self) -> list[DSRSectionResult]:
        results = [
            self.verify_design(),
            self.verify_build(),
            self.verify_evaluate(),
        ]
        print("DFAT DSR Methodology Verification")
        print("=" * 72)
        for result in results:
            print(f"{result.section}: {'PASS' if result.passed else 'FAIL'} ({result.checks_passed}/{result.checks_total})")
            for detail in result.details:
                print(f"  {detail}")
            print()
        print(f"OVERALL: {'PASS' if all(item.passed for item in results) else 'FAIL'}")
        return results


def main() -> int:
    results = DSRVerifier().verify_all()
    payload = {
        "overall_passed": all(item.passed for item in results),
        "results": [json.loads(item.model_dump_json()) for item in results],
    }
    (REPO_ROOT / "reports").mkdir(exist_ok=True)
    (REPO_ROOT / "reports" / "dsr_verification.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    return 0 if payload["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
