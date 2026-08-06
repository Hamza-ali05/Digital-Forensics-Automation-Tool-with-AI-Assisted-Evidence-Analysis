"""DFAT CLI Entry — Command-line interface for pipeline invocation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dfat import __version__
from dfat.container import ApplicationContainer


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

    _print_banner(mode=args.mode, verbose=args.verbose)
    if args.evidence is not None:
        print(f"Evidence : {args.evidence}")
    if args.output is not None:
        print(f"Output   : {args.output}")

    print("Pipeline execution not yet implemented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
