"""Jinja2 forensic prompt templates for local LLaMA-3 triage.

Templates are Python string constants (not files) for portability.
All templates include anti-hallucination instructions.
``PROMPT_VERSION`` tracks template versions for reproducibility — changing
templates changes research results and must be documented in the dissertation.

Known limitation: base LLaMA-3 may underperform a domain-fine-tuned forensic
model (Sharma et al., 2025). Narrative output is advisory; structured JSON
remains the authoritative record (Scanlon et al., 2023).
"""

from __future__ import annotations

from typing import Any

from jinja2 import BaseLoader, Environment, StrictUndefined, TemplateError, UndefinedError

from dfat.ai_engine.llm.config import PROMPT_VERSION as _CONFIG_PROMPT_VERSION

# Module-level re-export for evaluation methodology / reproducibility tracking.
PROMPT_VERSION: str = _CONFIG_PROMPT_VERSION

__all__ = ["PROMPT_VERSION", "ForensicPromptTemplates"]


class ForensicPromptTemplates:
    """Manages all LLM prompt templates for forensic analysis.

    Templates are stored as Python string constants (not files) for portability.
    All templates include anti-hallucination instructions.
    ``PROMPT_VERSION`` tracks template versions for reproducibility.
    """

    PROMPT_VERSION: str = "1.0.0"

    CLASSIFICATION_TEMPLATE: str = """Analyse the following forensic artefacts
and classify each by suspicion level.

For each artefact, respond with a JSON object containing:
- "artefact_id": the ID provided
- "suspicion_level": one of CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL
- "reasoning": a brief explanation (1-2 sentences) for the classification
- "ioc_indicators": list of any indicators of compromise identified

IMPORTANT: Only classify based on the data provided. Do not fabricate
information. If uncertain, classify as INFORMATIONAL and note the uncertainty.

Respond ONLY with a JSON array. No other text.

Artefacts:
{{ artefact_text }}

---END---"""

    RANKING_TEMPLATE: str = """Given these classified forensic artefacts,
rank them by investigative relevance.

Respond with a JSON array of objects, each containing:
- "artefact_id": the ID
- "relevance_score": float 0.0-1.0 (1.0 = most relevant)
- "priority_reasoning": why this artefact matters for the investigation

Consider: evidence of compromise, data exfiltration indicators, persistence
mechanisms, lateral movement, and timeline significance.

IMPORTANT: Rank only based on the provided data. Do not fabricate information.
If uncertain about relevance, assign a lower score and note uncertainty.

Respond ONLY with a JSON array. No other text.

Artefacts:
{{ artefact_text }}

---END---"""

    SUMMARY_TEMPLATE: str = """Generate an investigative summary for the
following forensic artefacts from a digital forensic examination.

Structure your summary as:
1. EXECUTIVE SUMMARY (2-3 sentences overview)
2. KEY FINDINGS (bullet points by category)
3. TIMELINE OF EVENTS (chronological if timestamps available)
4. INDICATORS OF COMPROMISE (list any IOCs)
5. RECOMMENDED NEXT STEPS (investigative actions)

Mark any uncertain conclusions with [UNCERTAIN].
Reference artefact IDs when making specific claims.
Do not fabricate information not present in the data.

Analysis Statistics:
- Total artefacts: {{ total_count }}
- Critical: {{ critical_count }}, High: {{ high_count }}
- Categories present: {{ categories }}

Key Artefacts:
{{ artefact_text }}

---END---"""

    EXPLANATION_TEMPLATE: str = """Explain the forensic significance of this
artefact to an investigator.

Artefact: {{ artefact_text }}
Classification: {{ suspicion_level }}

Provide:
1. What this artefact represents
2. Why it was classified at this level
3. What investigative action it suggests
4. Any related artefacts to examine

Keep explanation concise (3-5 sentences). Mark uncertainty with [UNCERTAIN].

---END---"""

    QA_TEMPLATE: str = """You are assisting a forensic investigator examining
digital evidence. Answer their question based ONLY on the provided artefact
data. If the data is insufficient, say so explicitly.

Available artefact data:
{{ context_text }}

Investigator question: {{ question }}

---END---"""

    # Backward-compatible aliases used by earlier LocalLLMClient call sites.
    CLASSIFICATION_PROMPT = CLASSIFICATION_TEMPLATE
    RANKING_PROMPT = RANKING_TEMPLATE
    SUMMARY_PROMPT = SUMMARY_TEMPLATE

    def __init__(self) -> None:
        """Initialise Jinja2 with ``StrictUndefined`` to catch missing variables."""
        self._env = Environment(
            loader=BaseLoader(),
            undefined=StrictUndefined,
            autoescape=False,
        )
        self._templates = {
            "classification": self._env.from_string(self.CLASSIFICATION_TEMPLATE),
            "ranking": self._env.from_string(self.RANKING_TEMPLATE),
            "summary": self._env.from_string(self.SUMMARY_TEMPLATE),
            "explanation": self._env.from_string(self.EXPLANATION_TEMPLATE),
            "qa": self._env.from_string(self.QA_TEMPLATE),
        }

    def render(self, template_name: str, **context: Any) -> str:
        """Render a named prompt template.

        Args:
            template_name: One of ``classification``, ``ranking``, ``summary``,
                ``explanation``, ``qa``.
            **context: Template context variables. Legacy callers may pass
                ``artefacts`` (list of dicts); these are converted to
                ``artefact_text`` / summary stats when needed.

        Returns:
            Rendered prompt string.

        Raises:
            KeyError: If the template name is unknown.
            TemplateError / UndefinedError: If rendering fails or variables are missing.
        """
        if template_name not in self._templates:
            raise KeyError(f"Unknown prompt template: {template_name}")
        payload = self._normalise_context(template_name, context)
        payload = {"prompt_version": self.get_template_version(), **payload}
        try:
            return self._templates[template_name].render(**payload)
        except (TemplateError, UndefinedError):
            raise

    def get_template_version(self) -> str:
        """Return the template version string for reproducibility tracking."""
        return self.PROMPT_VERSION

    def list_templates(self) -> list[str]:
        """Return registered template names."""
        return sorted(self._templates.keys())

    def _normalise_context(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Fill template variables from legacy ``artefacts`` context when present."""
        payload = dict(context)
        artefacts = payload.get("artefacts")

        if template_name in {"classification", "ranking"}:
            if "artefact_text" not in payload and isinstance(artefacts, list):
                payload["artefact_text"] = self._artefacts_to_text(artefacts)

        if template_name == "summary":
            if isinstance(artefacts, list):
                if "artefact_text" not in payload:
                    payload["artefact_text"] = self._artefacts_to_text(artefacts)
                if "total_count" not in payload:
                    payload["total_count"] = len(artefacts)
                if "critical_count" not in payload:
                    payload["critical_count"] = self._count_level(artefacts, "critical")
                if "high_count" not in payload:
                    payload["high_count"] = self._count_level(artefacts, "high")
                if "categories" not in payload:
                    cats = sorted(
                        {
                            str(item.get("category", "unknown"))
                            for item in artefacts
                            if isinstance(item, dict)
                        }
                    )
                    payload["categories"] = ", ".join(cats) if cats else "none"

        return payload

    @staticmethod
    def _artefacts_to_text(artefacts: list[Any]) -> str:
        """Build a compact text block from artefact dicts or objects."""
        lines: list[str] = []
        for item in artefacts:
            if isinstance(item, dict):
                artefact_id = item.get("artefact_id", "unknown")
                category = item.get("category", "unknown")
                suspicion = item.get("suspicion_level")
                score = item.get("relevance_score")
                raw = item.get("raw_data", {})
                reasoning = item.get("classification_reasoning")
                path = item.get("source_path")
            else:
                artefact_id = getattr(item, "artefact_id", "unknown")
                category = getattr(item, "category", "unknown")
                suspicion = getattr(item, "suspicion_level", None)
                score = getattr(item, "relevance_score", None)
                raw = getattr(item, "raw_data", {})
                reasoning = getattr(item, "classification_reasoning", None)
                path = getattr(item, "source_path", None)

            header = f"[{artefact_id}] category={category}"
            if suspicion is not None:
                header += f" suspicion={suspicion}"
            if score is not None:
                header += f" score={score}"
            lines.append(header)
            if path:
                lines.append(f"  source_path: {path}")
            if isinstance(raw, dict):
                for key in sorted(raw.keys()):
                    lines.append(f"  {key}: {raw[key]}")
            if reasoning:
                lines.append(f"  reasoning: {reasoning}")
            lines.append("")
        return "\n".join(lines).rstrip()

    @staticmethod
    def _count_level(artefacts: list[Any], level: str) -> int:
        """Count artefacts whose suspicion level matches ``level``."""
        count = 0
        needle = level.lower()
        for item in artefacts:
            if isinstance(item, dict):
                value = item.get("suspicion_level")
            else:
                value = getattr(item, "suspicion_level", None)
            if value is None:
                continue
            text = getattr(value, "value", value)
            if str(text).lower() == needle:
                count += 1
        return count
