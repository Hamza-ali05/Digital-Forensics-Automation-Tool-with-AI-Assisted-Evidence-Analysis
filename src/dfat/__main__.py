"""DFAT CLI Entry — Command-line interface for pipeline invocation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dfat import __version__
from dfat.container import ApplicationContainer
from dfat.core.enums import EvidenceType
from dfat.core.exceptions import DFATError
from dfat.core.models.evidence import CaseMetadata
from dfat.core.validators import validate_file_extension, SUPPORTED_DISK_EXTENSIONS


def _build_parser() -> argparse.ArgumentParser:
    """Build the DFAT CLI argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="dfat",
        description=(
            "DFAT — Digital Forensics Automation Tool with "
            "AI-Assisted Evidence Analysis"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional path to a YAML configuration file or config directory",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=None,
        help="Path to forensic evidence image or memory dump",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for reports and audit artefacts",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "parse-only", "triage-only", "evaluate"],
        default="full",
        help="Pipeline execution mode",
    )
    parser.add_argument(
        "--case-name",
        default="CLI Case",
        help="Case name for the pipeline run",
    )
    parser.add_argument(
        "--investigator",
        default="dfat-cli",
        help="Investigator name recorded in case metadata",
    )
    parser.add_argument(
        "--use-fallback",
        action="store_true",
        help="Force rule-based AI triage fallback",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose console logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"dfat {__version__}",
    )
    return parser


def _print_banner(mode: str, verbose: bool) -> None:
    """Print the DFAT startup banner.

    Args:
        mode: Selected pipeline mode.
        verbose: Whether verbose mode is enabled.
    """
    print("=" * 64)
    print(" DFAT — Digital Forensics Automation Tool")
    print(f" Version : {__version__}")
    print(f" Mode    : {mode}")
    print(f" Verbose : {verbose}")
    print(" Pipeline: Acquisition -> Parsing -> AI Triage -> Reporting -> Evaluation")
    print("=" * 64)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument list override for testing.

    Returns:
        Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    container = ApplicationContainer()
    if args.config is not None:
        container.config.from_dict({"config_path": str(args.config)})
    container.logging.setup_app_logging()

    _print_banner(mode=args.mode, verbose=args.verbose)
    if args.evidence is not None:
        print(f"Evidence : {args.evidence}")
    if args.output is not None:
        print(f"Output   : {args.output}")

    if args.evidence is None:
        print("No --evidence path provided. Use --help for usage.")
        return 0

    evidence_path = Path(args.evidence)
    if not evidence_path.exists():
        print(f"Evidence path not found: {evidence_path}", file=sys.stderr)
        return 1

    case = CaseMetadata(
        case_name=args.case_name,
        investigator=args.investigator,
        description="Created via DFAT CLI",
    )
    orchestrator = container.pipeline.pipeline_orchestrator()

    try:
        if args.mode == "parse-only":
            artefact_set = orchestrator.run_parse_only(evidence_path, case)
            print(f"Parse complete: {artefact_set.total_count} artefacts")
            return 0
        if args.mode == "triage-only":
            artefact_set = orchestrator.run_parse_only(evidence_path, case)
            ranked = orchestrator.run_triage_only(
                artefact_set,
                use_fallback=args.use_fallback or True,
            )
            print(f"Triage complete: {len(ranked)} ranked artefacts")
            return 0
        if args.mode == "evaluate":
            print("Evaluate mode requires a prior parse and ground-truth path via API.")
            return 1

        # Default: full pipeline with forced fallback for offline CLI friendliness.
        use_fallback = args.use_fallback or True
        if validate_file_extension(evidence_path, SUPPORTED_DISK_EXTENSIONS):
            evidence_hint = EvidenceType.DISK_IMAGE
        else:
            evidence_hint = EvidenceType.MEMORY_DUMP
        if args.verbose:
            print(f"Evidence type hint: {evidence_hint.value}")
            print(f"Using fallback triage: {use_fallback}")

        report = orchestrator.run_full_pipeline(
            evidence_path,
            case,
            use_fallback=use_fallback,
        )
        print(f"Pipeline complete. Report ID: {report.report_id}")
        print(f"Duration: {report.pipeline_duration_seconds:.2f}s")
        return 0
    except DFATError as exc:
        print(f"DFAT error: {exc.message}", file=sys.stderr)
        if args.verbose and exc.context:
            print(f"Context: {exc.context}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        # Graceful handling when optional forensic libraries are missing.
        print(f"Pipeline failed (graceful): {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
