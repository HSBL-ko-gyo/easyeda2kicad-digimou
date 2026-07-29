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
from easyeda2kicad_digimou import __main__ as cli
from easyeda2kicad_digimou.cad import MouserCadSource
from easyeda2kicad_digimou.metadata.models import (
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CAD_PACKAGE_READY,
    CadRequest,
    normalize_manufacturer,
    normalize_mpn,
)
from easyeda2kicad_digimou.providers import MouserProvider

MANUFACTURER = "Rectron"
MPN = "FM220A-W"
KICAD_CLI = {
    "7": Path(r"C:\Program Files\KiCad\7.0\bin\kicad-cli.exe"),
    "9": Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
    "10": Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"),
}


@pytest.mark.network
def test_mouser_live_fm220a_cad_handoff_smoke() -> None:
    if not os.environ.get("MOUSER_API_KEY", "").strip():
        pytest.skip("Mouser CAD handoff smoke requires MOUSER_API_KEY")

    provider = MouserProvider(timeout=30.0)
    # One official exact-part request is sufficient. Never multiply live
    # traffic with automatic retries.
    provider.max_attempts = 1

    record = provider.search_exact_mpn(MANUFACTURER, MPN)
    assert normalize_manufacturer(record.manufacturer) == normalize_manufacturer(
        MANUFACTURER
    )
    assert normalize_mpn(record.mpn) == normalize_mpn(MPN)
    assert record.distributor_part_number

    result = MouserCadSource(provider).discover(
        CadRequest(
            manufacturer=MANUFACTURER,
            mpn=MPN,
            source="mouser",
        ),
        exact_record=record,
    )

    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.package is None
    assert result.provenance.distributor == "mouser"
    assert result.provenance.delivery_partner == "samacsys"
    assert result.provenance.model_creator is None
    assert result.action_required is not None
    assert result.action_required.code == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.action_required.setup_url
    assert result.provenance.landing_url == result.action_required.setup_url

    handoff = urlsplit(result.action_required.setup_url)
    hostname = handoff.hostname or ""
    assert handoff.scheme == "https"
    assert handoff.username is None
    assert handoff.password is None
    assert handoff.fragment == ""
    assert hostname == "mouser.com" or hostname.endswith(".mouser.com")
    assert "productdetail" in {
        segment.casefold() for segment in handoff.path.split("/") if segment
    }
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
def test_mouser_live_fm220a_package_project_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_path = os.environ.get("MOUSER_FM220A_CAD_PACKAGE", "").strip()
    if not configured_path:
        pytest.skip(
            "Real package E2E requires MOUSER_FM220A_CAD_PACKAGE to name the "
            "owner-exported SamacSys KiCad package"
        )
    package_path = Path(configured_path).expanduser()
    if not package_path.is_file():
        pytest.fail("MOUSER_FM220A_CAD_PACKAGE must name an existing regular file")

    missing_versions = [
        version for version, executable in KICAD_CLI.items() if not executable.is_file()
    ]
    if missing_versions:
        pytest.fail(
            "Real package E2E requires installed KiCad CLI versions: "
            + ", ".join(missing_versions)
        )

    project_directory = tmp_path / "fm220a-validation"
    project_directory.mkdir()
    project = project_directory / "fm220a-validation.kicad_pro"
    project.write_text("{}\n", encoding="utf-8")
    output = project_directory / "libs" / MPN
    output.parent.mkdir()
    manifest = project_directory / "build" / (MPN + "-package.json")

    def no_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Local real-package E2E attempted network access")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    arguments = [
        "--manufacturer",
        MANUFACTURER,
        "--mpn",
        MPN,
        "--cad-source",
        "mouser",
        "--cad-package",
        str(package_path),
        "--cad-package-format",
        "samacsys-kicad",
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
        "manufacturer": MANUFACTURER,
        "mpn": MPN,
        "source": "mouser",
    }
    assert provenance["distributor"] == "mouser"
    assert provenance["delivery_partner"] == "samacsys"
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
    assert "${KIPRJMOD}/libs/FM220A-W.3dshapes/" in footprint_text

    symbol_table = (project_directory / "sym-lib-table").read_text(encoding="utf-8")
    footprint_table = (project_directory / "fp-lib-table").read_text(encoding="utf-8")
    assert "${KIPRJMOD}/libs/FM220A-W.kicad_sym" in symbol_table
    assert "${KIPRJMOD}/libs/FM220A-W.pretty" in footprint_table

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
