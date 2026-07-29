from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import easyeda2kicad_digimou.__main__ as cli

ROOT = Path(__file__).parents[1]
README = ROOT / "README.md"
CHECKER = ROOT / "examples" / "check_provider_manifest.py"


def test_documented_lcsc_manifest_checker_runs_end_to_end() -> None:
    completed = subprocess.run(  # noqa: S603 - fixed interpreter/repository script
        [
            sys.executable,
            str(CHECKER),
            str(ROOT / "docs" / "examples" / "OPA333AIDBVR.manifest.json"),
            "--manufacturer",
            "Texas Instruments",
            "--mpn",
            "OPA333AIDBVR",
            "--provider",
            "lcsc",
            "--verification-status",
            "VERIFIED",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "providers": ["lcsc"],
        "status": "PASS",
        "verification_status": "VERIFIED",
    }


def test_manifest_checker_fails_closed_for_missing_provider(tmp_path: Path) -> None:
    source = json.loads(
        (ROOT / "docs" / "examples" / "OPA333AIDBVR.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    completed = subprocess.run(  # noqa: S603 - fixed interpreter/repository script
        [
            sys.executable,
            str(CHECKER),
            str(path),
            "--manufacturer",
            "Texas Instruments",
            "--mpn",
            "OPA333AIDBVR",
            "--provider",
            "digikey",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {"status": "FAIL"}
    assert str(tmp_path) not in completed.stdout


@pytest.mark.parametrize(
    "arguments",
    [
        [
            "--manufacturer",
            "Texas Instruments",
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "lcsc",
            "--cad-source",
            "easyeda",
            "--full",
            "--output",
            "./libs/project_parts",
            "--manifest-json",
            "./build/OPA333AIDBVR-lcsc.json",
        ],
        [
            "--manufacturer",
            "Texas Instruments",
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "digikey",
            "--cad-source",
            "easyeda",
            "--manifest-json",
            "./build/smoke-digikey.json",
            "--require-providers",
        ],
        [
            "--manufacturer",
            "Texas Instruments",
            "--mpn",
            "LM321MF/NOPB",
            "--providers",
            "mouser",
            "--cad-source",
            "easyeda",
            "--manifest-json",
            "./build/smoke-mouser.json",
            "--require-providers",
        ],
        [
            "--manufacturer",
            "Analog Devices Inc.",
            "--mpn",
            "AD5314BRM",
            "--providers",
            "digikey",
            "--cad-source",
            "digikey",
            "--manifest-json",
            "./build/AD5314BRM-handoff.json",
        ],
        [
            "--manufacturer",
            "Rectron",
            "--mpn",
            "FM220A-W",
            "--providers",
            "mouser",
            "--cad-source",
            "mouser",
            "--manifest-json",
            "./build/FM220A-W-handoff.json",
        ],
        [
            "--manufacturer",
            "Analog Devices Inc.",
            "--mpn",
            "AD5314BRM",
            "--cad-source",
            "digikey",
            "--cad-package",
            "./downloads/official-ultralibrarian-kicad.zip",
            "--cad-package-format",
            "ultralibrarian-kicad",
            "--cad-package-evidence",
            "./downloads/AD5314BRM.evidence.json",
            "--full",
            "--output",
            "./libs/provider_parts",
            "--manifest-json",
            "./build/AD5314BRM-import.json",
        ],
        [
            "--manufacturer",
            "Example Manufacturer",
            "--mpn",
            "EXACT-MPN-INCLUDING-SUFFIX",
            "--cad-source",
            "auto",
            "--cad-candidate",
            "digikey=./downloads/ultralibrarian-kicad.zip",
            "--cad-candidate",
            "mouser=./downloads/samacsys-kicad.zip",
            "--full",
            "--output",
            "./libs/provider_parts",
            "--manifest-json",
            "./build/auto-selection.json",
        ],
        [
            "--full",
            "--lcsc_id",
            "C2040",
            "--output",
            "./myproject/libs/my_lib",
            "--project",
            "./myproject/board.kicad_pro",
            "--register-project-libraries",
        ],
    ],
)
def test_documented_human_cli_commands_parse(arguments: list[str]) -> None:
    parsed = cli.get_parser().parse_args(arguments)

    assert parsed is not None


def test_documented_machine_and_read_only_commands_parse() -> None:
    machine = cli.get_acquire_parser().parse_args(
        [
            "--manufacturer",
            "Texas Instruments",
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "lcsc,digikey",
            "--cad-source",
            "easyeda",
            "--full",
            "--output",
            "./libs/parts",
            "--machine-json",
        ]
    )
    capabilities = cli.get_headless_parser("capabilities").parse_args(
        ["--machine-json"]
    )
    inspection = cli.get_headless_parser("inspect-project").parse_args(
        ["./board.kicad_pro", "--machine-json"]
    )
    plan = cli.get_headless_parser("plan-acquire").parse_args(
        [
            "--manufacturer",
            "Texas Instruments",
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "lcsc,digikey",
            "--offline",
            "--machine-json",
        ]
    )
    verification = cli.get_headless_parser("verify-artifacts").parse_args(
        ["./result.json", "--output-root", "./libs", "--machine-json"]
    )

    assert machine.machine_json is True
    assert capabilities.machine_json is True
    assert inspection.project_path == "./board.kicad_pro"
    assert plan.offline is True
    assert verification.result_path == "./result.json"


def test_readme_relative_links_resolve() -> None:
    readme = README.read_text(encoding="utf-8")
    targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", readme)
    local_targets = [
        target.split("#", maxsplit=1)[0]
        for target in targets
        if not target.startswith(("http://", "https://", "#"))
    ]

    assert local_targets
    for target in local_targets:
        assert (ROOT / target).exists(), target


def test_readme_contains_no_secret_or_machine_specific_path() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "C:\\Users\\HSBL-PC" not in readme
    assert "/home/hsbl" not in readme.casefold()
    assert not re.search(r"AKIA[0-9A-Z]{16}", readme)
    assert not re.search(r"gh[pousr]_[A-Za-z0-9_]{20,}", readme)
    assert "-----BEGIN PRIVATE KEY-----" not in readme
