"""Portable, no-network regression evidence for the legacy C2040 CLI path.

The checked-in symbol and footprint were generated from upstream baseline
``fff10a38619963d7cb1c57d779655a9ea4572e95``.  The CAD fixture is the real
C2040 cache envelope with non-ASCII JSON escaped so Windows locale decoding
cannot change its semantics.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path
from typing import NoReturn

import pytest

from easyeda2kicad.__main__ import main


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "legacy"
CAD_FIXTURE = FIXTURE_ROOT / "C2040.json"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"
SYMBOL_GOLDEN = GOLDEN_ROOT / "legacy_c2040.kicad_sym"
FOOTPRINT_NAME = "LQFN-56_L7.0-W7.0-P0.4-EP.kicad_mod"
FOOTPRINT_GOLDEN = GOLDEN_ROOT / FOOTPRINT_NAME

CANONICAL_SHA256 = {
    "legacy_c2040.kicad_sym": (
        "56548f0c154ccee100f0c00d8b85b76ed2fc0126913aa960c38f517f86cbb934"
    ),
    FOOTPRINT_NAME: (
        "f611dd6b66453dd3a9d8d821f7025698c7e050791c44263c3484b2be71509847"
    ),
}


def _unexpected_network(*args: object, **kwargs: object) -> NoReturn:
    """Fail immediately if a cache regression attempts the EasyEDA network."""

    del args, kwargs
    raise AssertionError("legacy cached CLI attempted a network request")


def _canonical_bytes(path: Path) -> bytes:
    """Return platform-independent UTF-8 bytes with canonical LF newlines."""

    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return (text.rstrip("\n") + "\n").encode("utf-8")


def test_legacy_c2040_cli_is_offline_and_matches_upstream_golden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The legacy symbol+footprint CLI remains deterministic without the network."""

    cache_dir = tmp_path / ".easyeda_cache"
    cache_dir.mkdir()
    shutil.copyfile(CAD_FIXTURE, cache_dir / "C2040.json")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(urllib.request, "urlopen", _unexpected_network)

    output = tmp_path / "legacy_c2040"
    exit_code = main(
        [
            "--lcsc_id",
            "C2040",
            "--symbol",
            "--footprint",
            "--output",
            str(output),
            "--project-relative",
            "--use-cache",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.startswith("-- easyeda2kicad.py v")
    assert captured.out.rstrip().endswith(" --")
    assert len(captured.out.splitlines()) == 1
    assert captured.err == ""

    generated_symbol = output.with_suffix(".kicad_sym")
    generated_footprint = output.with_suffix(".pretty") / FOOTPRINT_NAME
    assert generated_symbol.is_file()
    assert generated_footprint.is_file()

    for generated, golden in (
        (generated_symbol, SYMBOL_GOLDEN),
        (generated_footprint, FOOTPRINT_GOLDEN),
    ):
        generated_bytes = _canonical_bytes(generated)
        golden_bytes = _canonical_bytes(golden)
        assert generated_bytes == golden_bytes
        assert (
            hashlib.sha256(generated_bytes).hexdigest() == CANONICAL_SHA256[golden.name]
        )

    assert not output.with_suffix(".3dshapes").exists()
