"""Local LLaMA-3 client configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field

_DEFAULT_SYSTEM_PROMPT = (
    "You are a digital forensics analyst assisting with evidence triage. "
    "Analyse only the provided artefacts. Do NOT fabricate facts, file paths, "
    "timestamps, or indicators that are not present in the input. Clearly mark "
    "uncertain inferences. Prefer conservative suspicion ratings. Known limitation: "
    "base LLaMA-3 may be less accurate than a fine-tuned forensic model "
    "(Sharma et al., 2025); treat narrative output as advisory, not authoritative."
)


class LLMConfig(BaseModel):
    """Configuration for the local LLaMA-3 HTTP API client.

    Attributes:
        api_url: Local generate endpoint (must remain host-local).
        model: Model name served by the local runtime (e.g. Ollama).
        temperature: Low temperature for forensic reproducibility.
        max_tokens: Maximum generation length.
        request_timeout_seconds: HTTP timeout for generate calls.
        top_p: Nucleus sampling parameter.
        repeat_penalty: Repetition penalty.
        system_prompt: Forensic-context system instruction.
    """

    api_url: str = "http://localhost:11434/api/generate"
    model: str = "llama3"
    temperature: float = 0.1
    max_tokens: int = 4096
    request_timeout_seconds: int = 120
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    system_prompt: str = Field(default=_DEFAULT_SYSTEM_PROMPT)
