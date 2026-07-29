from __future__ import annotations

import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional, cast

import pytest

import easyeda2kicad.cad.package as package_module
from easyeda2kicad import __main__ as cli
from easyeda2kicad.cad.errors import CadPackageError
from easyeda2kicad.cad.kicad import parse_document
from easyeda2kicad.cad.package import ingest_cad_package
from easyeda2kicad.metadata.models import CAD_PACKAGE_READY, CadRequest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "cad_packages"
MANUFACTURER = "Synthetic Devices"
MPN = "SYNTH-PART-01"


def _zip_tree(
    source: Path,
    destination: Path,
    *,
    mutate: Callable[[str, bytes], bytes | None] | None = None,
    extras: dict[str, bytes] | None = None,
) -> Path:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source).as_posix()
            original = path.read_bytes()
            value: bytes | None = (
                mutate(relative, original) if mutate is not None else original
            )
            if value is not None:
                archive.writestr(relative, value)
        for relative, value in sorted((extras or {}).items()):
            archive.writestr(relative, value)
    return destination


def _request(source: str = "digikey") -> CadRequest:
    return CadRequest(manufacturer=MANUFACTURER, mpn=MPN, source=source)


def _attested_ultralibrarian_archive(
    destination: Path,
    *,
    one_mpn_signal_only: bool = False,
    include_filename_variants: bool = False,
) -> Path:
    fixture = FIXTURE_ROOT / "ultralibrarian-kicad-v1" / "UltraLibrarian"
    symbol_text = (fixture / "20260725.kicad_sym").read_text(encoding="utf-8")
    symbol_text = (
        symbol_text.replace(
            '    (property "Manufacturer" "Synthetic Devices" (at 0 0 0)\n'
            "      (effects (font (size 1.27 1.27)) hide)\n"
            "    )\n",
            "",
        )
        .replace(
            '    (property "MPN" "SYNTH-PART-01" (at 0 0 0)\n'
            "      (effects (font (size 1.27 1.27)) hide)\n"
            "    )\n",
            "",
        )
        .replace(
            '    (property "Model Creator" "Synthetic Fixture Team" (at 0 0 0)\n'
            "      (effects (font (size 1.27 1.27)) hide)\n"
            "    )\n",
            "",
        )
    )
    if not one_mpn_signal_only:
        symbol_text = symbol_text.replace(
            '(property "Datasheet" ""',
            '(property "Datasheet" "SYNTH-PART-01"',
        )
    footprint = (fixture / "Synthetic.pretty" / "SYNTH_FP.kicad_mod").read_bytes()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "KiCADv6/2026-07-28_16-34-01.kicad_sym",
            symbol_text.encode("utf-8"),
        )
        archive.writestr(
            "KiCADv6/footprints.pretty/SYNTH_FP.kicad_mod",
            footprint,
        )
        if include_filename_variants:
            archive.writestr(
                "KiCADv6/footprints.pretty/SYNTH_FP-L.kicad_mod",
                footprint + b"\n",
            )
            archive.writestr(
                "KiCADv6/footprints.pretty/SYNTH_FP-M.kicad_mod",
                footprint + b"\n\n",
            )
        archive.writestr(
            "SYNTH_FP.wrl",
            (fixture / "3D" / "SYNTH_FP.wrl").read_bytes(),
        )
    return destination


def _write_digikey_evidence(
    destination: Path,
    archive: Path,
    **overrides: object,
) -> Path:
    payload: dict[str, object] = {
        "agreement_url": (
            "https://www.digikey.com/en/models/123456?tab=ultralibrarian"
        ),
        "delivery_partner": "ultralibrarian",
        "landing_url": ("https://www.digikey.com/en/models/123456?tab=ultralibrarian"),
        "manufacturer": MANUFACTURER,
        "model_creator": None,
        "mpn": MPN,
        "package_format": "ultralibrarian-kicad",
        "package_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "product_url": (
            "https://www.digikey.com/en/products/detail/"
            "synthetic-devices/SYNTH-PART-01/123456"
        ),
        "retrieval_mode": "manual-official-download",
        "retrieved_at_utc": "2026-07-28T16:34:01Z",
        "schema_version": 1,
        "source": "digikey",
    }
    payload.update(overrides)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


