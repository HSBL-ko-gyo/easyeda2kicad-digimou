from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

from easyeda2kicad.cad.package import ingest_cad_package
from easyeda2kicad.metadata.models import CadRequest

FIXTURE = (
    Path(__file__).parent / "fixtures" / "cad_packages" / "ultralibrarian-kicad-v1"
)
KICAD_CLI = {
    "7": Path(r"C:\Program Files\KiCad\7.0\bin\kicad-cli.exe"),
    "9": Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"),
    "10": Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"),
}


def _package(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(FIXTURE.rglob("*")):
            if source.is_file():
                archive.write(source, source.relative_to(FIXTURE).as_posix())
    return path


@pytest.mark.parametrize("version", ["7", "9", "10"])
def test_ingested_symbol_and_footprint_parse_and_render_in_kicad_cli(
    tmp_path: Path,
    version: str,
) -> None:
    executable = KICAD_CLI[version]
    if not executable.is_file():
        pytest.skip("KiCad {0} CLI is not installed".format(version))
    output = tmp_path / "parts"
    ingest_cad_package(
        _package(tmp_path / "package.zip"),
        package_format="auto",
        request=CadRequest(
            manufacturer="Synthetic Devices",
            mpn="SYNTH-PART-01",
            source="digikey",
        ),
        output_base=output,
    )
    symbol_output = tmp_path / "symbol-svg"
    footprint_output = tmp_path / "footprint-svg"
    symbol_output.mkdir()
    footprint_output.mkdir()

    symbol = subprocess.run(  # noqa: S603 - executable is a fixed local KiCad path
        [
            str(executable),
            "sym",
            "export",
            "svg",
            "--output",
            str(symbol_output),
            "--symbol",
            "SYNTH-PART-01",
            str(output.with_suffix(".kicad_sym")),
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    footprint = subprocess.run(  # noqa: S603 - fixed local KiCad path
        [
            str(executable),
            "fp",
            "export",
            "svg",
            "--output",
            str(footprint_output),
            "--fp",
            "SYNTH_FP",
            str(output.with_suffix(".pretty")),
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert symbol.returncode == 0, symbol.stderr.decode(errors="replace")
    assert footprint.returncode == 0, footprint.stderr.decode(errors="replace")
    assert list(symbol_output.glob("*.svg"))
    assert list(footprint_output.glob("*.svg"))
