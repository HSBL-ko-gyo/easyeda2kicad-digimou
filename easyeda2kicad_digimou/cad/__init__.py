"""Safe local CAD package ingestion."""

from .archive import ArchiveLimits, extract_zip_safely
from .digikey import DigiKeyCadSource, DigiKeyProductApi
from .evidence import CadPackageEvidence, load_package_evidence
from .errors import CadPackageError
from .mouser import MouserCadSource, MouserProductApi
from .package import (
    CAD_PACKAGE_FORMATS,
    CadPackageIngestResult,
    CadPackageInspection,
    ingest_cad_package,
    inspect_cad_package,
)
from .selection import (
    AUTO_PACKAGE_SOURCE_PRIORITY,
    AutoCadSelection,
    CadPackageCandidate,
    CadSourceLock,
    load_source_lock,
    select_auto_cad_package,
    write_source_lock,
)

__all__ = [
    "ArchiveLimits",
    "AUTO_PACKAGE_SOURCE_PRIORITY",
    "AutoCadSelection",
    "CAD_PACKAGE_FORMATS",
    "CadPackageError",
    "CadPackageEvidence",
    "CadPackageIngestResult",
    "CadPackageInspection",
    "CadPackageCandidate",
    "CadSourceLock",
    "DigiKeyCadSource",
    "DigiKeyProductApi",
    "MouserCadSource",
    "MouserProductApi",
    "extract_zip_safely",
    "ingest_cad_package",
    "inspect_cad_package",
    "load_package_evidence",
    "load_source_lock",
    "select_auto_cad_package",
    "write_source_lock",
]