@pytest.mark.parametrize(
    ("fixture_name", "source", "format_name", "partner"),
    [
        (
            "ultralibrarian-kicad-v1",
            "digikey",
            "ultralibrarian-kicad",
            "ultralibrarian",
        ),
        ("samacsys-kicad-v1", "mouser", "samacsys-kicad", "samacsys"),
    ],
)
def test_synthetic_provider_layout_imports_atomically_and_is_idempotent(
    tmp_path: Path,
    fixture_name: str,
    source: str,
    format_name: str,
    partner: str,
) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / fixture_name,
        tmp_path / "{0}.zip".format(source),
    )
    output = tmp_path / "parts"

    first = ingest_cad_package(
        archive,
        package_format="auto",
        request=_request(source),
        output_base=output,
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and path != archive
    }
    second = ingest_cad_package(
        archive,
        package_format=format_name,
        request=_request(source),
        output_base=output,
    )
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and path != archive
    }

    assert first.discovery.status == CAD_PACKAGE_READY
    assert first.package.format_name == format_name
    assert first.package.format_version == "1"
    assert first.package.provenance.distributor == source
    assert first.package.provenance.delivery_partner == partner
    assert first.package.provenance.model_creator == "synthetic fixture team"
    assert first.cad.distributor == source
    assert first.cad.delivery_partner == partner
    assert first.cad.model_creator == "synthetic fixture team"
    assert (
        second.package.provenance.package_hash == first.package.provenance.package_hash
    )
    assert before == after
    symbol = output.with_suffix(".kicad_sym")
    assert symbol.is_file()
    assert '(property "Footprint" "parts:SYNTH_FP"' in symbol.read_text(
        encoding="utf-8"
    )
    footprint = output.with_suffix(".pretty") / "SYNTH_FP.kicad_mod"
    assert footprint.is_file()
    assert "${KIPRJMOD}/parts.3dshapes/SYNTH_FP.wrl" in footprint.read_text(
        encoding="utf-8"
    )
    assert (output.with_suffix(".3dshapes") / "SYNTH_FP.wrl").is_file()
    assert {artifact.kind for artifact in first.package.artifacts} == {
        "symbol",
        "footprint",
        "wrl",
    }
    assert all(len(artifact.sha256) == 64 for artifact in first.cad.artifacts)


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_symbol_footprint_property_must_be_unique(
    tmp_path: Path,
    mutation: str,
) -> None:
    def mutate_footprint_property(relative: str, value: bytes) -> bytes:
        if not relative.endswith(".kicad_sym"):
            return value
        text = value.decode("utf-8").replace("\r\n", "\n")
        property_block = (
            '    (property "Footprint" "Synthetic:SYNTH_FP" (at 0 0 0)\n'
            "      (effects (font (size 1.27 1.27)) hide)\n"
            "    )\n"
        )
        if mutation == "missing":
            return text.replace(property_block, "").encode("utf-8")
        return text.replace(
            property_block,
            property_block + property_block,
        ).encode("utf-8")

    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "{0}.zip".format(mutation),
        mutate=mutate_footprint_property,
    )
    output = tmp_path / "parts"

    with pytest.raises(
        CadPackageError,
        match="CAD_SYMBOL_FOOTPRINT_PROPERTY_INVALID",
    ):
        ingest_cad_package(
            archive,
            package_format="auto",
            request=_request(),
            output_base=output,
        )

    assert not output.with_suffix(".kicad_sym").exists()
    assert not output.with_suffix(".pretty").exists()
    assert not output.with_suffix(".3dshapes").exists()


def test_identity_mismatch_fails_before_any_output(tmp_path: Path) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "identity.zip",
    )
    output = tmp_path / "parts"

    with pytest.raises(CadPackageError, match="CAD_IDENTITY_MISMATCH"):
        ingest_cad_package(
            archive,
            package_format="ultralibrarian-kicad",
            request=CadRequest(
                manufacturer=MANUFACTURER,
                mpn="SYNTH-PART-01-T",
                source="digikey",
            ),
            output_base=output,
        )

    assert not output.with_suffix(".kicad_sym").exists()
    assert not output.with_suffix(".pretty").exists()
    assert not output.with_suffix(".3dshapes").exists()


