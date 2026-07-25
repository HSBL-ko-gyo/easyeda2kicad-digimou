"""Safe local CAD package ingestion."""

from .archive import ArchiveLimits, extract_zip_safely
from .digikey import DigiKeyCadSource, DigiKeyProductApi
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
    "CadPackageIngestResult",
    "DigiKeyCadSource",
    "DigiKeyProductApi",
    "extract_zip_safely",
    "ingest_cad_package",
]
