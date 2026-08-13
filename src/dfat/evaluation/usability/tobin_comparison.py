"""Tobin et al. (2021) usefulness benchmark comparison for RQ5."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TobinComparisonResult(BaseModel):
    """Outcome of comparing tool usefulness against Tobin et al. (2021)."""

    model_config = ConfigDict(frozen=False, validate_assignment=True)

    tool_percentage: float
    tobin_percentage: float = 74.0
    difference: float
    meets_benchmark: bool
    exceeds_benchmark: bool
    tool_sample_size: int = Field(ge=0)
    comparison_notes: str


class TobinComparison:
    """Compare observed usefulness percentage to Tobin et al. (2021)."""

    TOBIN_USEFULNESS_PERCENTAGE = 74.0  # From Tobin et al. (2021)
    TOBIN_SAMPLE_SIZE: Optional[int] = None  # Not specified in literature review

    def compare(
        self,
        tool_usefulness_pct: float,
        tool_sample_size: int,
    ) -> TobinComparisonResult:
        """Compare tool usefulness percentage against the Tobin benchmark.

        Args:
            tool_usefulness_pct: Observed usefulness percentage
                (respondents with avg(Q1, Q4) ≥ 4).
            tool_sample_size: Number of anonymised responses analysed.

        Returns:
            Structured comparison including difference and sample-size notes.
        """
        tool_pct = float(tool_usefulness_pct)
        difference = tool_pct - self.TOBIN_USEFULNESS_PERCENTAGE
        meets = tool_pct >= self.TOBIN_USEFULNESS_PERCENTAGE
        exceeds = tool_pct > self.TOBIN_USEFULNESS_PERCENTAGE

        notes: list[str] = []
        if exceeds:
            notes.append(
                "Tool usefulness percentage exceeds Tobin et al. (2021) "
                f"benchmark of {self.TOBIN_USEFULNESS_PERCENTAGE:.1f}%."
            )
        elif meets:
            notes.append(
                "Tool usefulness percentage meets Tobin et al. (2021) "
                f"benchmark of {self.TOBIN_USEFULNESS_PERCENTAGE:.1f}%."
            )
        else:
            notes.append(
                "Tool usefulness percentage falls below Tobin et al. (2021) "
                f"benchmark of {self.TOBIN_USEFULNESS_PERCENTAGE:.1f}%."
            )

        if self.TOBIN_SAMPLE_SIZE is None:
            notes.append(
                "Tobin et al. (2021) sample size is not specified in the "
                "literature review; interpret absolute percentage comparisons "
                "with caution."
            )
        if tool_sample_size < 30:
            notes.append(
                f"Tool sample size is small (n={tool_sample_size}); "
                "estimates may be unstable."
            )

        return TobinComparisonResult(
            tool_percentage=tool_pct,
            tobin_percentage=self.TOBIN_USEFULNESS_PERCENTAGE,
            difference=difference,
            meets_benchmark=meets,
            exceeds_benchmark=exceeds,
            tool_sample_size=int(tool_sample_size),
            comparison_notes=" ".join(notes),
        )
