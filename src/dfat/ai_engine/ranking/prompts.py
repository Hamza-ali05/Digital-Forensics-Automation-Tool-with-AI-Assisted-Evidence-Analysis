"""Ranking prompt construction for local LLM relevance scoring."""

from __future__ import annotations

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.core.models.artefact import Artefact


class RankingPromptBuilder:
    """Build ranking prompts from classified artefacts."""

    def __init__(
        self,
        templates: ForensicPromptTemplates | None = None,
        serializer: ArtefactSerializer | None = None,
    ) -> None:
        """Initialise the ranking prompt builder.

        Args:
            templates: Versioned forensic prompt templates.
            serializer: Artefact text serializer.
        """
        self._templates = templates or ForensicPromptTemplates()
        self._serializer = serializer or ArtefactSerializer()

    def build_prompt(
        self,
        classified: list[ClassificationResult],
        artefacts: list[Artefact],
    ) -> str:
        """Render ``RANKING_TEMPLATE`` with classified artefact context.

        Args:
            classified: Classification outcomes (suspicion + reasoning).
            artefacts: Source artefacts for raw_data context.

        Returns:
            Rendered ranking prompt string.
        """
        by_id = {item.artefact_id: item for item in artefacts}
        lines: list[str] = []
        for result in classified:
            artefact = by_id.get(result.artefact_id)
            header = (
                f"[{result.artefact_id}] "
                f"suspicion={result.suspicion_level.value} "
                f"confidence={result.confidence:.2f}"
            )
            lines.append(header)
            lines.append(f"  classification_reasoning: {result.reasoning}")
            if result.ioc_indicators:
                lines.append(
                    "  ioc_indicators: " + ", ".join(result.ioc_indicators)
                )
            if artefact is not None:
                lines.append(f"  category: {artefact.category.value}")
                if artefact.source_path:
                    lines.append(f"  source_path: {artefact.source_path}")
                for key, value in sorted(artefact.raw_data.items()):
                    lines.append(
                        f"  {key}: {self._serializer._format_value(value)}"
                    )
            lines.append("")

        artefact_text = "\n".join(lines).rstrip()
        return self._templates.render("ranking", artefact_text=artefact_text)
