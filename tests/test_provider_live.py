from __future__ import annotations

# Global imports
import json
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Mapping, cast
from urllib.parse import parse_qsl, urlsplit

import pytest

# Local imports
from easyeda2kicad import __main__ as cli
from easyeda2kicad.cad import DigiKeyCadSource
from easyeda2kicad.metadata.models import (
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CAD_PACKAGE_READY,
    CadRequest,
    normalize_manufacturer,
    normalize_mpn,
)
from easyeda2kicad.providers import DigiKeyProvider, MouserProvider


KICAD_CLI = {
    "7": Path(r"C:\Program Files\KiCad\7.0\bin\kicad-cli.exe"),
    "9": Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
    "10": Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"),
}


@pytest.mark.network
def test_digikey_live_exact_mpn_smoke() -> None:
    required = ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET")
    if not all(os.environ.get(name, "").strip() for name in required):
        pytest.skip(
            "DigiKey live smoke requires DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET"
        )

    requested_mpn = "OPA333AIDBVR"
    provider = DigiKeyProvider(timeout=30.0)
    # One OAuth transaction and one keyword request are the minimum. Disable
    # automatic retries so this smoke test cannot multiply live API traffic.
    provider.max_attempts = 1

    record = provider.search_exact_mpn(None, requested_mpn)

    assert record.provider == "digikey"
    assert normalize_mpn(record.mpn) == normalize_mpn(requested_mpn)


@pytest.mark.network
def test_digikey_live_ad5314_cad_handoff_smoke() -> None:
    required = ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET")
    if not all(os.environ.get(name, "").strip() for name in required):
        pytest.skip(
            "DigiKey CAD handoff smoke requires DIGIKEY_CLIENT_ID and "
            "DIGIKEY_CLIENT_SECRET"
        )

    requested_manufacturer = "Analog Devices Inc."
    requested_mpn = "AD5314BRM"
    provider = DigiKeyProvider(timeout=30.0)
    # One OAuth transaction, one exact keyword lookup, and one Media request
    # are sufficient. Never multiply live traffic with automatic retries.
    provider.max_attempts = 1

    record = provider.search_exact_mpn(requested_manufacturer, requested_mpn)
    assert normalize_manufacturer(record.manufacturer) == normalize_manufacturer(
        requested_manufacturer
    )
    assert normalize_mpn(record.mpn) == normalize_mpn(requested_mpn)
    assert record.distributor_part_number

    result = DigiKeyCadSource(provider).discover(
        CadRequest(
            manufacturer=requested_manufacturer,
            mpn=requested_mpn,
            source="digikey",
        ),
        exact_record=record,
    )

    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.package is None
    assert result.provenance.distributor == "digikey"
    assert result.provenance.delivery_partner == "ultralibrarian"
    assert result.provenance.model_creator is None
    assert result.action_required is not None
    assert result.action_required.code == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.action_required.setup_url
    assert result.provenance.landing_url == result.action_required.setup_url

    handoff = urlsplit(result.action_required.setup_url)
    assert handoff.scheme == "https"
    assert handoff.username is None
    assert handoff.password is None
    assert handoff.fragment == ""
    assert handoff.hostname in {
        "mm.digikey.com",
        "ultralibrarian.com",
        "app.ultralibrarian.com",
    } or (handoff.hostname or "").endswith(".ultralibrarian.com")
    secret_query_names = {
        "access_token",
        "apikey",
        "api_key",
        "client_secret",
        "key",
        "signature",
        "token",
    }
    assert not secret_query_names.intersection(
        name.casefold() for name, _value in parse_qsl(handoff.query)
    )


