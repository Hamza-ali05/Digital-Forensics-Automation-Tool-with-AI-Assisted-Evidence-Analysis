"""Jinja2 forensic prompt templates for local LLaMA-3 triage.

PROMPT_VERSION is part of the evaluation methodology — changing templates
changes research results and must be documented in the dissertation.
"""

from __future__ import annotations

from typing import Any

from jinja2 import BaseLoader, Environment, StrictUndefined, TemplateError

PROMPT_VERSION = "1.0.0"

_CLASSIFICATION_PROMPT = """
{# PROMPT_VERSION {{ prompt_version }} #}
You are a digital forensics analyst. Classify each artefact by suspicion level.
Do NOT fabricate information. Mark uncertain inferences explicitly.
Known limitation: base LLaMA-3 may be less accurate than a fine-tuned forensic
model (Sharma et al., 2025). Prefer conservative ratings.

Suspicion levels (choose exactly one per artefact):
CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL

Return ONLY valid JSON with this schema:
{
  "classifications": [
    {
      "artefact_id": "<id>",
      "suspicion_level": "<LEVEL>",
      "relevance_score": <float 0.0-1.0>,
      "reasoning": "<brief evidence-based reason>"
    }
  ]
}

Artefacts:
{% for artefact in artefacts %}
- id: {{ artefact['artefact_id'] }}
  category: {{ artefact['category'] }}
  source_path: {{ artefact.get('source_path') }}
  raw_data: {{ artefact['raw_data'] }}
{% endfor %}
""".strip()

_RANKING_PROMPT = """
{# PROMPT_VERSION {{ prompt_version }} #}
You are a digital forensics analyst. Rank the classified artefacts by
investigative relevance. Do NOT fabricate information. Mark uncertain
inferences explicitly.

Return ONLY valid JSON with this schema:
{
  "rankings": [
    {
      "artefact_id": "<id>",
      "relevance_score": <float 0.0-1.0>,
      "reasoning": "<brief reason>"
    }
  ]
}
Order the array from most relevant to least relevant.

Classified artefacts:
{% for artefact in artefacts %}
- id: {{ artefact['artefact_id'] }}
  category: {{ artefact['category'] }}
  suspicion_level: {{ artefact.get('suspicion_level') }}
  relevance_score: {{ artefact.get('relevance_score') }}
  reasoning: {{ artefact.get('classification_reasoning') }}
  raw_data: {{ artefact['raw_data'] }}
{% endfor %}
""".strip()

_SUMMARY_PROMPT = """
{# PROMPT_VERSION {{ prompt_version }} #}
You are a digital forensics analyst. Produce an investigative summary for an
investigator. Do NOT fabricate facts not present in the artefacts. Clearly mark
uncertain inferences. Narrative output is advisory; structured JSON remains the
authoritative record (Scanlon et al., 2023). Known limitation: base LLaMA-3 may
underperform fine-tuned forensic models (Sharma et al., 2025).

Include these sections:
1. Executive Summary
2. Key Findings by Category
3. Timeline of Events (if discernible; otherwise state insufficient data)
4. Indicators of Compromise
5. Recommended Next Steps

Ranked artefacts:
{% for artefact in artefacts %}
- [{{ artefact.get('suspicion_level') }} | score={{ artefact.get('relevance_score') }}]
  id={{ artefact['artefact_id'] }} category={{ artefact['category'] }}
  path={{ artefact.get('source_path') }}
  data={{ artefact['raw_data'] }}
  reason={{ artefact.get('classification_reasoning') }}
{% endfor %}
""".strip()


class ForensicPromptTemplates:
    """Render versioned forensic prompt templates via Jinja2."""

    CLASSIFICATION_PROMPT = _CLASSIFICATION_PROMPT
    RANKING_PROMPT = _RANKING_PROMPT
    SUMMARY_PROMPT = _SUMMARY_PROMPT

    def __init__(self) -> None:
        """Initialise the Jinja2 environment with strict undefined handling."""
        self._env = Environment(
            loader=BaseLoader(),
            undefined=StrictUndefined,
            autoescape=False,
        )
        self._templates = {
            "classification": self._env.from_string(self.CLASSIFICATION_PROMPT),
            "ranking": self._env.from_string(self.RANKING_PROMPT),
            "summary": self._env.from_string(self.SUMMARY_PROMPT),
        }

    def render(self, template_name: str, **context: Any) -> str:
        """Render a named prompt template.

        Args:
            template_name: One of ``classification``, ``ranking``, ``summary``.
            **context: Template context variables.

        Returns:
            Rendered prompt string.

        Raises:
            KeyError: If the template name is unknown.
            TemplateError: If rendering fails.
        """
        if template_name not in self._templates:
            raise KeyError(f"Unknown prompt template: {template_name}")
        payload = {"prompt_version": PROMPT_VERSION, **context}
        try:
            return self._templates[template_name].render(**payload)
        except TemplateError:
            raise
