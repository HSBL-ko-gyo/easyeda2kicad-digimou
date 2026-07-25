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
    assert "CAD acquisition defaults to EasyEDA" in readme
    assert "Ultra Librarian" in readme
    assert "SamacSys" in readme
    assert "does not provide complete DigiKey or Mouser CAD support" in (
        readme.replace("\n", " ")
    )


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


def test_readme_describes_local_package_as_an_intermediate_safe_handoff() -> None:
    readme = readme_text()

    assert "--cad-package ./downloads/official-ultralibrarian-kicad.zip" in readme
    assert "--cad-package-format ultralibrarian-kicad" in readme
    assert "--cad-source mouser --cad-package-format samacsys-kicad" in readme
    assert "CLI input alone is insufficient" in readme
    assert "more than 4096 entries" in readme
    assert "does not automate provider website search, login, agreements, or" in readme


def test_readme_documents_api_only_digikey_manual_handoff_boundary() -> None:
    readme = readme_text()
    section = readme[
        readme.index("### Discover the DigiKey / Ultra Librarian CAD handoff") :
    ]

    assert "--providers digikey" in section
    assert "--cad-source digikey" in section
    assert "Product Information V4 API" in section
    assert "`MediaType` is `Model`" in section
    assert "never fetches or scrapes" in section
    assert "`CAD_MANUAL_DOWNLOAD_REQUIRED`" in section
    assert "`CAD_AUTH_REQUIRED`" in section
    assert "`CAD_DOWNLOAD_UNAVAILABLE`" in section
    assert "review the Ultra Librarian agreement" in section
    assert "This is not yet an end-to-end completion claim" in section.replace(
        "\n", " "
    )


def test_readme_documents_opt_in_project_registration_and_dry_run() -> None:
    readme = readme_text()
    section = readme[readme.index("### Registering libraries in one KiCad project") :]

    assert "--project ./myproject" in section
    assert "--register-project-libraries" in section
    assert "--dry-run" in section
    assert "${KIPRJMOD}/libs/my_lib.kicad_sym" in section
    assert "${KIPRJMOD}/libs/my_lib.pretty" in section
    assert "does not edit the `.kicad_pro` file" in section
    assert "`--project-relative` by itself" in section
    assert "atomic" in section
    assert "roll back" in section
