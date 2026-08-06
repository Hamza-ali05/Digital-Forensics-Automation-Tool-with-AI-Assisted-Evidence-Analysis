"""Filesystem metadata parser using pytsk3.

Artefact ``raw_data`` schema for ``FILESYSTEM_METADATA``:
    filename, path, size, created_time, modified_time, accessed_time,
    is_deleted, file_type, inode_number
"""

from __future__ import annotations

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers import _tsk_utils
from dfat.forensic_engine.parsers.base import BaseParser


class FileSystemParser(BaseParser):
    """Extract filesystem metadata artefacts from disk images."""

    @property
    def parser_name(self) -> str:
        """Return the stable parser identifier."""
        return "FileSystemParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.FILESYSTEM_METADATA]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.DISK_IMAGE]

    def parse(self, evidence: EvidenceImage) -> ArtefactSet:
        """Walk the disk image filesystem and emit metadata artefacts.

        Args:
            evidence: Disk image evidence metadata.

        Returns:
            Artefact set of filesystem metadata entries.

        Raises:
            ImportError: If ``pytsk3`` is not installed.
            DiskParsingError: If filesystem walking fails.
        """
        self._log_parse_start(evidence.evidence_id)
        _tsk_utils.require_pytsk3()
        artefacts: list[Artefact] = []
        try:
            for full_path, entry in _tsk_utils.walk_filesystem(evidence.file_path):
                if len(artefacts) >= self._max_artefacts:
                    break
                try:
                    name = entry.info.name.name.decode("utf-8", errors="replace")
                    meta = entry.info.meta
                    is_dir = bool(
                        meta is not None and meta.type == meta.TYPE_DIR
                    )
                    artefacts.append(
                        self._create_artefact(
                            category=ArtefactCategory.FILESYSTEM_METADATA,
                            evidence_id=evidence.evidence_id,
                            source_path=full_path,
                            raw_data={
                                "filename": name,
                                "path": full_path,
                                "size": int(meta.size) if meta else 0,
                                "created_time": _tsk_utils.meta_timestamp(
                                    entry, "crtime"
                                ),
                                "modified_time": _tsk_utils.meta_timestamp(
                                    entry, "mtime"
                                ),
                                "accessed_time": _tsk_utils.meta_timestamp(
                                    entry, "atime"
                                ),
                                "is_deleted": bool(
                                    meta is not None and getattr(meta, "flags", 0)
                                ),
                                "file_type": "directory" if is_dir else "file",
                                "inode_number": int(meta.addr) if meta else None,
                            },
                        )
                    )
                except Exception:  # noqa: BLE001 - skip bad entries
                    continue
        except ImportError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._log_parse_error(evidence.evidence_id, exc)
            raise DiskParsingError(
                f"FileSystemParser failed for {evidence.file_path}",
                context={"evidence_id": evidence.evidence_id, "error": str(exc)},
            ) from exc

        artefacts = self._truncate(artefacts)
        result = self._to_artefact_set(evidence.evidence_id, artefacts)
        self._log_parse_end(evidence.evidence_id, len(artefacts))
        return result