def test_identity_must_be_proven_by_package_not_only_cli_input(tmp_path: Path) -> None:
    def remove_identity(relative: str, value: bytes) -> bytes:
        if not relative.endswith(".kicad_sym"):
            return value
        text = value.decode("utf-8").replace("\r\n", "\n")
        return text.replace(
            '    (property "Manufacturer" "Synthetic Devices" (at 0 0 0)\n'
            "      (effects (font (size 1.27 1.27)) hide)\n"
            "    )\n",
            "",
        ).encode("utf-8")

    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "unproven.zip",
        mutate=remove_identity,
    )
    output = tmp_path / "parts"

    with pytest.raises(CadPackageError, match="CAD_IDENTITY_UNPROVEN"):
        ingest_cad_package(
            archive,
            package_format="auto",
            request=_request(),
            output_base=output,
        )

    assert not output.with_suffix(".kicad_sym").exists()
    assert not output.with_suffix(".pretty").exists()
    assert not output.with_suffix(".3dshapes").exists()


def test_hash_bound_manual_handoff_evidence_accepts_real_ultra_layout(
    tmp_path: Path,
) -> None:
    archive = _attested_ultralibrarian_archive(
        tmp_path / "official.zip",
        include_filename_variants=True,
    )
    evidence = _write_digikey_evidence(tmp_path / "evidence.json", archive)
    output = tmp_path / "parts"

    result = ingest_cad_package(
        archive,
        package_format="auto",
        request=_request(),
        output_base=output,
        evidence_path=evidence,
    )

    assert result.package.format_name == "ultralibrarian-kicad"
    assert result.package.format_version == "2"
    assert result.package.provenance.retrieval_mode == "manual-official-download"
    assert result.package.provenance.delivery_partner == "ultralibrarian"
    assert result.package.provenance.model_creator is None
    assert result.package.provenance.landing_url == (
        "https://www.digikey.com/en/models/123456?tab=ultralibrarian"
    )
    symbol_text = output.with_suffix(".kicad_sym").read_text(encoding="utf-8")
    assert '(property "Manufacturer" "Synthetic Devices"' in symbol_text
    assert '(property "MPN" "SYNTH-PART-01"' in symbol_text
    assert (output.with_suffix(".pretty") / "SYNTH_FP.kicad_mod").is_file()
    assert (output.with_suffix(".3dshapes") / "SYNTH_FP.wrl").is_file()


def test_real_ultra_layout_without_hash_bound_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    archive = _attested_ultralibrarian_archive(tmp_path / "official.zip")

    with pytest.raises(CadPackageError, match="CAD_PACKAGE_FORMAT_UNPROVEN"):
        ingest_cad_package(
            archive,
            package_format="ultralibrarian-kicad",
            request=_request(),
            output_base=tmp_path / "parts",
        )


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"package_sha256": "0" * 64}, "CAD_PACKAGE_EVIDENCE_HASH_MISMATCH"),
        ({"mpn": "SYNTH-PART-01-T"}, "CAD_PACKAGE_EVIDENCE_IDENTITY_MISMATCH"),
        (
            {
                "landing_url": (
                    "https://www.digikey.com/en/models/123456?access_token=canary"
                )
            },
            "CAD_PACKAGE_EVIDENCE_URL_UNSAFE",
        ),
        ({"raw_response": {"private": True}}, "CAD_PACKAGE_EVIDENCE_INVALID"),
    ],
)
def test_manual_handoff_evidence_is_strict_and_fail_closed(
    tmp_path: Path,
    overrides: dict[str, object],
    error_code: str,
) -> None:
    archive = _attested_ultralibrarian_archive(tmp_path / "official.zip")
    evidence = _write_digikey_evidence(
        tmp_path / "evidence.json",
        archive,
        **overrides,
    )

    with pytest.raises(CadPackageError, match=error_code):
        ingest_cad_package(
            archive,
            package_format="ultralibrarian-kicad",
            request=_request(),
            output_base=tmp_path / "parts",
            evidence_path=evidence,
        )


def test_attested_package_still_requires_multiple_exact_mpn_signals(
    tmp_path: Path,
) -> None:
    archive = _attested_ultralibrarian_archive(
        tmp_path / "official.zip",
        one_mpn_signal_only=True,
    )
    evidence = _write_digikey_evidence(tmp_path / "evidence.json", archive)

    with pytest.raises(CadPackageError, match="CAD_IDENTITY_UNPROVEN"):
        ingest_cad_package(
            archive,
            package_format="ultralibrarian-kicad",
            request=_request(),
            output_base=tmp_path / "parts",
            evidence_path=evidence,
        )


