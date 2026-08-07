"""Registry mapping ``PipelineStage`` values to executable stage handlers."""

from __future__ import annotations

from dfat.core.enums import PipelineStage
from dfat.pipeline.stage_interface import IPipelineStage

_FULL_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage.ACQUISITION,
    PipelineStage.PARSING,
    PipelineStage.AI_TRIAGE,
    PipelineStage.REPORTING,
    PipelineStage.EVALUATION,
)

_MODE_STAGES: dict[str, tuple[PipelineStage, ...]] = {
    "full": _FULL_ORDER,
    "parse-only": (
        PipelineStage.ACQUISITION,
        PipelineStage.PARSING,
    ),
    "triage-only": (PipelineStage.AI_TRIAGE,),
}


class StageRegistry:
    """Register and resolve ordered pipeline stage handlers by mode."""

    def __init__(self) -> None:
        """Initialise an empty stage registry."""
        self._stages: dict[PipelineStage, IPipelineStage] = {}

    def register(self, stage: IPipelineStage) -> None:
        """Register a stage handler, replacing any prior handler for that stage.

        Args:
            stage: Stage handler implementing ``IPipelineStage``.
        """
        self._stages[stage.stage_name] = stage

    def get(self, stage_name: PipelineStage) -> IPipelineStage:
        """Return the registered handler for ``stage_name``.

        Args:
            stage_name: Pipeline stage enum value.

        Returns:
            Registered stage handler.

        Raises:
            KeyError: If the stage is not registered.
        """
        if stage_name not in self._stages:
            raise KeyError(f"Pipeline stage not registered: {stage_name.value}")
        return self._stages[stage_name]

    def get_ordered_stages(self, mode: str = "full") -> list[IPipelineStage]:
        """Return registered stages in execution order for the given mode.

        Modes:
            ``full`` — all five stages in pipeline order.
            ``parse-only`` — acquisition and parsing only.
            ``triage-only`` — AI triage only.

        Args:
            mode: Pipeline run mode.

        Returns:
            Ordered list of registered stage handlers for the mode.

        Raises:
            ValueError: If ``mode`` is unknown.
            KeyError: If a required stage for the mode is not registered.
        """
        ordered = _MODE_STAGES.get(mode)
        if ordered is None:
            raise ValueError(
                f"Unknown pipeline mode: {mode!r}. "
                f"Expected one of {sorted(_MODE_STAGES)}"
            )
        return [self.get(stage_name) for stage_name in ordered]

    def list_registered(self) -> list[PipelineStage]:
        """Return registered stages in canonical pipeline order."""
        return [stage for stage in _FULL_ORDER if stage in self._stages]

    def is_registered(self, stage_name: PipelineStage) -> bool:
        """Return whether a handler is registered for ``stage_name``."""
        return stage_name in self._stages
