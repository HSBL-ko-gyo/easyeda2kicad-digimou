"""
easyeda2kicad_digimou - +DigiMou EasyEDA-to-KiCad conversion package

A Python tool for converting EasyEDA symbols, footprints, and 3D models
to KiCad library format.
"""

# Local imports
from ._version import (
    CLI_NAME,
    DISPLAY_NAME,
    DISTRIBUTION_NAME,
    __version__,
    version_identity,
)

__author__ = "uPesy"
__email__ = "contact@upesy.com"

# Local imports
# Import main functionality for easy access
from .easyeda.easyeda_api import EasyedaApi
from .easyeda.easyeda_importer import (
    Easyeda3dModelImporter,
    EasyedaFootprintImporter,
    EasyedaSymbolImporter,
)
from .kicad.export_kicad_3d_model import Exporter3dModelKicad
from .kicad.export_kicad_footprint import ExporterFootprintKicad
from .kicad.export_kicad_symbol import ExporterSymbolKicad

__all__ = [
    "__version__",
    "CLI_NAME",
    "DISPLAY_NAME",
    "DISTRIBUTION_NAME",
    "version_identity",
    "__author__",
    "__email__",
    "EasyedaApi",
    "EasyedaSymbolImporter",
    "EasyedaFootprintImporter",
    "Easyeda3dModelImporter",
    "ExporterSymbolKicad",
    "ExporterFootprintKicad",
    "Exporter3dModelKicad",
]
