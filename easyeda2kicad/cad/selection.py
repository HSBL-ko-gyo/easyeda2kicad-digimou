"""Deterministic selection and content locking for validated CAD packages."""

from __future__ import annotations

# Global imports
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

# Local imports
from easyeda2kicad.metadata.models import (
    CadRequest,
    identity_text,
    normalize_manufacturer,
    normalize_mpn,
)

from .errors import CadPackageError
from .package import CadPackageInspection, inspect_cad_package

AUTO_PACKAGE_SOURCE_PRIORITY = ("digikey", "mouser")
_PACKAGE_FORMAT_BY_SOURCE = {
    "digikey": "ultralibrarian-kicad",
    "mouser": "samacsys-kicad",
}
_LOCK_FIELDS = frozenset(
    (
        "schema_version",
        "manufacturer",
        "mpn",
        "selected_source",
        "package_sha256",
    )
)


@dataclass(frozen=True)
class CadPackageCandidate:
    source: str
    archive_path: Path
    evidence_path: Optional[Path] = None

    def __post_init__(self) -> None:
        normalized_source = identity_text(
            self.source, "CadPackageCandidate.source"
        ).lower()
        if normalized_source not in AUTO_PACKAGE_SOURCE_PRIORITY:
            raise ValueError("unsupported auto CAD package source")
        object.__setattr__(self, "source", normalized_source)
        object.__setattr__(self, "archive_path", Path(self.archive_path))
        if self.evidence_path is not None:
            object.__setattr__(self, "evidence_path", Path(self.evidence_path))


@dataclass(frozen=True)
class CadSourceLock:
    schema_version: int
    manufacturer: str
    mpn: str
    selected_source: str
    package_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported CAD source lock schema")
        manufacturer = identity_text(self.manufacturer, "CadSourceLock.manufacturer")
        mpn = identity_text(self.mpn, "CadSourceLock.mpn")
        source = identity_text(
            self.selected_source, "CadSourceLock.selected_source"
        ).lower()
        if source not in AUTO_PACKAGE_SOURCE_PRIORITY:
            raise ValueError("unsupported CAD source lock selection")
        package_sha256 = identity_text(
            self.package_sha256, "CadSourceLock.package_sha256"
        ).lower()
        if len(package_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in package_sha256
        ):
            raise ValueError("CadSourceLock.package_sha256 must be a SHA-256 digest")
        object.__setattr__(self, "manufacturer", manufacturer)
        object.__setattr__(self, "mpn", mpn)
        object.__setattr__(self, "selected_source", source)
        object.__setattr__(self, "package_sha256", package_sha256)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manufacturer": self.manufacturer,
            "mpn": self.mpn,
            "selected_source": self.selected_source,
            "package_sha256": self.package_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CadSourceLock":
        unknown = set(data).difference(_LOCK_FIELDS)
        missing = _LOCK_FIELDS.difference(data)
        if unknown or missing:
            raise ValueError("CAD source lock fields do not match schema 1")
        schema_version = data["schema_version"]
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ValueError("CadSourceLock.schema_version must be an integer")
        return cls(
            schema_version=schema_version,
            manufacturer=identity_text(
                data["manufacturer"], "CadSourceLock.manufacturer"
            ),
            mpn=identity_text(data["mpn"], "CadSourceLock.mpn"),
            selected_source=identity_text(
                data["selected_source"], "CadSourceLock.selected_source"
            ),
            package_sha256=identity_text(
                data["package_sha256"], "CadSourceLock.package_sha256"
            ),
        )


@dataclass(frozen=True)
class InspectedCadCandidate:
    candidate: CadPackageCandidate
    inspection: CadPackageInspection


@dataclass(frozen=True)
class AutoCadSelection:
    selected: InspectedCadCandidate
    inspected: Tuple[InspectedCadCandidate, ...]
    source_lock: CadSourceLock
    existing_lock: bool


