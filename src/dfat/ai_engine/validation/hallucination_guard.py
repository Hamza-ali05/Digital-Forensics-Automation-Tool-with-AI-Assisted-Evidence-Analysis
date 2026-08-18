"""Hallucination detection heuristics for local LLM forensic outputs.

Flags fabricated artefact IDs, categories, suspicion levels, unsupported
certainty claims, and knowledge artefacts (IPs/domains/hashes) not present
in the provided evidence context (Scanlon et al., 2023).
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_ART_ID_RE = re.compile(r"\b(?:art|artefact)[-_][\w-]+\b", re.IGNORECASE)

_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,})\b",
    re.IGNORECASE,
)
_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b")

_ASSERTION_RE = re.compile(
    r"\b(definitely|certainly|it is clear that|without (?:a )?doubt|"
    r"obviously|undoubtedly| conclusively)\b",
    re.IGNORECASE,
)

# Common LLM-fabricated category-like tokens not in DFAT taxonomy.
_KNOWN_FABRICATED_CATEGORIES = frozenset(
    {
        "malware_signature",
        "rootkit_trace",
        "crypto_wallet",
        "password_vault",
        "cloud_exfiltration",
        "kernel_hook",
    }
)

_KNOWN_FABRICATED_LEVELS = frozenset(
    {
        "extreme",
        "severe",
        "negligible",
        "unknown",
        "catastrophic",
    }
)

_COMMON_DOMAIN_ALLOW = frozenset(
    {
        "localhost",
        "example.com",
        "example.org",
        "example.net",
    }
)


class HallucinationReport(BaseModel):
    """Outcome of a hallucination scan over LLM text."""

    model_config = ConfigDict(frozen=False)

    hallucinated_ids: list[str] = Field(default_factory=list)
    fabricated_terms: list[str] = Field(default_factory=list)
    unsupported_assertions: list[str] = Field(default_factory=list)
    risk_level: str = "low"  # low | medium | high
    clean_response: str = ""


class HallucinationGuard:
    """Detect hallucinated references and unsupported claims in LLM text."""

    def __init__(
        self,
        valid_artefact_ids: set[str],
        valid_categories: set[str],
        valid_suspicion_levels: set[str],
        *,
        known_facts: Optional[set[str]] = None,
    ) -> None:
        """Initialise the guard with allowed reference vocabularies.

        Args:
            valid_artefact_ids: Artefact IDs present in the current analysis.
            valid_categories: Allowed ``ArtefactCategory`` values.
            valid_suspicion_levels: Allowed ``SuspicionLevel`` values.
            known_facts: Optional set of IP/domain/hash strings present in input
                artefact ``raw_data`` (case-insensitive match for hashes).
        """
        self._valid_ids = set(valid_artefact_ids)
        self._valid_categories = {item.lower() for item in valid_categories}
        self._valid_levels = {item.lower() for item in valid_suspicion_levels}
        self._known_facts = {item.lower() for item in (known_facts or set())}

    def check_response(self, response_text: str) -> HallucinationReport:
        """Scan ``response_text`` and return a hallucination report.

        Steps:
            1. Extract artefact ID references.
            2. Flag IDs not in ``valid_artefact_ids``.
            3. Flag fabricated category names.
            4. Flag fabricated suspicion levels.
            5. Detect unsupported certainty assertions.
            6. Detect IP/domain/hash claims absent from known facts.
            7. Assess risk and produce a cleaned response.
        """
        text = response_text or ""
        hallucinated_ids = self._find_hallucinated_ids(text)
        fabricated_terms = self._find_fabricated_terms(text)
        unsupported = self._find_unsupported_assertions(text)
        fabricated_terms.extend(self._find_unknown_knowledge_claims(text))
        # Deduplicate fabricated terms while preserving order
        seen: set[str] = set()
        unique_terms: list[str] = []
        for term in fabricated_terms:
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_terms.append(term)

        risk = self._assess_risk(hallucinated_ids, unique_terms, unsupported)
        clean = self._clean_response(text, hallucinated_ids, unique_terms)

        return HallucinationReport(
            hallucinated_ids=hallucinated_ids,
            fabricated_terms=unique_terms,
            unsupported_assertions=unsupported,
            risk_level=risk,
            clean_response=clean,
        )

    def with_known_facts(self, known_facts: set[str]) -> HallucinationGuard:
        """Return a copy of this guard with updated known fact tokens."""
        return HallucinationGuard(
            set(self._valid_ids),
            set(self._valid_categories),
            set(self._valid_levels),
            known_facts=known_facts,
        )

    def _find_hallucinated_ids(self, text: str) -> list[str]:
        found: list[str] = []
        found.extend(_UUID_RE.findall(text))
        found.extend(_ART_ID_RE.findall(text))
        hallucinated: list[str] = []
        seen: set[str] = set()
        for item in found:
            if item in seen:
                continue
            seen.add(item)
            if item not in self._valid_ids:
                hallucinated.append(item)
        return hallucinated

    def _find_fabricated_terms(self, text: str) -> list[str]:
        terms: list[str] = []
        lowered = text.lower()

        for fabricated in _KNOWN_FABRICATED_CATEGORIES:
            if fabricated in lowered and fabricated not in self._valid_categories:
                terms.append(fabricated)

        # Category-like snake_case tokens that look taxonomic but aren't valid.
        for match in re.findall(r"\b[a-z]+(?:_[a-z]+){1,3}\b", lowered):
            if match in self._valid_categories or match in self._valid_levels:
                continue
            if match in _KNOWN_FABRICATED_CATEGORIES:
                continue  # already added
            if match.endswith(("_trace", "_signature", "_exfiltration", "_hook")):
                terms.append(match)

        for fabricated in _KNOWN_FABRICATED_LEVELS:
            if re.search(rf"\b{re.escape(fabricated)}\b", lowered):
                if fabricated not in self._valid_levels:
                    terms.append(fabricated)

        # Explicit "suspicion level: X" / "classified as X" with invalid X
        for match in re.finditer(
            r"(?:suspicion(?:_level)?|classified as|severity level)\s*[:=]?\s*"
            r"([A-Za-z_]+)",
            text,
            flags=re.IGNORECASE,
        ):
            level = match.group(1).lower()
            if level not in self._valid_levels and level not in {
                "level",
                "of",
                "compromise",
            }:
                terms.append(level)

        return terms

    def _find_unsupported_assertions(self, text: str) -> list[str]:
        assertions: list[str] = []
        for match in _ASSERTION_RE.finditer(text):
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 80)
            snippet = text[start:end].strip()
            window_ids = set(_UUID_RE.findall(snippet)) | set(_ART_ID_RE.findall(snippet))
            has_valid_ref = any(item in self._valid_ids for item in window_ids)
            if not has_valid_ref:
                assertions.append(snippet)
        return assertions

    def _find_unknown_knowledge_claims(self, text: str) -> list[str]:
        claims: list[str] = []
        for ip in _IPV4_RE.findall(text):
            if ip.lower() not in self._known_facts and ip not in {"0.0.0.0", "127.0.0.1"}:  # nosec B104
                claims.append(ip)
        for domain in _DOMAIN_RE.findall(text):
            lowered = domain.lower()
            if lowered in _COMMON_DOMAIN_ALLOW:
                continue
            # Skip category-like or file-extension false positives
            if lowered.endswith((".exe", ".dll", ".sys", ".bat", ".ps1", ".json")):
                continue
            if lowered not in self._known_facts:
                claims.append(domain)
        for digest in _HASH_RE.findall(text):
            if digest.lower() not in self._known_facts:
                claims.append(digest)
        return claims

    @staticmethod
    def _assess_risk(
        hallucinated_ids: list[str],
        fabricated_terms: list[str],
        unsupported: list[str],
    ) -> str:
        score = (
            len(hallucinated_ids) * 2
            + len(fabricated_terms)
            + len(unsupported)
        )
        if score >= 4 or len(hallucinated_ids) >= 2:
            return "high"
        if score >= 2 or hallucinated_ids or unsupported:
            return "medium"
        if fabricated_terms:
            return "medium"
        return "low"

    def _clean_response(
        self,
        text: str,
        hallucinated_ids: list[str],
        fabricated_terms: list[str],
    ) -> str:
        cleaned = text
        for artefact_id in hallucinated_ids:
            cleaned = cleaned.replace(
                artefact_id,
                f"[HALLUCINATED_ID:{artefact_id}]",
            )
        for term in fabricated_terms:
            cleaned = re.sub(
                rf"\b{re.escape(term)}\b",
                f"[FABRICATED:{term}]",
                cleaned,
                flags=re.IGNORECASE,
            )
        return cleaned
