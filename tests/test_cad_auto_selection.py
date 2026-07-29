from __future__ import annotations

# Global imports
import json
import zipfile
from pathlib import Path
from typing import Callable, Optional

import pytest

# Local imports
from easyeda2kicad.cad import (
    CadPackageCandidate,
    CadPackageError,
    ingest_cad_package,
    load_source_lock,
    select_auto_cad_package,
    write_source_lock,
)
from easyeda2kicad.metadata.models import CadRequest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "cad_packages"
MANUFACTURER = "Synthetic Devices"
MPN = "SYNTH-PART-01"


def _zip_tree(
    source: Path,
    destination: Path,
    *,
    mutate: Optional[Callable[[str, bytes], bytes]] = None,
) -> Path:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source).as_posix()
            value = path.read_bytes()
            archive.writestr(relative, mutate(relative, value) if mutate else value)
    return destination


def _candidate(source: str, archive: Path) -> CadPackageCandidate:
    return CadPackageCandidate(source=source, archive_path=archive)


def test_matching_validated_candidates_choose_digikey_priority_without_output(
    tmp_path: Path,
) -> None:
    digikey = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "digikey.zip",
    )
    mouser = _zip_tree(
        FIXTURE_ROOT / "samacsys-kicad-v1",
        tmp_path / "mouser.zip",
    )

    selection = select_auto_cad_package(
        [_candidate("mouser", mouser), _candidate("digikey", digikey)],
        manufacturer=MANUFACTURER,
        mpn=MPN,
    )

    assert selection.selected.candidate.source == "digikey"
    assert selection.source_lock.selected_source == "digikey"
    assert selection.source_lock.package_sha256 == (
        selection.selected.inspection.package.provenance.package_hash
    )
    assert {path.name for path in tmp_path.iterdir()} == {
        "digikey.zip",
        "mouser.zip",
    }


def test_materially_different_validated_candidates_fail_closed(
    tmp_path: Path,
) -> None:
    digikey = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "digikey.zip",
    )

    def rename_package(relative: str, value: bytes) -> bytes:
        if relative.endswith((".kicad_sym", ".kicad_mod")):
            return value.replace(b"SYNTH_FP", b"ALT_FP")
        return value

    mouser = _zip_tree(
        FIXTURE_ROOT / "samacsys-kicad-v1",
        tmp_path / "mouser.zip",
        mutate=rename_package,
    )

    with pytest.raises(CadPackageError, match="CAD_SOURCE_CONFLICT"):
        select_auto_cad_package(
            [_candidate("digikey", digikey), _candidate("mouser", mouser)],
            manufacturer=MANUFACTURER,
            mpn=MPN,
        )


def test_source_lock_is_atomic_portable_and_reselects_exact_content(
    tmp_path: Path,
) -> None:
    digikey = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "digikey.zip",
    )
    mouser = _zip_tree(
        FIXTURE_ROOT / "samacsys-kicad-v1",
        tmp_path / "mouser.zip",
    )
    lock_path = tmp_path / "build" / "cad-source-lock.json"
    first = select_auto_cad_package(
        [_candidate("digikey", digikey), _candidate("mouser", mouser)],
        manufacturer=MANUFACTURER,
        mpn=MPN,
        source_lock_path=lock_path,
    )

    write_source_lock(lock_path, first.source_lock)
    before = lock_path.read_bytes()
    second = select_auto_cad_package(
        [_candidate("mouser", mouser), _candidate("digikey", digikey)],
        manufacturer=MANUFACTURER,
        mpn=MPN,
        source_lock_path=lock_path,
    )
    write_source_lock(lock_path, second.source_lock)

    assert second.existing_lock
    assert second.selected.candidate.source == "digikey"
    assert lock_path.read_bytes() == before
    payload = json.loads(before)
    assert payload == {
        "manufacturer": MANUFACTURER,
        "mpn": MPN,
        "package_sha256": first.source_lock.package_sha256,
        "schema_version": 1,
        "selected_source": "digikey",
    }
    assert str(tmp_path) not in before.decode("utf-8")
    assert not list(lock_path.parent.glob(".*.tmp"))


def test_existing_lock_requires_matching_hash_and_exact_identity(
    tmp_path: Path,
) -> None:
    digikey = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "digikey.zip",
    )
    lock_path = tmp_path / "cad-source-lock.json"
    selection = select_auto_cad_package(
        [_candidate("digikey", digikey)],
        manufacturer=MANUFACTURER,
        mpn=MPN,
    )
    write_source_lock(lock_path, selection.source_lock)

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["package_sha256"] = "0" * 64
    lock_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CadPackageError, match="CAD_SOURCE_LOCK_MISMATCH"):
        select_auto_cad_package(
            [_candidate("digikey", digikey)],
            manufacturer=MANUFACTURER,
            mpn=MPN,
            source_lock_path=lock_path,
        )

    payload["manufacturer"] = "Other Manufacturer"
    lock_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CadPackageError, match="CAD_SOURCE_LOCK_IDENTITY_MISMATCH"):
        select_auto_cad_package(
            [_candidate("digikey", digikey)],
            manufacturer=MANUFACTURER,
            mpn=MPN,
            source_lock_path=lock_path,
        )


def test_source_lock_rejects_unknown_fields_and_conflicting_overwrite(
    tmp_path: Path,
) -> None:
    digikey = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "digikey.zip",
    )
    selection = select_auto_cad_package(
        [_candidate("digikey", digikey)],
        manufacturer=MANUFACTURER,
        mpn=MPN,
    )
    lock_path = tmp_path / "cad-source-lock.json"
    write_source_lock(lock_path, selection.source_lock)

    payload = selection.source_lock.to_dict()
    payload["machine_path"] = str(tmp_path)
    lock_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CadPackageError, match="CAD_SOURCE_LOCK_INVALID"):
        load_source_lock(lock_path)

    lock_path.unlink()
    other = selection.source_lock.__class__(
        schema_version=1,
        manufacturer=MANUFACTURER,
        mpn=MPN,
        selected_source="mouser",
        package_sha256="1" * 64,
    )
    write_source_lock(lock_path, other)
    with pytest.raises(CadPackageError, match="CAD_SOURCE_LOCK_CONFLICT"):
        write_source_lock(lock_path, selection.source_lock)


def test_candidate_change_after_selection_fails_before_output(tmp_path: Path) -> None:
    digikey = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "digikey.zip",
    )
    selection = select_auto_cad_package(
        [_candidate("digikey", digikey)],
        manufacturer=MANUFACTURER,
        mpn=MPN,
    )
    with zipfile.ZipFile(digikey, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("UltraLibrarian/NOTICE-extra.txt", "changed package\n")
    output = tmp_path / "parts"

    with pytest.raises(CadPackageError, match="CAD_SOURCE_LOCK_MISMATCH"):
        ingest_cad_package(
            digikey,
            package_format="ultralibrarian-kicad",
            request=CadRequest(
                manufacturer=MANUFACTURER,
                mpn=MPN,
                source="digikey",
            ),
            output_base=output,
            expected_package_hash=selection.source_lock.package_sha256,
        )

    assert not output.with_suffix(".kicad_sym").exists()
    assert not output.with_suffix(".pretty").exists()
    assert not output.with_suffix(".3dshapes").exists()
