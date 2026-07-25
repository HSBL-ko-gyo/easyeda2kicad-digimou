from __future__ import annotations

# Global imports
from pathlib import Path


README = Path(__file__).parents[1] / "README.md"


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_never_recommends_the_upstream_pypi_install_command() -> None:
    assert "pip install easyeda2kicad" not in readme_text()


def test_readme_states_current_cad_boundaries_near_the_top() -> None:
    readme = readme_text()
    capabilities = readme.index("## Current capabilities")
    installation = readme.index("## 💾 Installation")

    assert capabilities < installation
    assert "CAD acquisition is fixed to EasyEDA" in readme
    assert "Ultra Librarian" in readme
    assert "SamacSys" in readme
    assert "does not provide complete\nDigiKey or Mouser CAD support" in readme


def test_readme_warns_before_the_first_three_provider_command() -> None:
    readme = readme_text()
    first_three_provider_command = readme.index("--providers lcsc,digikey,mouser")
    preamble = readme[:first_three_provider_command]

    assert "DIGIKEY_CLIENT_ID" in preamble
    assert "DIGIKEY_CLIENT_SECRET" in preamble
    assert "MOUSER_API_KEY" in preamble
    assert "status `0`" in preamble
    assert "`PARTIAL`" in preamble
    assert "provider_errors" in preamble
