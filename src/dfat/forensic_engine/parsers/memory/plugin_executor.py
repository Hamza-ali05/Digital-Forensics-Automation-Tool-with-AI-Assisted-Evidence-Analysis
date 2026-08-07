"""Higher-level Volatility3 plugin execution with timeout and batch support."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from dfat.core.enums import PipelineStage
from dfat.core.exceptions import MemoryParsingError
from dfat.forensic_engine.parsers.memory.volatility_runner import VolatilityRunner
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)


class PluginExecutor:
    """Run Volatility3 plugins with timeout, audit logging, and batch isolation."""

    def __init__(
        self,
        volatility_runner: VolatilityRunner,
        audit_logger: ForensicAuditLogger,
        timeout_seconds: int = 300,
    ) -> None:
        """Initialise the plugin executor.

        Args:
            volatility_runner: Low-level Volatility3 runner.
            audit_logger: ACPO-compliant forensic audit logger.
            timeout_seconds: Per-plugin wall-clock timeout.
        """
        self._runner = volatility_runner
        self._audit_logger = audit_logger
        self._timeout_seconds = max(1, int(timeout_seconds))

    async def execute_plugin(
        self,
        memory_path: Path,
        plugin_name: str,
        plugin_module: str,
        evidence_id: str,
        config: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Run a single Volatility3 plugin with timeout protection.

        Args:
            memory_path: Path to the memory dump.
            plugin_name: Plugin class name (e.g. ``PsList``).
            plugin_module: Fully-qualified plugin module path.
            evidence_id: Evidence identifier for audit correlation.
            config: Optional plugin configuration forwarded to
                :meth:`VolatilityRunner.run_plugin`.

        Returns:
            Normalised list of row dictionaries from the plugin.

        Raises:
            MemoryParsingError: If the plugin fails or exceeds the timeout.
            ImportError: If ``volatility3`` is not installed.
        """
        path = Path(memory_path)
        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="VOLATILITY_PLUGIN_START",
            evidence_id=evidence_id,
            details={
                "path": str(path),
                "plugin_name": plugin_name,
                "plugin_module": plugin_module,
                "timeout_seconds": self._timeout_seconds,
                "config_keys": sorted(config.keys()) if config else [],
            },
        )
        try:
            rows = await asyncio.wait_for(
                asyncio.to_thread(
                    self._runner.run_plugin,
                    path,
                    plugin_name,
                    plugin_module,
                    config,
                ),
                timeout=float(self._timeout_seconds),
            )
        except TimeoutError as exc:
            self._audit_logger.log_action(
                stage=PipelineStage.PARSING,
                action="VOLATILITY_PLUGIN_TIMEOUT",
                evidence_id=evidence_id,
                details={
                    "path": str(path),
                    "plugin_name": plugin_name,
                    "plugin_module": plugin_module,
                    "timeout_seconds": self._timeout_seconds,
                },
            )
            raise MemoryParsingError(
                f"Volatility3 plugin '{plugin_name}' timed out after "
                f"{self._timeout_seconds}s",
                context={
                    "path": str(path),
                    "plugin_name": plugin_name,
                    "plugin_module": plugin_module,
                    "evidence_id": evidence_id,
                    "timeout_seconds": self._timeout_seconds,
                },
            ) from exc
        except ImportError:
            raise
        except MemoryParsingError:
            self._audit_logger.log_action(
                stage=PipelineStage.PARSING,
                action="VOLATILITY_PLUGIN_FAILED",
                evidence_id=evidence_id,
                details={
                    "path": str(path),
                    "plugin_name": plugin_name,
                    "plugin_module": plugin_module,
                },
            )
            raise
        except Exception as exc:  # noqa: BLE001 — normalise unexpected errors
            self._audit_logger.log_action(
                stage=PipelineStage.PARSING,
                action="VOLATILITY_PLUGIN_FAILED",
                evidence_id=evidence_id,
                details={
                    "path": str(path),
                    "plugin_name": plugin_name,
                    "plugin_module": plugin_module,
                    "error": str(exc),
                },
            )
            raise MemoryParsingError(
                f"Volatility3 plugin '{plugin_name}' failed: {exc}",
                context={
                    "path": str(path),
                    "plugin_name": plugin_name,
                    "plugin_module": plugin_module,
                    "evidence_id": evidence_id,
                    "error": str(exc),
                },
            ) from exc

        normalised = self._normalise_rows(rows)
        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="VOLATILITY_PLUGIN_END",
            evidence_id=evidence_id,
            details={
                "path": str(path),
                "plugin_name": plugin_name,
                "plugin_module": plugin_module,
                "row_count": len(normalised),
            },
        )
        return normalised

    async def execute_plugins_batch(
        self,
        memory_path: Path,
        plugins: list[tuple[str, str]],
        evidence_id: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """Run multiple plugins sequentially, isolating individual failures.

        Args:
            memory_path: Path to the memory dump.
            plugins: List of ``(plugin_name, plugin_module)`` pairs.
            evidence_id: Evidence identifier for audit correlation.

        Returns:
            Mapping of plugin name → row dictionaries. Failed plugins map to
            an empty list and do not abort the batch.
        """
        results: dict[str, list[dict[str, Any]]] = {}
        for plugin_name, plugin_module in plugins:
            try:
                results[plugin_name] = await self.execute_plugin(
                    memory_path,
                    plugin_name,
                    plugin_module,
                    evidence_id,
                )
            except Exception as exc:  # noqa: BLE001 — continue batch
                logger.warning(
                    "Volatility plugin %s failed during batch for %s: %s",
                    plugin_name,
                    evidence_id,
                    exc,
                )
                results[plugin_name] = []
        return results

    @staticmethod
    def _normalise_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ensure plugin output is a clean list of plain dictionaries."""
        normalised: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalised.append({str(key): value for key, value in row.items()})
        return normalised
