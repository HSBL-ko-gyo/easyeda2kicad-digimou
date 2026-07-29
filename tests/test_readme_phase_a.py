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
    assert "--cad-package-evidence" in readme
    assert "--cad-source mouser --cad-package-format samacsys-kicad" in readme
    assert "CLI input alone is insufficient" in readme
    assert "hash-bound" in readme
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
    assert "review the model download agreement" in section.replace("\n", " ")
    assert (
        "tests/test_provider_live.py::test_digikey_live_ad5314_cad_handoff_smoke"
        in section
    )
    assert (
        "tests/test_provider_live.py::test_digikey_live_ad5314_package_project_e2e"
        in section
    )
    assert "`DIGIKEY_AD5314_CAD_PACKAGE`" in section
    assert "guest download" in section
    assert "2026-07-29" in section
    assert "disposable temporary project" in section
    assert "KiCad 7, 9, and 10 CLIs" in section
    assert "writes no response or credential artifact" in section.replace("\n", " ")
    assert "completes the Phase C DigiKey real-service acquisition" in section.replace(
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


def test_readme_documents_same_command_jlcpcb_resolution_contract() -> None:
    readme = readme_text()
    section = readme.split(
        "### JLCPCB/LCSC resolution in the same command", maxsplit=1
    )[1].split("### Import a locally downloaded CAD package", maxsplit=1)[0]
    flattened = section.replace("\n", " ")

    assert "regardless of `--providers` or" in section
    assert "`--cad-source`" in section
    assert "No `--pcba-target` flag or second command" in section
    assert "`JLCPCB Part #` and `LCSC Part #`" in section
    assert "`JLCPCB_PART_FOUND`" in section
    assert "stock is zero" in flattened
    assert "`MANUAL_GLOBAL_SOURCING_REQUIRED`" in section
    assert "Search/order exact MPN in JLCPCB Parts Manager > Global Sourcing" in section
    assert "`JLCPCB_LOOKUP_FAILED`" in section
    assert "`JLCPCB_IDENTITY_AMBIGUOUS`" in section
    assert "`JLCPCB_IDENTITY_CONFLICT`" in section
    assert "`LIVE`, `CACHED`, and `OFFLINE_MISS`" in section
    assert "existing native `LCSC Part` field" in flattened
    assert "workflow hints" in section
    assert "do not claim" in section


def test_readme_documents_policy_safe_mouser_handoff_boundary() -> None:
    readme = readme_text()
    section = readme.split(
        "### Discover the Mouser / SamacSys CAD handoff", maxsplit=1
    )[1].split("### Import a locally downloaded CAD package", maxsplit=1)[0]
    flattened = section.replace("\n", " ")

    assert "--manufacturer Rectron" in section
    assert "--mpn FM220A-W" in section
    assert "--cad-source mouser" in section
    assert "CAD_MANUAL_DOWNLOAD_REQUIRED" in section
    assert "CAD_AUTH_REQUIRED" in section
    assert "CAD_DOWNLOAD_UNAVAILABLE" in section
    assert "never fetches or scrapes" in section
    assert "never falls back to EasyEDA" in section
    assert "SamacSys automated" in section
    assert "live-only" in section
    assert "neither the raw response nor normalized Mouser record" in flattened
    assert "reports an offline provider diagnostic" in flattened
    assert (
        "tests/test_cad_mouser_live.py::"
        "test_mouser_live_fm220a_cad_handoff_smoke" in section
    )
    assert (
        "tests/test_cad_mouser_live.py::"
        "test_mouser_live_fm220a_package_project_e2e" in section
    )
    assert "`MOUSER_FM220A_CAD_PACKAGE`" in section
    assert "disposable temporary project" in flattened
    assert "KiCad CLI 7/9/10" in section
    assert "Build or request PCB Symbol" in flattened
    assert "no replacement was chosen" in flattened
    assert "cannot claim end-to-end completion" in flattened


def test_readme_documents_validated_auto_selection_and_source_lock() -> None:
    readme = readme_text()
    section = readme.split(
        "### Deterministic automatic CAD source selection", maxsplit=1
    )[1].split("`--providers` is a comma-separated list", maxsplit=1)[0]
    flattened = section.replace("\n", " ")

    assert "--cad-source auto" in section
    assert "--cad-candidate digikey=" in section
    assert "--cad-candidate mouser=" in section
    assert "--cad-candidate-evidence" in section
    assert "product or model landing URL is only an actionable handoff" in flattened
    assert "`CAD_SOURCE_CONFLICT`" in section
    assert "EasyEDA, DigiKey/Ultra Librarian, then Mouser/SamacSys" in flattened
    assert "<output>.cad-source-lock.json" in section
    assert "package SHA-256" in section
    assert "--offline" in section
    assert "fails before output" in flattened
    assert "remain no-fallback paths" in flattened
