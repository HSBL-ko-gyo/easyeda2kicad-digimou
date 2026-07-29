__version__ = "1.1.0b3"
DISPLAY_NAME = "easyeda2kicad +DigiMou"
DISTRIBUTION_NAME = "easyeda2kicad-digimou"
CLI_NAME = "easyeda2kicad-digimou"
GENERATOR_URL = "https://github.com/uPesy/easyeda2kicad.py"


def version_identity() -> str:
    """Return the unambiguous public command identity."""

    return f"{CLI_NAME} {__version__} ({DISPLAY_NAME}, unofficial derivative)"
