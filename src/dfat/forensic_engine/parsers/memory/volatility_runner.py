"""Volatility3 framework integration for memory dump plugin execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from dfat.core.enums import PipelineStage
from dfat.core.exceptions import MemoryParsingError
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger


class VolatilityRunner:
    """Abstraction over Volatility3 for running forensic plugins.

    Lazy-imports ``volatility3`` modules and configures optional symbol
    table paths from settings.
    """

    def __init__(
        self,
        symbols_path: Optional[Path],
        audit_logger: ForensicAuditLogger,
    ) -> None:
        """Initialise the Volatility3 runner.

        Args:
            symbols_path: Optional directory of Volatility symbol tables.
            audit_logger: ACPO-compliant forensic audit logger.
        """
        self._symbols_path = Path(symbols_path) if symbols_path is not None else None
        self._audit_logger = audit_logger

    def is_available(self) -> bool:
        """Return ``True`` when the ``volatility3`` package can be imported."""
        try:
            import volatility3  # noqa: F401
        except ImportError:
            return False
        return True

    def _init_context(self, memory_path: Path) -> Any:
        """Build a Volatility3 context for ``memory_path``.

        Configures:
            * Automagic modules for OS detection
            * Optional symbol table path from settings
            * Memory file as ``single_location``

        Args:
            memory_path: Path to the memory dump file.

        Returns:
            Constructed Volatility3 ``Context`` instance.

        Raises:
            ImportError: If ``volatility3`` is not installed.
            MemoryParsingError: If context construction fails.
        """
        try:
            from volatility3.framework import automagic, constants, contexts
        except ImportError as exc:
            raise ImportError(
                "volatility3 is required for memory artefact parsing. Install with: "
                "pip install volatility3"
            ) from exc

        try:
            if self._symbols_path is not None:
                symbols = str(self._symbols_path.resolve())
                if symbols not in constants.SYMBOL_BASEPATHS:
                    constants.SYMBOL_BASEPATHS.insert(0, symbols)

            ctx = contexts.Context()
            single_location = "file:" + Path(memory_path).resolve().as_posix()
            ctx.config["automagic.LayerStacker.single_location"] = single_location
            # Ensure automagics are discoverable for later plugin construction.
            _ = automagic.available(ctx)
            return ctx
        except ImportError:
            raise
        except Exception as exc:  # noqa: BLE001 — bridge framework errors
            raise MemoryParsingError(
                f"Failed to initialise Volatility3 context for {memory_path}",
                context={"path": str(memory_path), "error": str(exc)},
            ) from exc

    def run_plugin(
        self,
        memory_path: Path,
        plugin_class_name: str,
        plugin_module: str,
        config: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Run a Volatility3 plugin and return flat row dictionaries.

        Args:
            memory_path: Path to the memory dump.
            plugin_class_name: Plugin class name (e.g. ``PsList``).
            plugin_module: Fully-qualified module path
                (e.g. ``volatility3.plugins.windows.pslist``).
            config: Optional plugin configuration values applied under
                ``plugins.<plugin_class_name>.*`` before construction
                (e.g. ``{\"offset\": 0x1a000, \"recurse\": True}``).

        Returns:
            List of flat dictionaries derived from the plugin TreeGrid.

        Raises:
            ImportError: If ``volatility3`` is not installed.
            MemoryParsingError: If plugin import/execution fails.
        """
        try:
            from volatility3.framework import automagic, plugins
        except ImportError as exc:
            raise ImportError(
                "volatility3 is required for memory artefact parsing. Install with: "
                "pip install volatility3"
            ) from exc

        path = Path(memory_path)
        ctx = self._init_context(path)
        try:
            module = __import__(plugin_module, fromlist=[plugin_class_name])
            plugin_class = getattr(module, plugin_class_name)
        except Exception as exc:  # noqa: BLE001
            raise MemoryParsingError(
                f"Unable to load Volatility3 plugin "
                f"{plugin_module}.{plugin_class_name}",
                context={
                    "plugin_module": plugin_module,
                    "plugin_class_name": plugin_class_name,
                    "error": str(exc),
                },
            ) from exc

        config_path = f"plugins.{plugin_class_name}"
        if config:
            for key, value in config.items():
                ctx.config[f"{config_path}.{key}"] = value
        try:
            automagics = automagic.available(ctx)
            constructed = plugins.construct_plugin(
                ctx,
                automagics,
                plugin_class,
                config_path,
                None,
                None,
            )
            treegrid = constructed.run()
            rows = self._treegrid_to_dicts(treegrid)
        except MemoryParsingError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MemoryParsingError(
                f"Volatility3 plugin '{plugin_class_name}' failed: {exc}",
                context={
                    "path": str(path),
                    "plugin_module": plugin_module,
                    "plugin_class_name": plugin_class_name,
                    "error": str(exc),
                },
            ) from exc

        self._audit_logger.log_action(
            stage=PipelineStage.PARSING,
            action="VOLATILITY_PLUGIN_EXECUTED",
            evidence_id="system",
            details={
                "path": str(path),
                "plugin_module": plugin_module,
                "plugin_class_name": plugin_class_name,
                "row_count": len(rows),
                "config_keys": sorted(config.keys()) if config else [],
            },
        )
        return rows

    def _treegrid_to_dicts(self, grid: Any) -> list[dict[str, Any]]:
        """Convert a Volatility3 ``TreeGrid`` into a list of flat dicts.

        Args:
            grid: Plugin ``TreeGrid`` (or compatible) output.

        Returns:
            Flat row dictionaries with named columns when available.
        """
        rows: list[dict[str, Any]] = []
        columns = list(getattr(grid, "columns", []) or [])

        def _visitor(node: Any, accumulator: list[dict[str, Any]]) -> None:
            values = getattr(node, "values", ())
            if not values:
                return
            row: dict[str, Any] = {}
            for index, value in enumerate(values):
                row[f"col_{index}"] = self._render_cell(value)
            if columns:
                try:
                    for column, value in zip(columns, values, strict=False):
                        name = getattr(column, "name", None) or str(column)
                        row[str(name)] = self._render_cell(value)
                except Exception:  # noqa: BLE001 — keep positional keys
                    pass
            accumulator.append(row)

        try:
            populate = getattr(grid, "populate", None)
            if callable(populate):
                populate(_visitor, rows)
            else:
                for node in getattr(grid, "children", []) or []:
                    _visitor(node, rows)
        except Exception as exc:  # noqa: BLE001
            raise MemoryParsingError(
                f"Failed to convert Volatility3 TreeGrid output: {exc}",
                context={"error": str(exc)},
            ) from exc
        return rows

    @staticmethod
    def _render_cell(value: Any) -> Any:
        """Render Volatility UnreadableValue / NotApplicableValue as ``None``."""
        type_name = type(value).__name__
        if type_name in {
            "UnreadableValue",
            "NotApplicableValue",
            "NotAvailableValue",
            "RenderType",
        }:
            return None
        return value
