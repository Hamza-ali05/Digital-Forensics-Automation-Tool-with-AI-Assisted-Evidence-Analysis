"""Local LLaMA-3 client configuration and forensic system prompt.

Known limitation: base LLaMA-3 may produce less accurate forensic summaries
than a domain-fine-tuned model (Sharma et al., 2025). Structured JSON
reporting remains the authoritative evidential record (Scanlon et al., 2023).
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, Field

PROMPT_VERSION: str = "1.0.0"

FORENSIC_SYSTEM_PROMPT: str = """You are a digital forensics analyst \
assistant. You analyse forensic artefacts extracted from disk images and \
memory dumps. Your role is to classify artefacts by suspicion level, \
identify indicators of compromise, and generate investigative summaries.

RULES:
- Only base conclusions on the artefact data provided.
- Never fabricate or infer information not present in the data.
- Clearly mark uncertain conclusions with [UNCERTAIN] tags.
- Reference specific artefact IDs when making claims.
- Use CRITICAL/HIGH/MEDIUM/LOW/INFORMATIONAL for suspicion levels.
- If insufficient data exists to classify, use INFORMATIONAL.
- Provide reasoning for every classification decision.
"""


class LLMConfig(BaseModel):
    """Configuration for the local LLaMA-3 (Ollama) HTTP API.

    ``api_url`` is the Ollama base URL (e.g. ``http://localhost:11434``).
    Generate and tags endpoints are derived from this base.
    """

    api_url: str = "http://localhost:11434"
    model: str = "llama3"
    temperature: float = 0.1
    max_tokens: int = 4096
    request_timeout_seconds: int = 120
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    context_window: int = 8192
    num_predict: int = 2048
    stop_sequences: list[str] = Field(default_factory=lambda: ["```", "---END---"])
    system_prompt: str = FORENSIC_SYSTEM_PROMPT
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    health_check_timeout_seconds: int = 5

    @property
    def base_url(self) -> str:
        """Return scheme+host[+port] for Ollama API paths."""
        parsed = urlparse(self.api_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return self.api_url.rstrip("/")

    @property
    def generate_url(self) -> str:
        """Return the Ollama ``/api/generate`` endpoint URL."""
        path = urlparse(self.api_url).path.rstrip("/")
        if path.endswith("/api/generate"):
            return self.api_url
        return f"{self.base_url}/api/generate"

    @property
    def tags_url(self) -> str:
        """Return the Ollama ``/api/tags`` health/list endpoint URL."""
        return f"{self.base_url}/api/tags"

    @property
    def show_url(self) -> str:
        """Return the Ollama ``/api/show`` model-info endpoint URL."""
        return f"{self.base_url}/api/show"
