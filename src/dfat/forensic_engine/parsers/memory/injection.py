"""Volatility3 injected-code parser (malfind).

Artefact ``raw_data`` schema for ``INJECTED_CODE`` (contract)::

    {
        "pid": int,
        "process_name": str,
        "vad_start": str (hex),
        "vad_end": str (hex),
        "vad_tag": str,
        "protection": str,
        "hex_dump_preview": str (first 64 bytes as hex),
        "disassembly_preview": str | null,
        "suspicious_indicators": list[str],
    }

``suspicious_indicators`` may include ``MZ header``, ``shellcode patterns``,
and ``RWX memory region``.
"""

from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import MemoryParsingError
from dfat.core.models.artefact import Artefact
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.memory.plugin_executor import PluginExecutor
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.constants import MAX_ARTEFACTS_PER_CATEGORY

_MALFIND_MODULE = "volatility3.plugins.windows.malfind"

# Common shellcode signatures in the first 64 bytes (hex, no spaces).
_SHELLCODE_HEX_PATTERNS: tuple[str, ...] = (
    "90909090",  # NOP sled
    "ffd0",  # call eax
    "ffd1",  # call ecx
    "ffd2",  # call edx
    "ffd3",  # call ebx
    "ffe4",  # jmp esp
    "ffe0",  # jmp eax
    "c9c3",  # leave; ret
    "31c0",  # xor eax, eax
    "31db",  # xor ebx, ebx
    "31c9",  # xor ecx, ecx
    "31d2",  # xor edx, edx
    "4883ec",  # sub rsp, imm (x64 prologue)
)

_HEX_BYTE_RE = re.compile(r"\b([0-9a-fA-F]{2})\b")


