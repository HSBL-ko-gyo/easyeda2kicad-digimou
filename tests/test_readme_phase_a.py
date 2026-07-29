from __future__ import annotations

from pathlib import Path

README = Path(__file__).parents[1] / "README.md"


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_never_recommends_the_upstream_pypi_install_command() -> None:
    readme = readme_text()

    assert "python -m pip install easyeda2kicad\n" not in readme
    assert "python -m pip install easyeda2kicad " not in readme
    assert "pip install ./easyeda2kicad_digimou-1.1.0b2-py3-none-any.whl" in readme
    assert "python -m pip install -e ." in readme
    assert "generic distribution from\nPyPI installs the separate upstream" in readme


def test_readme_uses_the_required_user_workflow_order() -> None:
    readme = readme_text()
    headings = [
        "## Current capabilities",
        "## 60-second quick start",
        "## API primer and credential setup",
        "## Provider smoke tests",
        "## CAD handoff and package import",
        "## Registering libraries in one KiCad project",
        "## JLCPCB/LCSC resolution in the same command",
        "## Verify the result in KiCad",
        "## Machine JSON for automation",
        "## Troubleshooting",
        "## Legacy and advanced usage",
    ]

    positions = [readme.index(heading) for heading in headings]
    assert positions == sorted(positions)


def test_readme_capability_matrix_states_current_product_boundaries() -> None:
    section = (
        readme_text()
        .split("## Current capabilities", maxsplit=1)[1]
        .split("## 60-second quick start", maxsplit=1)[0]
    )
    flattened = section.replace("\n", " ")

    assert "`--providers` selects metadata" in flattened
    assert "`--cad-source` selects CAD" in flattened
    assert "never silently falls back to EasyEDA" in flattened
    assert "DigiKey-linked CAD" in section
    assert "Mouser / SamacSys" in section
    assert "`distributor`, `delivery_partner`, and `model_creator`" in flattened
    assert "does not provide complete DigiKey or Mouser CAD support" in flattened
    assert "2026-07-30" in section
    assert "real-package import" in section
    assert "not yet complete" in section


def test_quick_start_is_anonymous_and_has_observable_success() -> None:
    section = (
        readme_text()
        .split("## 60-second quick start", maxsplit=1)[1]
        .split("## API primer and credential setup", maxsplit=1)[0]
    )

    assert "needs internet access but no distributor account" in section
    assert "--providers lcsc" in section
    assert "--cad-source easyeda" in section
    assert "--full" in section
    assert "verification_status` is `VERIFIED`" in section
    assert "project_parts.kicad_sym" in section
    assert "project_parts.pretty/" in section
    assert "project_parts.3dshapes/" in section
    assert "examples/check_provider_manifest.py" in section


def test_partial_warning_precedes_first_three_provider_command() -> None:
    readme = readme_text()
    first_three = readme.index("--providers lcsc,digikey,mouser")
    preamble = readme[:first_three]

    assert "`PARTIAL` and exit\n> status `0`" in preamble
    assert "`distributor_records`" in preamble
    assert "`provider_errors`" in preamble
    assert "`provider_diagnostics`" in preamble
    assert "`GUEST_LOOKUP_UNSUPPORTED`" in preamble
    assert "`--require-providers`" in preamble
    assert "`DIGIKEY_CLIENT_ID`" in preamble
    assert "`DIGIKEY_CLIENT_SECRET`" in preamble
    assert "`MOUSER_API_KEY`" in preamble


def test_api_primer_explains_official_account_setup_and_token_boundary() -> None:
    section = (
        readme_text()
        .split("## API primer and credential setup", maxsplit=1)[1]
        .split("## Provider smoke tests", maxsplit=1)[0]
    )
    flattened = section.replace("\n", " ")

    assert "Visiting a public product page as a guest is not the same" in flattened
    assert "https://developer.digikey.com/products" in section
    assert "https://developer.digikey.com/faq" in section
    assert "https://www.mouser.com/api-search/" in section
    assert "Register an application" in section
    assert "Complete the online Search API request" in section
    assert "short-lived access token in memory" in flattened
    assert "do not manually paste, persist, print, or commit" in flattened
    assert "This repository cannot issue or approve credentials" in section


def test_readme_has_current_session_setup_for_all_shells_and_safe_preflight() -> None:
    section = (
        readme_text()
        .split("### Configure the current terminal only", maxsplit=1)[1]
        .split("## Provider smoke tests", maxsplit=1)[0]
    )

    assert "$env:DIGIKEY_CLIENT_ID" in section
    assert 'set "DIGIKEY_CLIENT_ID=<client-id>"' in section
    assert "export DIGIKEY_CLIENT_ID='<client-id>'" in section
    assert "python -m easyeda2kicad_digimou capabilities --machine-json" in section
    assert "authentication_configured" in section
    assert "configured' } else { 'missing" in section
    assert "if defined DIGIKEY_CLIENT_ID" in section
    assert "${!name:-}" in section
    assert "setx " not in section.casefold()
    assert "SetEnvironmentVariable" not in section
    assert "committed `.env` files" in section


def test_each_provider_has_a_smoke_and_exact_manifest_assertion() -> None:
    section = (
        readme_text()
        .split("## Provider smoke tests", maxsplit=1)[1]
        .split("## CAD handoff and package import", maxsplit=1)[0]
    )

    assert "### LCSC (anonymous)" in section
    assert "### DigiKey (credentialed)" in section
    assert "### Mouser (credentialed)" in section
    assert "--provider lcsc" in section
    assert "--provider digikey" in section
    assert "--provider mouser" in section
    assert "--require-providers" in section
    assert "exact manufacturer/full MPN" in section
    assert "no `provider_errors.digikey`" in section
    assert "no `provider_errors.mouser`" in section
    assert "`AUTH_FAILED` / HTTP 401 or 403" in section
    assert "`RATE_LIMITED` / HTTP 429" in section
    assert "`NOT_FOUND`" in section


