"""Safe local CAD package ingestion."""

from .archive import ArchiveLimits, extract_zip_safely
from .errors import CadPackageError
from .mouser import MouserCadSource, MouserProductApi
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
    "MouserCadSource",
    "MouserProductApi",
    "extract_zip_safely",
    "ingest_cad_package",
]