def select_auto_cad_package(
    candidates: Sequence[CadPackageCandidate],
    *,
    manufacturer: str,
    mpn: str,
    source_lock_path: Optional[Path] = None,
) -> AutoCadSelection:
    """Inspect all candidates before selecting one or emitting a conflict."""

    if not candidates:
        raise CadPackageError(
            "CAD_AUTO_CANDIDATE_MISSING",
            "auto package selection requires at least one local candidate",
        )
    by_source: Dict[str, CadPackageCandidate] = {}
    for candidate in candidates:
        if candidate.source in by_source:
            raise CadPackageError(
                "CAD_AUTO_CANDIDATE_AMBIGUOUS",
                "auto package selection accepts at most one candidate per source",
            )
        by_source[candidate.source] = candidate

    existing_lock = False
    source_lock: Optional[CadSourceLock] = None
    if source_lock_path is not None and source_lock_path.exists():
        existing_lock = True
        source_lock = load_source_lock(source_lock_path)
        if normalize_manufacturer(source_lock.manufacturer) != normalize_manufacturer(
            manufacturer
        ) or normalize_mpn(source_lock.mpn) != normalize_mpn(mpn):
            raise CadPackageError(
                "CAD_SOURCE_LOCK_IDENTITY_MISMATCH",
                "CAD source lock does not match the requested manufacturer and MPN",
            )

    inspected = tuple(
        _inspect_candidate(by_source[source], manufacturer, mpn)
        for source in AUTO_PACKAGE_SOURCE_PRIORITY
        if source in by_source
    )
    if source_lock is not None:
        selected = next(
            (
                item
                for item in inspected
                if item.candidate.source == source_lock.selected_source
                and item.inspection.package.provenance.package_hash
                == source_lock.package_sha256
            ),
            None,
        )
        if selected is None:
            raise CadPackageError(
                "CAD_SOURCE_LOCK_MISMATCH",
                "no validated candidate matches the locked source and package hash",
            )
        return AutoCadSelection(
            selected=selected,
            inspected=inspected,
            source_lock=source_lock,
            existing_lock=True,
        )

    signatures = {item.inspection.material_signature() for item in inspected}
    if len(signatures) > 1:
        raise CadPackageError(
            "CAD_SOURCE_CONFLICT",
            (
                "validated CAD candidates materially disagree on pin/pad, "
                "footprint package, or primary 3D link"
            ),
        )

    selected = inspected[0]
    package_hash = selected.inspection.package.provenance.package_hash
    if package_hash is None:
        raise CadPackageError(
            "CAD_SOURCE_LOCK_UNAVAILABLE",
            "selected CAD package did not retain its content hash",
        )
    source_lock = CadSourceLock(
        schema_version=1,
        manufacturer=manufacturer,
        mpn=mpn,
        selected_source=selected.candidate.source,
        package_sha256=package_hash,
    )
    return AutoCadSelection(
        selected=selected,
        inspected=inspected,
        source_lock=source_lock,
        existing_lock=existing_lock,
    )


def load_source_lock(path: Path) -> CadSourceLock:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("CAD source lock root must be an object")
        return CadSourceLock.from_dict(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise CadPackageError(
            "CAD_SOURCE_LOCK_INVALID",
            "CAD source lock is missing, malformed, or unsupported",
            path.name,
        ) from error


def write_source_lock(path: Path, source_lock: CadSourceLock) -> None:
    """Write one source lock atomically without replacing a different lock."""

    target = Path(path)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        current = load_source_lock(target)
        if current != source_lock:
            raise CadPackageError(
                "CAD_SOURCE_LOCK_CONFLICT",
                "an existing CAD source lock selects different content",
                target.name,
            )
        return

    payload = (
        json.dumps(
            source_lock.to_dict(),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=str(parent),
            prefix=".{0}.".format(target.name),
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        if target.exists():
            raise CadPackageError(
                "CAD_SOURCE_LOCK_CONCURRENT_MODIFICATION",
                "CAD source lock appeared while the selected package was installed",
                target.name,
            )
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _inspect_candidate(
    candidate: CadPackageCandidate,
    manufacturer: str,
    mpn: str,
) -> InspectedCadCandidate:
    request = CadRequest(
        manufacturer=manufacturer,
        mpn=mpn,
        source=candidate.source,
    )
    inspection = inspect_cad_package(
        candidate.archive_path,
        package_format=_PACKAGE_FORMAT_BY_SOURCE[candidate.source],
        request=request,
        evidence_path=candidate.evidence_path,
    )
    return InspectedCadCandidate(candidate=candidate, inspection=inspection)


__all__ = [
    "AUTO_PACKAGE_SOURCE_PRIORITY",
    "AutoCadSelection",
    "CadPackageCandidate",
    "CadSourceLock",
    "InspectedCadCandidate",
    "load_source_lock",
    "select_auto_cad_package",
    "write_source_lock",
]
