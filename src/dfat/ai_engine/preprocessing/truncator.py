"""Token-aware truncation for LLM prompt budgets."""

from __future__ import annotations


class TokenTruncator:
    """Truncate text to fit within an estimated token budget."""

    def __init__(self, max_tokens: int = 6000) -> None:
        """Initialise the truncator.

        Args:
            max_tokens: Maximum estimated tokens for the full prompt window.
        """
        self._max_tokens = max(1, max_tokens)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count as ``len(text) / 4`` (ceiling via integer math).

        Args:
            text: Input text.

        Returns:
            Estimated token count (0 for empty text).
        """
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)

    def truncate(self, text: str, reserve_tokens: int = 2000) -> str:
        """Truncate from the middle when text exceeds the usable budget.

        Preserves the start and end of ``text`` and inserts a marker::

            [...TRUNCATED {n} tokens...]

        Args:
            text: Full prompt payload.
            reserve_tokens: Tokens reserved for system prompt / completion.

        Returns:
            Original text when within budget; otherwise middle-truncated text.
        """
        budget = max(1, self._max_tokens - max(0, reserve_tokens))
        total = self.estimate_tokens(text)
        if total <= budget:
            return text

        # Allocate roughly half the budget to head and half to tail (in chars).
        # Marker is excluded from the kept sections.
        keep_chars = budget * 4
        head_chars = keep_chars // 2
        tail_chars = keep_chars - head_chars
        if head_chars <= 0 or tail_chars <= 0 or len(text) <= head_chars + tail_chars:
            return text[:keep_chars]

        head = text[:head_chars]
        tail = text[-tail_chars:]
        removed_tokens = max(0, total - budget)
        marker = f"\n[...TRUNCATED {removed_tokens} tokens...]\n"
        return f"{head}{marker}{tail}"