def test_explicit_adapter_and_source_must_match_package_evidence(
    tmp_path: Path,
) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "package.zip",
    )

    with pytest.raises(CadPackageError, match="CAD_PACKAGE_FORMAT_UNPROVEN"):
        ingest_cad_package(
            archive,
            package_format="samacsys-kicad",
            request=_request("mouser"),
            output_base=tmp_path / "wrong-format",
        )
    with pytest.raises(CadPackageError, match="CAD_PACKAGE_SOURCE_MISMATCH"):
        ingest_cad_package(
            archive,
            package_format="ultralibrarian-kicad",
            request=_request("mouser"),
            output_base=tmp_path / "wrong-source",
        )


def test_multiple_exact_symbols_are_rejected(tmp_path: Path) -> None:
    def duplicate_symbol(relative: str, value: bytes) -> bytes:
        if not relative.endswith(".kicad_sym"):
            return value
        text = value.decode("utf-8")
        document = parse_document(text, "kicad_symbol_lib")
        symbol = next(form.text for form in document.forms if form.head == "symbol")
        return (
            text[: document.root_end - 1].rstrip()
            + "\n  "
            + symbol.replace("\n", "\n  ")
            + "\n)"
            + text[document.root_end :]
        ).encode("utf-8")

    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "symbols.zip",
        mutate=duplicate_symbol,
    )

    with pytest.raises(CadPackageError, match="CAD_SYMBOL_AMBIGUOUS"):
        ingest_cad_package(
            archive,
            package_format="auto",
            request=_request(),
            output_base=tmp_path / "parts",
        )


def test_multiple_matching_footprints_are_rejected(tmp_path: Path) -> None:
    footprint = (
        FIXTURE_ROOT
        / "ultralibrarian-kicad-v1"
        / "UltraLibrarian"
        / "Synthetic.pretty"
        / "SYNTH_FP.kicad_mod"
    ).read_bytes()
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "footprints.zip",
        extras={"UltraLibrarian/Other.pretty/SYNTH_FP.kicad_mod": footprint},
    )

    with pytest.raises(CadPackageError, match="CAD_FOOTPRINT_AMBIGUOUS"):
        ingest_cad_package(
            archive,
            package_format="auto",
            request=_request(),
            output_base=tmp_path / "parts",
        )


def test_colliding_flattened_model_names_are_rejected(tmp_path: Path) -> None:
    model = (
        FIXTURE_ROOT
        / "ultralibrarian-kicad-v1"
        / "UltraLibrarian"
        / "3D"
        / "SYNTH_FP.wrl"
    ).read_bytes()
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "models.zip",
        extras={"UltraLibrarian/Other/SYNTH_FP.wrl": model},
    )

    with pytest.raises(CadPackageError, match="CAD_3D_AMBIGUOUS"):
        ingest_cad_package(
            archive,
            package_format="auto",
            request=_request(),
            output_base=tmp_path / "parts",
        )


def test_missing_3d_malformed_symbol_and_pin_pad_mismatch_are_rejected(
    tmp_path: Path,
) -> None:
    fixture = FIXTURE_ROOT / "ultralibrarian-kicad-v1"

    no_model = _zip_tree(
        fixture,
        tmp_path / "no-model.zip",
        mutate=lambda relative, value: (
            None if relative.casefold().endswith(".wrl") else value
        ),
    )
    with pytest.raises(CadPackageError, match="CAD_3D_MISSING"):
        ingest_cad_package(
            no_model,
            package_format="auto",
            request=_request(),
            output_base=tmp_path / "no-model",
        )

    malformed = _zip_tree(
        fixture,
        tmp_path / "malformed.zip",
        mutate=lambda relative, value: (
            value.rstrip()[:-1] if relative.endswith(".kicad_sym") else value
        ),
    )
    with pytest.raises(CadPackageError, match="CAD_KICAD_MALFORMED"):
        ingest_cad_package(
            malformed,
            package_format="auto",
            request=_request(),
            output_base=tmp_path / "malformed",
        )

    mismatch = _zip_tree(
        fixture,
        tmp_path / "mismatch.zip",
        mutate=lambda relative, value: (
            value.replace(b'(pad "2"', b'(pad "3"')
            if relative.endswith(".kicad_mod")
            else value
        ),
    )
    with pytest.raises(CadPackageError, match="CAD_PIN_PAD_MISMATCH"):
        ingest_cad_package(
            mismatch,
            package_format="auto",
            request=_request(),
            output_base=tmp_path / "mismatch",
        )


