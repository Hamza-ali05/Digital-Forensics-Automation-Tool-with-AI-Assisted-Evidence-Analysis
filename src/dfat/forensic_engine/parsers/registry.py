"""Windows registry hive parser using python-registry.

Artefact ``raw_data`` schema for ``REGISTRY_KEY``:
    key_path, value_name, value_data, value_type, last_modified
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers import _tsk_utils
from dfat.forensic_engine.parsers.base import BaseParser

_HIVE_NAMES = ("SAM", "SYSTEM", "SOFTWARE", "SECURITY", "NTUSER.DAT")


class RegistryParser(BaseParser):
    """Extract registry key/value artefacts from disk images."""

    @property
    def parser_name(self) -> str:
        """Return the stable parser identifier."""
        return "RegistryParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.REGISTRY_KEY]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.DISK_IMAGE]

    def parse(self, evidence: EvidenceImage) -> ArtefactSet:
        """Locate registry hives in the image and parse key/value pairs.

        Args:
            evidence: Disk image evidence metadata.

        Returns:
            Artefact set of registry key entries.

        Raises:
            ImportError: If ``pytsk3`` or ``python-registry`` is not installed.
            DiskParsingError: If hive parsing fails fatally.
        """
        self._log_parse_start(evidence.evidence_id)
        try:
            from Registry import Registry
        except ImportError as exc:
            raise ImportError(
                "python-registry is required for registry parsing. Install with: "
                "pip install python-registry"
            ) from exc

        _tsk_utils.require_pytsk3()
        artefacts: list[Artefact] = []
        try:
            hives = _tsk_utils.find_files(
                evidence.file_path,
                predicate=lambda p: any(
                    p.upper().endswith("/" + name) or p.upper().endswith("\\" + name)
                    for name in _HIVE_NAMES
                ),
                limit=10,
            )
            for hive_path, content in hives:
                if len(artefacts) >= self._max_artefacts:
                    break
                artefacts.extend(
                    self._parse_hive_bytes(
                        content,
                        hive_path,
                        evidence.evidence_id,
                        Registry,
                        remaining=self._max_artefacts - len(artefacts),
                    )
                )
        except ImportError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._log_parse_error(evidence.evidence_id, exc)
            raise DiskParsingError(
                f"RegistryParser failed for {evidence.file_path}",
                context={"evidence_id": evidence.evidence_id, "error": str(exc)},
            ) from exc

        artefacts = self._truncate(artefacts)
        result = self._to_artefact_set(evidence.evidence_id, artefacts)
        self._log_parse_end(evidence.evidence_id, len(artefacts))
        return result

    def _parse_hive_bytes(
        self,
        content: bytes,
        hive_path: str,
        evidence_id: str,
        registry_mod: object,
        remaining: int,
    ) -> list[Artefact]:
        """Parse a hive blob from temporary storage.

        Args:
            content: Raw hive bytes.
            hive_path: Source path within the image.
            evidence_id: Evidence identifier.
            registry_mod: Imported ``Registry`` module.
            remaining: Remaining artefact capacity.

        Returns:
            List of registry artefacts.
        """
        artefacts: list[Artefact] = []
        with tempfile.NamedTemporaryFile(suffix=".hive", delete=False) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            registry = registry_mod.Registry(str(temp_path))  # type: ignore[attr-defined]
            root = registry.root()
            self._walk_key(
                root,
                root.path(),
                hive_path,
                evidence_id,
                artefacts,
                remaining,
            )
        except Exception:  # noqa: BLE001 - skip corrupt hives
            return artefacts
        finally:
            temp_path.unlink(missing_ok=True)
        return artefacts

    def _walk_key(
        self,
        key: object,
        key_path: str,
        hive_path: str,
        evidence_id: str,
        artefacts: list[Artefact],
        remaining: int,
    ) -> None:
        """Recursively walk registry keys collecting values.

        Args:
            key: Registry key object.
            key_path: Current key path.
            hive_path: Source hive path.
            evidence_id: Evidence identifier.
            artefacts: Output artefact accumulator.
            remaining: Remaining capacity.
        """
        if len(artefacts) >= remaining:
            return
        try:
            values = key.values()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            values = []
        for value in values:
            if len(artefacts) >= remaining:
                return
            try:
                artefacts.append(
                    self._create_artefact(
                        category=ArtefactCategory.REGISTRY_KEY,
                        evidence_id=evidence_id,
                        source_path=hive_path,
                        raw_data={
                            "key_path": key_path,
                            "value_name": value.name(),
                            "value_data": str(value.value()),
                            "value_type": str(value.value_type()),
                            "last_modified": str(key.timestamp()),  # type: ignore[attr-defined]
                        },
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        try:
            subkeys = key.subkeys()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return
        for subkey in subkeys:
            if len(artefacts) >= remaining:
                return
            try:
                self._walk_key(
                    subkey,
                    subkey.path(),
                    hive_path,
                    evidence_id,
                    artefacts,
                    remaining,
                )
            except Exception:  # noqa: BLE001
                continue
