"""Prompt construction helpers that fit local LLaMA-3 context windows.

Truncation keeps the system prompt and task instructions intact and drops
artefact payload from the least-suspicious end of the list first (CRITICAL
is retained preferentially over INFORMATIONAL).
"""

from __future__ import annotations

import re
from typing import Literal

from dfat.ai_engine.llm.config import FORENSIC_SYSTEM_PROMPT
from dfat.ai_engine.preprocessing.truncator import TokenTruncator
from dfat.core.enums import SuspicionLevel

TaskKind = Literal["classification", "summarization"]

_LEVEL_RANK: dict[str, int] = {
    SuspicionLevel.CRITICAL.value: 0,
    SuspicionLevel.HIGH.value: 1,
    SuspicionLevel.MEDIUM.value: 2,
    SuspicionLevel.LOW.value: 3,
    SuspicionLevel.INFORMATIONAL.value: 4,
}

_LEVEL_PATTERN = re.compile(
    r"(?:suspicion(?:_level)?|classified as)\s*[:=]?\s*"
    r"(CRITICAL|HIGH|MEDIUM|LOW|INFORMATIONAL)",
    re.IGNORECASE,
)

_ARTEFACT_SPLIT = re.compile(r"(?=^\[)", re.MULTILINE)

_ARTEFACT_SECTION_MARKERS = (
    "\nArtefacts:\n",
    "\nArtefacts:\r\n",
    "\nKey Artefacts:\n",
    "\nKey Artefacts:\r\n",
    "\n=== HIGH / CRITICAL DETAIL ===\n",
)

_END_MARKER = "---END---"


