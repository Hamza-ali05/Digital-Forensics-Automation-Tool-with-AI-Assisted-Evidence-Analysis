"""Write structured JSON reports to disk with post-write integrity checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dfat.core.exceptions import IntegrityVerificationError
from dfat.core.models.report import JSONReport
from dfat.reporting.integrity import ReportIntegrityVerifier


class JSONFileExporter:
    """Persist ``JSONReport`` / raw report documents as pretty-printed JSON files."""

    def __init__(
        self,
        integrity_verifier: ReportIntegrityVerifier | None = None,
    ) -> None:
        """Initialise the JSON file exporter.

        Args:
            integrity_verifier: Optional verifier used after writes. Defaults to
                a new ``ReportIntegrityVerifier``.
        """
        self._verifier = integrity_verifier or ReportIntegrityVerifier()

    def export(self, json_report: JSONReport, output_dir: Path) -> Path:
        """Write the JSON report to a ``.json`` file and verify integrity.

        Args:
            json_report: In-memory structured JSON report.
            output_dir: Destination directory.

        Returns:
            Path to the written JSON file.

        Raises:
            IntegrityVerificationError: If the on-disk integrity hash check fails.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"dfat_json_{json_report.report_id[:8]}.json"
        document = {
            "schema_version": json_report.schema_version,
            "report_id": json_report.report_id,
            "evidence_id": json_report.evidence_id,
            "generated_at": json_report.generated_at.isoformat(),
            "integrity_hash": json_report.integrity_hash,
            "artefacts": list(json_report.artefact_data),
        }
        return self.export_raw(document, path)

    def export_raw(self, report_data: dict[str, Any], output_path: Path) -> Path:
        """Write an arbitrary report document and verify its integrity hash.

        Args:
            report_data: Full report document (must include ``artefacts`` /
                ``artefact_data`` and ``integrity_hash`` for verification).
            output_path: Exact destination file path.

        Returns:
            ``output_path`` after a successful write and verification.

        Raises:
            IntegrityVerificationError: If recomputed hash does not match.
            TypeError: If ``report_data`` is not a mapping.
        """
        if not isinstance(report_data, dict):
            raise TypeError("report_data must be a JSON object (dict)")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report_data, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )

        loaded = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise TypeError(f"Written file {output_path} is not a JSON object")

        # Ensure in-memory and on-disk payloads match structurally.
        if json.dumps(loaded, sort_keys=True, default=str) != json.dumps(
            report_data, sort_keys=True, default=str
        ):
            raise IntegrityVerificationError(
                f"On-disk JSON does not match in-memory report data: {output_path}",
                expected_hash=str(report_data.get("integrity_hash") or ""),
                actual_hash="",
                context={"path": str(output_path)},
            )

        result = self._verifier.verify_report(loaded)
        if not result.integrity_hash_match:
            raise IntegrityVerificationError(
                f"Integrity hash verification failed after writing {output_path}",
                expected_hash=str(loaded.get("integrity_hash") or ""),
                actual_hash="",
                context={
                    "path": str(output_path),
                    "issues": list(result.issues),
                },
            )
        return output_path