@pytest.mark.network
def test_digikey_live_ad5314_package_project_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_path = os.environ.get("DIGIKEY_AD5314_CAD_PACKAGE", "").strip()
    if not configured_path:
        pytest.skip(
            "Real package E2E requires DIGIKEY_AD5314_CAD_PACKAGE to name the "
            "owner-downloaded Ultra Librarian ZIP"
        )
    package_path = Path(configured_path).expanduser()
    if not package_path.is_file():
        pytest.fail("DIGIKEY_AD5314_CAD_PACKAGE must name an existing regular file")

    missing_versions = [
        version for version, executable in KICAD_CLI.items() if not executable.is_file()
    ]
    if missing_versions:
        pytest.fail(
            "Real package E2E requires installed KiCad CLI versions: "
            + ", ".join(missing_versions)
        )

    project_directory = tmp_path / "ad5314-validation"
    project_directory.mkdir()
    project = project_directory / "ad5314-validation.kicad_pro"
    project.write_text("{}\n", encoding="utf-8")
    output = project_directory / "libs" / "AD5314BRM"
    output.parent.mkdir()
    manifest = project_directory / "build" / "AD5314BRM-package.json"

    def no_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Local real-package E2E attempted network access")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    arguments = [
        "--manufacturer",
        "Analog Devices Inc.",
        "--mpn",
        "AD5314BRM",
        "--cad-source",
        "digikey",
        "--cad-package",
        str(package_path),
        "--cad-package-format",
        "ultralibrarian-kicad",
        "--output",
        str(output),
        "--manifest-json",
        str(manifest),
        "--project",
        str(project),
        "--register-project-libraries",
    ]

    assert cli.main(arguments) == 0
    before_rerun = {
        path.relative_to(project_directory).as_posix(): path.read_bytes()
        for path in project_directory.rglob("*")
        if path.is_file()
    }
    assert cli.main(arguments) == 0
    after_rerun = {
        path.relative_to(project_directory).as_posix(): path.read_bytes()
        for path in project_directory.rglob("*")
        if path.is_file()
    }
    assert after_rerun == before_rerun

    manifest_text = manifest.read_text(encoding="utf-8")
    for absolute_path in (tmp_path.resolve(), package_path.resolve()):
        assert str(absolute_path) not in manifest_text
        assert absolute_path.as_posix() not in manifest_text
    payload = cast(Mapping[str, Any], json.loads(manifest_text))
    discovery = cast(Mapping[str, Any], payload["cad_discovery"])
    provenance = cast(Mapping[str, Any], discovery["provenance"])
    package = cast(Mapping[str, Any], discovery["package"])
    package_request = cast(Mapping[str, Any], package["request"])
    cad = cast(Mapping[str, Any], payload["cad"])
    assert discovery["status"] == CAD_PACKAGE_READY
    assert package_request == {
        "manufacturer": "Analog Devices Inc.",
        "mpn": "AD5314BRM",
        "source": "digikey",
    }
    assert provenance["distributor"] == "digikey"
    assert provenance["delivery_partner"] == "ultralibrarian"
    assert isinstance(provenance["model_creator"], (str, type(None)))
    assert provenance["retrieval_mode"] == "local-package"
    assert isinstance(provenance["package_hash"], str)
    assert len(provenance["package_hash"]) == 64
    artifacts = cast(list[Mapping[str, Any]], package["artifacts"])
    assert artifacts
    artifact_kinds = {artifact["kind"] for artifact in artifacts}
    assert {"symbol", "footprint"} <= artifact_kinds
    assert artifact_kinds & {"step", "wrl"}
    assert all(
        isinstance(artifact["sha256"], str) and len(artifact["sha256"]) == 64
        for artifact in artifacts
    )
    assert all(
        isinstance(artifact["relative_path"], str)
        and not Path(artifact["relative_path"]).is_absolute()
        and "\\" not in artifact["relative_path"]
        for artifact in artifacts
    )

    symbol_name = cad["symbol_name"]
    footprint_name = cad["footprint_name"]
    assert isinstance(symbol_name, str) and symbol_name
    assert isinstance(footprint_name, str) and footprint_name
    symbol_library = output.with_suffix(".kicad_sym")
    footprint_library = output.with_suffix(".pretty")
    model_library = output.with_suffix(".3dshapes")
    assert symbol_library.is_file()
    footprint_path = footprint_library / (footprint_name + ".kicad_mod")
    assert footprint_path.is_file()
    assert any(model_library.iterdir())
    footprint_text = footprint_path.read_text(encoding="utf-8")
    assert "${KIPRJMOD}/libs/AD5314BRM.3dshapes/" in footprint_text

    symbol_table = (project_directory / "sym-lib-table").read_text(encoding="utf-8")
    footprint_table = (project_directory / "fp-lib-table").read_text(encoding="utf-8")
    assert "${KIPRJMOD}/libs/AD5314BRM.kicad_sym" in symbol_table
    assert "${KIPRJMOD}/libs/AD5314BRM.pretty" in footprint_table

    for version, executable in KICAD_CLI.items():
        symbol_svg = tmp_path / ("symbol-svg-" + version)
        footprint_svg = tmp_path / ("footprint-svg-" + version)
        symbol_svg.mkdir()
        footprint_svg.mkdir()
        symbol_result = subprocess.run(  # noqa: S603 - fixed local KiCad path
            [
                str(executable),
                "sym",
                "export",
                "svg",
                "--output",
                str(symbol_svg),
                "--symbol",
                symbol_name,
                str(symbol_library),
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
        footprint_result = subprocess.run(  # noqa: S603 - fixed local KiCad path
            [
                str(executable),
                "fp",
                "export",
                "svg",
                "--output",
                str(footprint_svg),
                "--fp",
                footprint_name,
                str(footprint_library),
            ],
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert symbol_result.returncode == 0, symbol_result.stderr.decode(
            errors="replace"
        )
        assert footprint_result.returncode == 0, footprint_result.stderr.decode(
            errors="replace"
        )
        assert list(symbol_svg.glob("*.svg"))
        assert list(footprint_svg.glob("*.svg"))


@pytest.mark.network
def test_mouser_live_exact_mpn_smoke() -> None:
    if not os.environ.get("MOUSER_API_KEY", "").strip():
        pytest.skip("Mouser live smoke requires MOUSER_API_KEY")

    requested_mpn = "LM321MF/NOPB"
    provider = MouserProvider(timeout=30.0)
    # A single official exact-part request is sufficient for this smoke test.
    provider.max_attempts = 1

    record = provider.search_exact_mpn(None, requested_mpn)

    assert record.provider == "mouser"
    assert normalize_mpn(record.mpn) == normalize_mpn(requested_mpn)