class PromptOptimizer:
    """Trim forensic LLM prompts so they fit a token budget."""

    def __init__(self, truncator: TokenTruncator | None = None) -> None:
        """Initialise the optimizer.

        Args:
            truncator: Optional token estimator; defaults to ``chars / 4``.
        """
        self._truncator = truncator or TokenTruncator()

    def estimate_tokens(self, text: str) -> int:
        """Estimate tokens for ``text`` via the shared truncator heuristic."""
        return self._truncator.estimate_tokens(text)

    def estimate_response_tokens(
        self,
        prompt_tokens: int,
        task: TaskKind = "classification",
    ) -> int:
        """Estimate completion size from the prompt token count.

        Heuristic: ``prompt_tokens * 0.5`` for classification and
        ``prompt_tokens * 0.3`` for summarization.

        Args:
            prompt_tokens: Estimated tokens in the prompt.
            task: Prompt family (``classification`` or ``summarization``).

        Returns:
            Non-negative estimated response tokens.
        """
        ratio = 0.3 if task == "summarization" else 0.5
        return max(0, int(prompt_tokens * ratio))

    def optimize_for_context_window(self, prompt: str, max_tokens: int) -> str:
        """Truncate ``prompt`` so its estimated tokens are ``<= max_tokens``.

        The forensic system prompt (when present) and task instructions are
        kept in full. Artefact records are dropped from the least-suspicious
        end until the budget fits. A single oversized artefact is tail-trimmed.

        Args:
            prompt: Full rendered prompt (instructions plus artefact data).
            max_tokens: Context-window budget in estimated tokens.

        Returns:
            Prompt that fits the budget, or the preserved instruction prefix
            when artefact data cannot be included.
        """
        budget = max(1, int(max_tokens))
        if self.estimate_tokens(prompt) <= budget:
            return prompt

        header, body, footer = self._split_prompt(prompt)
        prefix = header
        suffix = footer
        if self.estimate_tokens(prefix + suffix) >= budget:
            # Instructions exceed the window: still preserve them entirely.
            return prefix + suffix if (prefix or suffix) else prompt[: budget * 4]

        blocks = self._parse_artefact_blocks(body)
        kept = list(blocks)
        assembled = self._join(prefix, kept, suffix)
        while kept and self.estimate_tokens(assembled) > budget:
            drop_index = self._least_suspicious_bottom_index(kept)
            del kept[drop_index]
            assembled = self._join(prefix, kept, suffix)

        if self.estimate_tokens(assembled) <= budget:
            return assembled

        if kept:
            kept[0] = self._tail_trim_block(kept[0], prefix, suffix, budget)
            assembled = self._join(prefix, kept, suffix)
        return assembled if self.estimate_tokens(assembled) <= budget else prefix + suffix

    def _split_prompt(self, prompt: str) -> tuple[str, str, str]:
        """Split into instruction header, artefact body, and trailing footer."""
        text = prompt
        footer = ""
        end_at = text.rfind(_END_MARKER)
        if end_at >= 0:
            footer = text[end_at:]
            text = text[:end_at]

        header = text
        body = ""
        marker_at = -1
        marker_len = 0
        for marker in _ARTEFACT_SECTION_MARKERS:
            found = text.find(marker)
            if found >= 0 and (marker_at < 0 or found < marker_at):
                marker_at = found
                marker_len = len(marker)

        if marker_at >= 0:
            header = text[: marker_at + marker_len]
            body = text[marker_at + marker_len :]
        else:
            first_artefact = text.find("\n[")
            if first_artefact >= 0:
                header = text[: first_artefact + 1]
                body = text[first_artefact + 1 :]
            elif text.lstrip().startswith("["):
                header = self._instruction_prefix(text)
                body = text[len(header) :]
            else:
                body = ""

        if prompt.startswith(FORENSIC_SYSTEM_PROMPT) and FORENSIC_SYSTEM_PROMPT not in header:
            header = FORENSIC_SYSTEM_PROMPT + "\n" + header
        return header, body, footer

    @staticmethod
    def _instruction_prefix(text: str) -> str:
        """Return leading instruction lines before the first artefact block."""
        match = re.search(r"^\[", text, flags=re.MULTILINE)
        if match is None or match.start() == 0:
            return ""
        return text[: match.start()]

    def _parse_artefact_blocks(self, body: str) -> list[tuple[int, str]]:
        """Return ``(suspicion_rank, block_text)`` in original order."""
        if not body.strip():
            return []
        pieces = [part for part in _ARTEFACT_SPLIT.split(body) if part.strip()]
        if not pieces:
            return [(4, body)] if body.strip() else []
        blocks: list[tuple[int, str]] = []
        for piece in pieces:
            blocks.append((self._suspicion_rank(piece), piece))
        return blocks

    @staticmethod
    def _suspicion_rank(block: str) -> int:
        """Map a block to a 0–4 suspicion rank (CRITICAL=0)."""
        match = _LEVEL_PATTERN.search(block)
        if match:
            return _LEVEL_RANK.get(match.group(1).lower(), 4)
        lowered = block.lower()
        for name, rank in _LEVEL_RANK.items():
            if f" {name}" in lowered or f"={name}" in lowered or name in lowered:
                return rank
        return 4

    @staticmethod
    def _least_suspicious_bottom_index(blocks: list[tuple[int, str]]) -> int:
        """Index of the last block among those with the highest (worst) rank."""
        worst = max(item[0] for item in blocks)
        for index in range(len(blocks) - 1, -1, -1):
            if blocks[index][0] == worst:
                return index
        return len(blocks) - 1

    @staticmethod
    def _join(header: str, blocks: list[tuple[int, str]], footer: str) -> str:
        """Reassemble a prompt from kept artefact blocks."""
        body = "".join(text for _, text in blocks)
        return f"{header}{body}{footer}"

    def _tail_trim_block(
        self,
        block: tuple[int, str],
        header: str,
        footer: str,
        budget: int,
    ) -> tuple[int, str]:
        """Trim a single oversized artefact block from the tail."""
        rank, text = block
        overhead = self.estimate_tokens(header + footer)
        keep_tokens = max(1, budget - overhead)
        keep_chars = keep_tokens * 4
        first_line, _, rest = text.partition("\n")
        marker = "\n[...truncated to fit context window...]\n"
        available = max(len(first_line) + 1, keep_chars - len(marker))
        trimmed = (first_line + "\n" + rest)[:available].rstrip() + marker
        return (rank, trimmed)