class CodeInjectionParser(BaseParser):
    """Detect injected code artefacts from memory dumps via Volatility3 ``malfind``."""

    _parse_error_class = MemoryParsingError

    def __init__(
        self,
        plugin_executor: PluginExecutor,
        audit_logger: ForensicAuditLogger,
        max_artefacts: int = MAX_ARTEFACTS_PER_CATEGORY,
    ) -> None:
        """Initialise the code injection parser.

        Args:
            plugin_executor: Async Volatility3 plugin executor.
            audit_logger: ACPO-compliant forensic audit logger.
            max_artefacts: Maximum artefacts retained for a single parse.
        """
        super().__init__(audit_logger=audit_logger, max_artefacts=max_artefacts)
        self._executor = plugin_executor

    @property
    def parser_name(self) -> str:
        """Return the stable parser identifier."""
        return "CodeInjectionParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.INJECTED_CODE]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.MEMORY_DUMP]

    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        """Extract injected-code findings using Volatility3 ``malfind``."""
        dump_path = Path(evidence.file_path)
        rows = self._await(
            self._executor.execute_plugin(
                dump_path,
                "Malfind",
                _MALFIND_MODULE,
                evidence.evidence_id,
            )
        )
        artefacts: list[Artefact] = []
        for row in rows:
            if not self._check_limit(len(artefacts)):
                break
            artefacts.append(
                self._create_artefact(
                    category=ArtefactCategory.INJECTED_CODE,
                    evidence_id=evidence.evidence_id,
                    source_path=str(dump_path),
                    raw_data=self._map_row(row),
                )
            )
        return artefacts

    def _map_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Map a Volatility ``malfind`` row to the ``INJECTED_CODE`` schema."""
        protection = self._as_str(
            row.get("Protection", row.get("protection", row.get("Protect")))
        )
        hex_preview = self._hex_dump_preview(
            row.get("Hexdump", row.get("hex_dump_preview", row.get("HexDump")))
        )
        disasm = self._as_str(
            row.get("Disasm", row.get("disassembly_preview", row.get("Disassembly")))
        )
        return {
            "pid": self._as_int(row.get("PID", row.get("pid"))),
            "process_name": self._as_str(
                row.get("Process", row.get("process_name", row.get("ImageFileName")))
            ),
            "vad_start": self._as_hex_addr(
                row.get("Start VPN", row.get("vad_start", row.get("Start", row.get("Address"))))
            ),
            "vad_end": self._as_hex_addr(
                row.get("End VPN", row.get("vad_end", row.get("End")))
            ),
            "vad_tag": self._as_str(row.get("Tag", row.get("vad_tag", row.get("tag")))),
            "protection": protection,
            "hex_dump_preview": hex_preview,
            "disassembly_preview": disasm,
            "suspicious_indicators": self._suspicious_indicators(
                hex_preview, protection, disasm
            ),
        }

    @staticmethod
    def _hex_dump_preview(value: Any) -> str:
        """Return the first 64 bytes of a dump as a contiguous lowercase hex string."""
        if value is None:
            return ""
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)[:64].hex()
        if isinstance(value, memoryview):
            return bytes(value[:64]).hex()

        text = str(value).strip()
        if not text:
            return ""

        # Already a plain hex string (no formatting).
        compact = re.sub(r"[\s:]", "", text)
        if re.fullmatch(r"[0-9a-fA-F]+", compact) and len(compact) >= 2:
            return compact[:128].lower()

        # Formatted Volatility hexdump: extract byte tokens in order.
        tokens = _HEX_BYTE_RE.findall(text)
        if tokens:
            return "".join(tokens[:64]).lower()
        return ""

    @staticmethod
    def _suspicious_indicators(
        hex_preview: str,
        protection: Optional[str],
        disasm: Optional[str],
    ) -> list[str]:
        """Identify MZ header, shellcode patterns, and RWX regions."""
        indicators: list[str] = []
        preview = (hex_preview or "").lower()

        if preview.startswith("4d5a") or preview.startswith("mz"):
            indicators.append("MZ header")

        if CodeInjectionParser._has_shellcode_patterns(preview, disasm):
            indicators.append("shellcode patterns")

        if CodeInjectionParser._is_rwx(protection):
            indicators.append("RWX memory region")

        return indicators

    @staticmethod
    def _has_shellcode_patterns(hex_preview: str, disasm: Optional[str]) -> bool:
        """Detect common shellcode byte/disassembly patterns."""
        if hex_preview:
            # NOP sled of at least 4 consecutive NOPs.
            if "90909090" in hex_preview:
                return True
            for pattern in _SHELLCODE_HEX_PATTERNS:
                if len(pattern) >= 4 and pattern in hex_preview:
                    return True
            # Short jump / call near start of region (classic stub).
            if hex_preview.startswith(("eb", "e8", "e9")):
                return True

        if disasm:
            lowered = disasm.lower()
            markers = (
                "jmp esp",
                "call eax",
                "call ecx",
                "call edx",
                "xor eax, eax",
                "nop",
                "int3",
            )
            if any(m in lowered for m in markers):
                # Require more than a single incidental nop mention.
                if "nop" in lowered and lowered.count("nop") >= 3:
                    return True
                if any(m in lowered for m in markers if m != "nop"):
                    return True
        return False

    @staticmethod
    def _is_rwx(protection: Optional[str]) -> bool:
        """Return ``True`` when protection indicates execute+write (RWX)."""
        if not protection:
            return False
        upper = protection.upper().replace(" ", "_")
        if "RWX" in upper:
            return True
        if "EXECUTE" in upper and "WRITE" in upper:
            return True
        # Volatility may print PAGE_EXECUTE_READWRITE or mask 0x40.
        if "PAGE_EXECUTE_READWRITE" in upper or "PAGE_EXECUTE_WRITECOPY" in upper:
            return True
        if "0X40" in upper:
            return True
        return False

    @staticmethod
    def _as_hex_addr(value: Any) -> Optional[str]:
        """Normalise an address to a ``0x``-prefixed hex string."""
        if value is None or value == "":
            return None
        if isinstance(value, int):
            return hex(value)
        text = str(value).strip()
        if not text:
            return None
        if text.lower().startswith("0x"):
            try:
                return hex(int(text, 16))
            except ValueError:
                return text.lower()
        try:
            return hex(int(text))
        except ValueError:
            return text

    @staticmethod
    def _as_int(value: Any) -> Optional[int]:
        """Best-effort integer coercion."""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_str(value: Any) -> Optional[str]:
        """Best-effort string coercion."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _await(coro: Any) -> Any:
        """Run an async coroutine from sync ``_do_parse`` safely."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