def test_readme_documents_safe_provider_cad_handoffs_and_import() -> None:
    section = (
        readme_text()
        .split("## CAD handoff and package import", maxsplit=1)[1]
        .split("## Registering libraries", maxsplit=1)[0]
    )
    flattened = section.replace("\n", " ")

    assert "### Discover a product-specific DigiKey CAD handoff" in section
    assert '--manufacturer "Analog Devices Inc."' in section
    assert "--mpn AD5314BRM" in section
    assert "`CAD_MANUAL_DOWNLOAD_REQUIRED`" in section
    assert "`CAD_AUTH_REQUIRED`" in section
    assert "`CAD_DOWNLOAD_UNAVAILABLE`" in section
    assert "credential-free, cookie-free GET" in flattened
    assert "does not bypass login, CAPTCHA, agreements" in flattened
    assert "`cad_discovery.available_sources`" in section
    assert "`missing_artifacts`" in section
    assert "Unknown hosts remain truthful manual handoffs" in flattened
    assert "review the applicable terms" in flattened
    assert "Same Sky `MJ-2523-SMT-TR`" in section
    assert "KiCad CLI 7/9/10 and KiCad" in flattened
    assert "### Discover the Mouser / SamacSys CAD handoff" in section
    assert "--manufacturer Rectron" in section
    assert "--mpn FM220A-W" in section
    assert "never falls back to EasyEDA" in flattened
    assert "still required" in flattened
    assert "--cad-package ./downloads/official-ultralibrarian-kicad.zip" in section
    assert "--cad-package-format ultralibrarian-kicad" in section
    assert "--cad-package-format manufacturer-kicad" in section
    assert "--cad-package-evidence" in section
    assert "`CAD_PARTIAL` with `SYMBOL_UNAVAILABLE`" in section
    assert "CLI input alone is insufficient proof of identity" in flattened
    assert "hash-bound evidence" in flattened
    assert "more than 4096 entries" in flattened
    assert "`CAD_SOURCE_CONFLICT`" in section
    assert "<output>.cad-source-lock.json" in section


def test_project_registration_documents_opt_in_atomicity_and_dry_run() -> None:
    section = (
        readme_text()
        .split("## Registering libraries in one KiCad project", maxsplit=1)[1]
        .split("## JLCPCB/LCSC resolution", maxsplit=1)[0]
    )

    assert "--project ./myproject/board.kicad_pro" in section
    assert "--register-project-libraries" in section
    assert "--dry-run" in section
    assert "${KIPRJMOD}/libs/my_lib.kicad_sym" in section
    assert "${KIPRJMOD}/libs/my_lib.pretty" in section
    assert "does not edit the `.kicad_pro` file" in section
    assert "atomic" in section
    assert "detect concurrent changes" in section
    assert "roll back" in section
    assert "`--project-relative` alone" in section


def test_readme_covers_jlcpcb_statuses_and_kicad_gui_acceptance() -> None:
    readme = readme_text()
    jlcpcb = readme.split("## JLCPCB/LCSC resolution in the same command", maxsplit=1)[
        1
    ].split("## Verify the result in KiCad", maxsplit=1)[0]
    kicad = readme.split("## Verify the result in KiCad", maxsplit=1)[1].split(
        "## Machine JSON for automation", maxsplit=1
    )[0]

    assert "regardless of `--providers` or `--cad-source`" in jlcpcb
    assert "`JLCPCB_PART_FOUND`" in jlcpcb
    assert "stock may still be zero" in jlcpcb
    assert "`MANUAL_GLOBAL_SOURCING_REQUIRED`" in jlcpcb
    assert "`JLCPCB_LOOKUP_FAILED`" in jlcpcb
    assert "`JLCPCB_IDENTITY_AMBIGUOUS`" in jlcpcb
    assert "`JLCPCB_IDENTITY_CONFLICT`" in jlcpcb
    assert "Symbol Chooser" in kicad
    assert "every pin number" in kicad
    assert "pad count/numbers" in kicad
    assert "courtyard" in kicad
    assert "3D Viewer" in kicad
    assert "rotated, offset, or scaled incorrectly" in kicad
    assert "${KIPRJMOD}/..." in kicad
    assert "real Mouser/SamacSys proof remains outstanding" in kicad


def test_machine_troubleshooting_and_advanced_links_are_present() -> None:
    readme = readme_text()
    machine = readme.split("## Machine JSON for automation", maxsplit=1)[1].split(
        "## Troubleshooting", maxsplit=1
    )[0]
    troubleshooting = readme.split("## Troubleshooting", maxsplit=1)[1].split(
        "## Legacy and advanced usage", maxsplit=1
    )[0]

    assert "stdout is exactly one schema-v1 UTF-8 JSON document" in machine
    assert "`path_base=project|output|cwd`" in machine
    assert "--require-provider digikey" in machine
    assert "`70` | Unexpected internal failure" in machine
    assert "--json-events" in machine
    assert "python -m easyeda2kicad_digimou capabilities --machine-json" in machine
    assert "python -m easyeda2kicad_digimou inspect-project" in machine
    assert "python -m easyeda2kicad_digimou plan-acquire" in machine
    assert "python -m easyeda2kicad_digimou verify-artifacts" in machine
    assert "`OFFLINE_CACHE_MISS`" in troubleshooting
    assert "Windows" in troubleshooting
    assert "[Provider contract" in readme
    assert "[Architecture and security boundaries" in readme
    assert "[Current implementation/evidence state" in readme
