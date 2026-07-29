"""Safe local CAD package ingestion."""

from .archive import ArchiveLimits, extract_zip_safely
from .digikey import DigiKeyCadSource, DigiKeyProductApi
from .evidence import CadPackageEvidence, load_package_evidence
from .errors import CadPackageError
from .package import (
    CAD_PACKAGE_FORMATS,
    CadPackageIngestResult,
    ingest_cad_package,
)

__all__ = [
    "ArchiveLimits",
    "CAD_PACKAGE_FORMATS",
    "CadPackageError",
    "CadPackageEvidence",
    "CadPackageIngestResult",
    "DigiKeyCadSource",
    "DigiKeyProductApi",
    "extract_zip_safely",
    "ingest_cad_package",
    "load_package_evidence",
]
