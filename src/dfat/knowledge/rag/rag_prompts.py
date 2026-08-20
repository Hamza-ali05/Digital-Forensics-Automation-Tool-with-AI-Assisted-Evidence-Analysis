"""RAG-augmented forensic prompt templates wrapping the base LLM prompts."""

from __future__ import annotations

from typing import Any

from jinja2 import BaseLoader, Environment, StrictUndefined, TemplateError, UndefinedError

from dfat.ai_engine.llm.prompts import PROMPT_VERSION, ForensicPromptTemplates

__all__ = ["PROMPT_VERSION", "RAGPromptTemplates"]


class RAGPromptTemplates:
    """Extends ``ForensicPromptTemplates`` with RAG-retrieved context sections.

    The original prompts remain unchanged and available through ``base_templates``.
    RAG prompts wrap the originals with additional context and attribution guidance.
    """

    RAG_PROMPT_VERSION: str = "1.0.0-rag"

    _SOURCE_ATTRIBUTION_INSTRUCTIONS: str = """
Source attribution:
- Identify which retrieved knowledge informed your response.
- Cite contributing datasets or knowledge sources using [KB-{source}] tags.
- Available attributed sources: {{ source_attribution }}
- Do not cite sources that did not influence your answer.
"""

    RAG_CLASSIFICATION_TEMPLATE: str = """RETRIEVED FORENSIC CONTEXT (from knowledge base):
{{ rag_context }}

Use the above context to inform your classification, but only classify based on
the actual artefact data provided. The context provides background from similar
cases and known threat patterns.

IMPORTANT: Cite which retrieved context influenced your classification using
[KB-{source}] tags.
""" + _SOURCE_ATTRIBUTION_INSTRUCTIONS + """
""" + ForensicPromptTemplates.CLASSIFICATION_TEMPLATE

    RAG_SUMMARY_TEMPLATE: str = """RETRIEVED FORENSIC CONTEXT (from knowledge base):
{{ rag_context }}

Use the retrieved threat patterns, MITRE mappings, and historical findings above
to enrich the summary, but base all claims on the artefact data below.

IMPORTANT: Cite retrieved knowledge that influenced each major finding using
[KB-{source}] tags.
""" + _SOURCE_ATTRIBUTION_INSTRUCTIONS + """
""" + ForensicPromptTemplates.SUMMARY_TEMPLATE

    RAG_QA_TEMPLATE: str = """RETRIEVED FORENSIC CONTEXT (from knowledge base):
{{ rag_context }}

Use the retrieved context to inform your answer, but answer ONLY from the
artefact data and retrieved knowledge shown. If the data is insufficient,
say so explicitly.

IMPORTANT: Cite retrieved knowledge using [KB-{source}] tags when it informs
your answer.
""" + _SOURCE_ATTRIBUTION_INSTRUCTIONS + """
""" + ForensicPromptTemplates.QA_TEMPLATE

    RAG_EXPLANATION_TEMPLATE: str = """RETRIEVED FORENSIC CONTEXT (from knowledge base):
{{ rag_context }}

Use the retrieved context to explain forensic significance, but ground every
statement in the artefact data and retrieved knowledge provided.

IMPORTANT: Cite retrieved knowledge using [KB-{source}] tags when it informs
your explanation.
""" + _SOURCE_ATTRIBUTION_INSTRUCTIONS + """
""" + ForensicPromptTemplates.EXPLANATION_TEMPLATE

    def __init__(self, base_templates: ForensicPromptTemplates | None = None) -> None:
        self.base_templates = base_templates or ForensicPromptTemplates()
        self._env = Environment(  # nosec B701
            loader=BaseLoader(),
            undefined=StrictUndefined,
            autoescape=False,
        )
        self._templates = {
            "classification": self._env.from_string(self.RAG_CLASSIFICATION_TEMPLATE),
            "summary": self._env.from_string(self.RAG_SUMMARY_TEMPLATE),
            "qa": self._env.from_string(self.RAG_QA_TEMPLATE),
            "explanation": self._env.from_string(self.RAG_EXPLANATION_TEMPLATE),
        }

    def render(self, template_name: str, *, rag_context: str, source_attribution: list[str], **context: Any) -> str:
        """Render a RAG-augmented prompt template."""
        if template_name not in self._templates:
            raise KeyError(f"Unknown RAG prompt template: {template_name}")

        payload = self.base_templates._normalise_context(template_name, context)
        payload.update(
            {
                "rag_context": rag_context,
                "source_attribution": ", ".join(source_attribution) or "none",
                "prompt_version": self.get_template_version(),
                "base_prompt_version": self.base_templates.get_template_version(),
            }
        )
        try:
            return self._templates[template_name].render(**payload)
        except (TemplateError, UndefinedError):
            raise

    def get_template_version(self) -> str:
        """Return the RAG template version string."""
        return self.RAG_PROMPT_VERSION

    def list_templates(self) -> list[str]:
        """Return registered RAG template names."""
        return sorted(self._templates.keys())
