"""Unit tests for HTML report exporter (Prompt 6.20 named suite)."""

from __future__ import annotations

from pathlib import Path

from tests.unit.reporting import test_html_json_exporters as html_tests


def test_self_contained_html(tmp_path: Path) -> None:
    """Verify HTML has inline CSS/JS and no external stylesheet/script URLs."""
    html_tests.test_html_export_is_self_contained(tmp_path)


def test_artefact_table_colour_coded(tmp_path: Path) -> None:
    """Verify findings table rows use suspicion colour CSS classes."""
    html_tests.test_html_artefact_table_colour_coding(tmp_path)


def test_json_file_integrity_verified(tmp_path: Path) -> None:
    """Verify JSON file matches in-memory data and integrity hash verifies."""
    html_tests.test_json_file_matches_memory_and_verifies(tmp_path)