def test_existing_conflicting_symbol_is_never_overwritten(tmp_path: Path) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "package.zip",
    )
    output = tmp_path / "parts"
    source_symbol = (
        FIXTURE_ROOT
        / "ultralibrarian-kicad-v1"
        / "UltraLibrarian"
        / "20260725.kicad_sym"
    ).read_text(encoding="utf-8")
    conflicting = source_symbol.replace('"Synthetic Devices"', '"Conflicting Devices"')
    output.with_suffix(".kicad_sym").write_text(conflicting, encoding="utf-8")

    with pytest.raises(CadPackageError, match="CAD_IDENTITY_MISMATCH"):
        ingest_cad_package(
            archive,
            package_format="auto",
            request=_request(),
            output_base=output,
            overwrite=True,
        )

    assert output.with_suffix(".kicad_sym").read_text(encoding="utf-8") == conflicting
    assert not output.with_suffix(".pretty").exists()
    assert not output.with_suffix(".3dshapes").exists()


def test_existing_conflicting_footprint_identity_is_never_overwritten(
    tmp_path: Path,
) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "package.zip",
    )
    output = tmp_path / "parts"
    ingest_cad_package(
        archive,
        package_format="auto",
        request=_request(),
        output_base=output,
    )
    footprint = output.with_suffix(".pretty") / "SYNTH_FP.kicad_mod"
    conflicting = footprint.read_text(encoding="utf-8").replace(
        '  (layer "F.Cu")',
        '  (property "Manufacturer" "Conflicting Devices")\n'
        '  (property "MPN" "SYNTH-PART-01")\n'
        '  (layer "F.Cu")',
    )
    footprint.write_text(conflicting, encoding="utf-8")
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    with pytest.raises(CadPackageError, match="CAD_IDENTITY_MISMATCH"):
        ingest_cad_package(
            archive,
            package_format="auto",
            request=_request(),
            output_base=output,
            overwrite=True,
        )

    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_unrelated_library_entries_and_files_are_preserved(tmp_path: Path) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "package.zip",
    )
    output = tmp_path / "parts"
    output.with_suffix(".kicad_sym").write_text(
        "(kicad_symbol_lib (version 20220914) (generator test)\n"
        '  (symbol "KEEP_ME" (in_bom yes) (on_board yes))\n'
        ")\n",
        encoding="utf-8",
    )
    footprint_directory = output.with_suffix(".pretty")
    model_directory = output.with_suffix(".3dshapes")
    footprint_directory.mkdir()
    model_directory.mkdir()
    (footprint_directory / "keep.txt").write_text("keep footprint", encoding="utf-8")
    (model_directory / "keep.txt").write_text("keep model", encoding="utf-8")

    ingest_cad_package(
        archive,
        package_format="auto",
        request=_request(),
        output_base=output,
    )

    assert '"KEEP_ME"' in output.with_suffix(".kicad_sym").read_text(encoding="utf-8")
    assert (footprint_directory / "keep.txt").read_text(encoding="utf-8") == (
        "keep footprint"
    )
    assert (model_directory / "keep.txt").read_text(encoding="utf-8") == "keep model"


