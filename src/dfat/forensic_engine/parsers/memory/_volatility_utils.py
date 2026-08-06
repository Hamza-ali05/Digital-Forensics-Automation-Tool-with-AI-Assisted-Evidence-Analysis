"""Shared Volatility3 helpers for memory artefact parsers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator


def require_volatility3() -> None:
    """Ensure volatility3 is importable.

    Raises:
        ImportError: If ``volatility3`` is not installed.
    """
    try:
        import volatility3  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "volatility3 is required for memory artefact parsing. Install with: "
            "pip install volatility3"
        ) from exc


def iter_plugin_rows(dump_path: Path, plugin_name: str) -> Iterator[dict[str, Any]]:
    """Run a Volatility3 Windows plugin and yield row dictionaries.

    Args:
        dump_path: Path to the memory dump.
        plugin_name: Fully-qualified plugin class path
            (e.g. ``windows.pslist.PsList``).

    Yields:
        Dictionaries representing plugin output rows.

    Raises:
        ImportError: If volatility3 is unavailable.
        RuntimeError: If plugin construction/execution fails.
    """
    require_volatility3()
    try:
        from volatility3.framework import automagic, contexts, plugins
    except ImportError as exc:
        raise ImportError(
            "volatility3 is required for memory artefact parsing. Install with: "
            "pip install volatility3"
        ) from exc

    ctx = contexts.Context()
    single_location = "file:" + dump_path.resolve().as_posix()
    ctx.config["automagic.LayerStacker.single_location"] = single_location

    plugin_class = _resolve_plugin_class(plugin_name, plugins)
    config_path = "plugins." + plugin_class.__name__
    automagics = automagic.available(ctx)

    try:
        constructed = plugins.construct_plugin(
            ctx,
            automagics,
            plugin_class,
            config_path,
            None,
            None,
        )
        treegrid = constructed.run()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Volatility3 plugin '{plugin_name}' failed: {exc}"
        ) from exc

    rows: list[dict[str, Any]] = []

    def _visitor(node: Any, accumulator: list[dict[str, Any]]) -> None:
        values = getattr(node, "values", ())
        if not values:
            return
        row: dict[str, Any] = {}
        for index, value in enumerate(values):
            row[f"col_{index}"] = value
        # Prefer named columns when TreeGrid exposes them.
        columns = getattr(getattr(treegrid, "columns", None), "__iter__", None)
        if columns is not None:
            try:
                for column, value in zip(treegrid.columns, values, strict=False):
                    name = getattr(column, "name", None) or str(column)
                    row[name] = value
            except Exception:  # noqa: BLE001
                pass
        accumulator.append(row)

    try:
        treegrid.populate(_visitor, rows)
    except Exception:
        for node in getattr(treegrid, "children", []) or []:
            _visitor(node, rows)
    yield from rows


def _resolve_plugin_class(plugin_name: str, plugins_mod: Any) -> Any:
    """Resolve a Volatility plugin class by dotted name.

    Args:
        plugin_name: Dotted plugin path.
        plugins_mod: Imported ``volatility3.framework.plugins`` module.

    Returns:
        Plugin class object.

    Raises:
        RuntimeError: If the plugin cannot be resolved.
    """
    getter = getattr(plugins_mod, "get_plugin", None)
    if callable(getter):
        try:
            return getter(plugin_name)
        except Exception:  # noqa: BLE001
            pass

    module_path, _, class_name = plugin_name.rpartition(".")
    if not module_path:
        raise RuntimeError(f"Invalid Volatility plugin name: {plugin_name}")
    try:
        module = __import__(
            f"volatility3.plugins.{module_path}",
            fromlist=[class_name],
        )
        return getattr(module, class_name)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Unable to load Volatility3 plugin '{plugin_name}': {exc}"
        ) from exc
