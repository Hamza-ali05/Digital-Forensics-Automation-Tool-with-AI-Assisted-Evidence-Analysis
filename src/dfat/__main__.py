"""DFAT CLI Entry — Command-line interface for pipeline invocation."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dfat import __version__
from dfat.container import build_application_container
from dfat.core.enums import EvidenceType
from dfat.core.exceptions import DFATError
from dfat.core.validators import SUPPORTED_DISK_EXTENSIONS, validate_file_extension
from dfat.pipeline.enums import JobStatus


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


async def _run_pipeline(args: argparse.Namespace) -> int:
    """Register evidence and execute the job-based pipeline."""
    container = build_application_container()
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

    if args.mode == "evaluate":
        print("Evaluate mode requires a prior parse and ground-truth path via API.")
        return 1

    engine = container.database.database_engine()
    await engine.create_tables()

    if validate_file_extension(evidence_path, SUPPORTED_DISK_EXTENSIONS):
        evidence_type = EvidenceType.DISK_IMAGE
    else:
        evidence_type = EvidenceType.MEMORY_DUMP

    use_fallback = bool(args.use_fallback) or True
    if args.verbose:
        print(f"Evidence type hint: {evidence_type.value}")
        print(f"Using fallback triage: {use_fallback}")

    evidence_service = container.services.evidence_service()
    evidence = await evidence_service.register_evidence(
        file_path=evidence_path,
        case_name=args.case_name,
        investigator=args.investigator,
        evidence_type=evidence_type,
        description="Created via DFAT CLI",
        user_id="cli",
    )

    orchestrator = container.pipeline.pipeline_orchestrator()
    mode = args.mode
    if mode == "triage-only":
        # Ensure artefacts exist before triage-only stage.
        parse_job = await orchestrator.execute_pipeline(
            evidence_id=evidence.evidence_id,
            case_id=evidence.case.case_id,
            user_id="cli",
            mode="parse-only",
            use_fallback=use_fallback,
        )
        if parse_job.status is not JobStatus.COMPLETED:
            print(
                f"Parse failed before triage: {parse_job.error_message}",
                file=sys.stderr,
            )
            return 1

    job = await orchestrator.execute_pipeline(
        evidence_id=evidence.evidence_id,
        case_id=evidence.case.case_id,
        user_id="cli",
        mode=mode,
        use_fallback=use_fallback,
    )

    if job.status is not JobStatus.COMPLETED:
        print(
            f"Pipeline failed: {job.error_message or job.status.value}",
            file=sys.stderr,
        )
        return 1

    if mode == "parse-only":
        artefact_set = orchestrator.get_job_artefact_set(job.job_id)
        count = artefact_set.total_count if artefact_set is not None else 0
        print(f"Parse complete: {count} artefacts")
        return 0

    if mode == "triage-only":
        artefact_set = orchestrator.get_job_artefact_set(job.job_id)
        ranked = orchestrator._job_contexts.get(job.job_id)  # noqa: SLF001
        ranked_count = (
            len(ranked.ranked_artefacts)
            if ranked is not None and ranked.ranked_artefacts is not None
            else (artefact_set.total_count if artefact_set else 0)
        )
        print(f"Triage complete: {ranked_count} ranked artefacts")
        return 0

    report = orchestrator.get_job_report(job.job_id)
    if report is None:
        print(f"Pipeline complete (job {job.job_id}) but no report was produced.")
        return 0
    print(f"Pipeline complete. Report ID: {report.report_id}")
    print(f"Duration: {report.pipeline_duration_seconds:.2f}s")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument list override for testing.

    Returns:
        Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        return asyncio.run(_run_pipeline(args))
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