def test_install_failure_rolls_back_all_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "package.zip",
    )
    output = tmp_path / "parts"
    real_replace = os.replace
    calls = 0

    def fail_second_install(source: str | Path, target: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic transaction failure")
        real_replace(source, target)

    monkeypatch.setattr(cast(Any, package_module).os, "replace", fail_second_install)

    with pytest.raises(CadPackageError, match="CAD_INSTALL_FAILED"):
        ingest_cad_package(
            archive,
            package_format="auto",
            request=_request(),
            output_base=output,
        )

    assert not output.with_suffix(".kicad_sym").exists()
    assert not output.with_suffix(".pretty").exists()
    assert not output.with_suffix(".3dshapes").exists()


def test_concurrent_output_change_is_detected_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "package.zip",
    )
    output = tmp_path / "parts"
    module = cast(Any, package_module)
    real_fingerprint = cast(
        Callable[[Path], Optional[str]],
        module._path_fingerprint,
    )
    calls = 0

    def changed_fingerprint(path: Path) -> str | None:
        nonlocal calls
        calls += 1
        if calls == 4:
            return "changed-while-staging"
        return real_fingerprint(path)

    monkeypatch.setattr(module, "_path_fingerprint", changed_fingerprint)

    with pytest.raises(CadPackageError, match="CAD_OUTPUT_CONCURRENT_MODIFICATION"):
        ingest_cad_package(
            archive,
            package_format="auto",
            request=_request(),
            output_base=output,
        )

    assert not output.with_suffix(".kicad_sym").exists()
    assert not output.with_suffix(".pretty").exists()
    assert not output.with_suffix(".3dshapes").exists()


def test_cli_package_mode_is_local_and_writes_sanitized_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "package.zip",
    )
    output = tmp_path / "parts"
    manifest = tmp_path / "manifest.json"

    def no_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("local package mode attempted network access")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    exit_code = cli.main(
        [
            "--manufacturer",
            MANUFACTURER,
            "--mpn",
            MPN,
            "--cad-source",
            "digikey",
            "--cad-package",
            str(archive),
            "--output",
            str(output),
            "--manifest-json",
            str(manifest),
        ]
    )

    document = json.loads(manifest.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert document["cad_discovery"]["status"] == CAD_PACKAGE_READY
    assert document["cad_discovery"]["provenance"]["distributor"] == "digikey"
    assert (
        document["cad_discovery"]["provenance"]["delivery_partner"] == "ultralibrarian"
    )
    assert document["cad_discovery"]["provenance"]["model_creator"] == (
        "synthetic fixture team"
    )
    assert document["cad"]["symbol_path"] == "parts.kicad_sym"
    assert str(tmp_path) not in manifest.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "missing",
    ["manufacturer", "mpn", "external-source"],
)
def test_cli_package_requires_exact_identity_and_external_source(
    tmp_path: Path,
    missing: str,
) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "package.zip",
    )
    arguments_list = [
        "--manufacturer",
        MANUFACTURER,
        "--mpn",
        MPN,
        "--cad-source",
        "digikey",
        "--cad-package",
        str(archive),
        "--output",
        str(tmp_path / "parts"),
    ]
    if missing == "manufacturer":
        del arguments_list[0:2]
    elif missing == "mpn":
        del arguments_list[2:4]
    else:
        arguments_list[5] = "easyeda"
    arguments = vars(cli.get_parser().parse_args(arguments_list))

    assert not cli.valid_arguments(arguments)


def test_cli_package_format_requires_package(tmp_path: Path) -> None:
    arguments = vars(
        cli.get_parser().parse_args(
            [
                "--mpn",
                MPN,
                "--cad-package-format",
                "ultralibrarian-kicad",
                "--manifest-json",
                str(tmp_path / "manifest.json"),
            ]
        )
    )

    assert not cli.valid_arguments(arguments)


def test_cli_package_evidence_requires_package(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    arguments = vars(
        cli.get_parser().parse_args(
            [
                "--mpn",
                MPN,
                "--cad-package-evidence",
                str(evidence),
                "--manifest-json",
                str(tmp_path / "manifest.json"),
            ]
        )
    )

    assert not cli.valid_arguments(arguments)


def test_cli_manifest_cannot_collide_with_implicit_package_outputs(
    tmp_path: Path,
) -> None:
    archive = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "package.zip",
    )
    output = tmp_path / "parts"
    arguments = vars(
        cli.get_parser().parse_args(
            [
                "--manufacturer",
                MANUFACTURER,
                "--mpn",
                MPN,
                "--cad-source",
                "digikey",
                "--cad-package",
                str(archive),
                "--output",
                str(output),
                "--manifest-json",
                str(output.with_suffix(".pretty")),
            ]
        )
    )

    assert not cli.valid_arguments(arguments)
    assert not output.with_suffix(".pretty").exists()
