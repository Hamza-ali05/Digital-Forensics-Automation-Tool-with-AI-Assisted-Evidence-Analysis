"""Classification prompt construction for local LLM artefact triage."""

from __future__ import annotations

from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.optimization import PromptOptimizer
from dfat.ai_engine.preprocessing.batcher import ArtefactBatcher
from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.core.models.artefact import Artefact


class ClassificationPromptBuilder:
    """Build classification prompts from artefacts, including batched prompts."""

    def __init__(
        self,
        templates: ForensicPromptTemplates,
        serializer: ArtefactSerializer,
        batcher: ArtefactBatcher,
        optimizer: PromptOptimizer | None = None,
        max_prompt_tokens: int = 6000,
    ) -> None:
        """Initialise the prompt builder.

        Args:
            templates: Versioned forensic prompt templates.
            serializer: Artefact text serializer.
            batcher: Token-budget artefact batcher.
            optimizer: Context-window prompt optimizer.
            max_prompt_tokens: Token budget applied after rendering.
        """
        self._templates = templates
        self._serializer = serializer
        self._batcher = batcher
        self._optimizer = optimizer or PromptOptimizer()
        self._max_prompt_tokens = max(1, max_prompt_tokens)

    def build_prompt(self, artefacts: list[Artefact]) -> str:
        """Build a single classification prompt for ``artefacts``.

        Args:
            artefacts: Artefacts to classify.

        Returns:
            Rendered classification prompt string.
        """
        artefact_text = self._serializer.serialize_for_classification(artefacts)
        prompt = self._templates.render(
            "classification",
            artefact_text=artefact_text,
        )
        return self._optimizer.optimize_for_context_window(
            prompt,
            self._max_prompt_tokens,
        )

    def build_batched_prompts(self, artefacts: list[Artefact]) -> list[str]:
        """Split artefacts into batches and build one prompt per batch.

        Args:
            artefacts: Full artefact list.

        Returns:
            List of rendered prompts (empty when ``artefacts`` is empty).
        """
        return [prompt for _, prompt in self.iter_batches(artefacts)]

    def iter_batches(
        self,
        artefacts: list[Artefact],
    ) -> list[tuple[list[Artefact], str]]:
        """Return ``(batch, prompt)`` pairs that respect the token budget.

        Args:
            artefacts: Full artefact list.

        Returns:
            Ordered batch/prompt pairs.
        """
        if not artefacts:
            return []
        batches = self._batcher.create_batches(artefacts)
        return [(batch, self.build_prompt(batch)) for batch in batches if batch]
