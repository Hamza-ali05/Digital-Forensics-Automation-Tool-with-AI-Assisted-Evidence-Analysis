"""Unit tests for PromptOptimizer context-window truncation."""

from __future__ import annotations

from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.optimization import PromptOptimizer


def test_estimate_response_tokens_by_task() -> None:
    optimizer = PromptOptimizer()
    assert optimizer.estimate_response_tokens(100) == 50
    assert optimizer.estimate_response_tokens(100, task="classification") == 50
    assert optimizer.estimate_response_tokens(100, task="summarization") == 30


def test_optimize_preserves_instructions_and_prefers_critical() -> None:
    templates = ForensicPromptTemplates()
    padding = "x" * 400
    artefact_text = "\n".join(
        [
            f"[art-info] filesystem_metadata | detail={padding} suspicion_level=informational",
            f"[art-low] browser_history | detail={padding} suspicion_level=low",
            f"[art-crit] injected_code | detail={padding} suspicion_level=critical",
            f"[art-high] network_connection | detail={padding} suspicion_level=high",
        ]
    )
    prompt = templates.render("classification", artefact_text=artefact_text)
    optimizer = PromptOptimizer()
    original_tokens = optimizer.estimate_tokens(prompt)
    fitted = optimizer.optimize_for_context_window(prompt, max_tokens=280)

    assert optimizer.estimate_tokens(fitted) <= 280 < original_tokens
    assert "Do not fabricate" in fitted
    assert "---END---" in fitted
    assert "[art-crit]" in fitted
    assert "[art-info]" not in fitted


def test_optimize_noop_when_within_budget() -> None:
    optimizer = PromptOptimizer()
    prompt = ForensicPromptTemplates().render(
        "classification",
        artefact_text="[a1] filesystem_metadata | path=/tmp/a",
    )
    assert optimizer.optimize_for_context_window(prompt, max_tokens=8000) == prompt
