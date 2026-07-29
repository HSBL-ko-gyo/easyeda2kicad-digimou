from __future__ import annotations

# Global imports
import json
import zipfile
from pathlib import Path
from typing import Callable, Optional, cast

import pytest

# Local imports
import easyeda2kicad.__main__ as cli
from easyeda2kicad.metadata.merge import VERIFIED
from easyeda2kicad.metadata.models import CAD_SOURCE_CONFLICT
from easyeda2kicad.metadata.service import MetadataResolution

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


def _auto_args(
    tmp_path: Path,
    digikey: Path,
    mouser: Path,
    *,
    manifest_name: str = "manifest.json",
) -> list[str]:
    return [
        "--manufacturer",
        MANUFACTURER,
        "--mpn",
        MPN,
        "--providers",
        "lcsc",
        "--cad-source",
        "auto",
        "--cad-candidate",
        "mouser={0}".format(mouser),
        "--cad-candidate",
        "digikey={0}".format(digikey),
        "--offline",
        "--full",
        "--output",
        str(tmp_path / "libs" / "parts"),
        "--manifest-json",
        str(tmp_path / manifest_name),
    ]


def test_parse_cad_candidate_paths_is_explicit_and_unique() -> None:
    assert cli.parse_cad_candidate_paths(
        ["mouser=C:/downloads/m.zip", "digikey=C:/downloads/d.zip"],
        option_name="--cad-candidate",
    ) == {
        "mouser": "C:/downloads/m.zip",
        "digikey": "C:/downloads/d.zip",
    }
    with pytest.raises(ValueError, match="digikey=PATH or mouser=PATH"):
        cli.parse_cad_candidate_paths(
            ["easyeda=part.zip"],
            option_name="--cad-candidate",
        )
    with pytest.raises(ValueError, match="one path per source"):
        cli.parse_cad_candidate_paths(
            ["digikey=one.zip", "digikey=two.zip"],
            option_name="--cad-candidate",
        )


def test_verified_easyeda_wins_before_local_candidate_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = MetadataResolution(cad_data={"verified": True})
    monkeypatch.setattr(
        cli,
        "_resolve_metadata_request",
        lambda _arguments, **_kwargs: (object(), result, VERIFIED, None, None),
    )
    finished: list[object] = []

    def finish(*args: object, **_kwargs: object) -> int:
        finished.extend(args)
        return 23

    monkeypatch.setattr(cli, "_finish_metadata_mode", finish)
    monkeypatch.setattr(
        cli,
        "select_auto_cad_package",
        lambda *_args, **_kwargs: pytest.fail(
            "validated EasyEDA must win before package inspection"
        ),
    )

    assert (
        cli._run_auto_cad_package_mode(
            {
                "manufacturer": MANUFACTURER,
                "mpn": MPN,
                "output": str(tmp_path / "parts"),
                "cad_candidates": {"digikey": "unused.zip"},
                "cad_candidate_evidence_paths": {},
            }
        )
        == 23
    )
    assert result in finished


def test_auto_cli_selects_digikey_locks_hash_and_rebuilds_offline(
    tmp_path: Path,
) -> None:
    (tmp_path / "libs").mkdir()
    digikey = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "digikey.zip",
    )
    mouser = _zip_tree(
        FIXTURE_ROOT / "samacsys-kicad-v1",
        tmp_path / "mouser.zip",
    )

    first_exit = cli.main(_auto_args(tmp_path, digikey, mouser))
    lock_path = tmp_path / "libs" / "parts.cad-source-lock.json"
    first_lock = lock_path.read_bytes()
    first_manifest = json.loads((tmp_path / "manifest.json").read_text("utf-8"))
    first_artifacts = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / "libs").rglob("*")
        if path.is_file()
    }

    second_exit = cli.main(
        _auto_args(
            tmp_path,
            digikey,
            mouser,
            manifest_name="manifest-second.json",
        )
    )
    second_manifest = json.loads((tmp_path / "manifest-second.json").read_text("utf-8"))
    second_artifacts = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / "libs").rglob("*")
        if path.is_file()
    }

    assert first_exit == second_exit == 0
    assert first_lock == lock_path.read_bytes()
    lock = json.loads(first_lock)
    assert lock["selected_source"] == "digikey"
    assert lock["package_sha256"] == first_manifest["cad"]["package_hash"]
    assert first_manifest["cad"]["source"] == "digikey"
    assert first_manifest["cad_discovery"]["requested_source"] == "digikey"
    assert second_manifest["cad"]["source"] == "digikey"
    assert first_manifest["cad"]["artifacts"] == second_manifest["cad"]["artifacts"]
    assert first_artifacts == second_artifacts
    assert str(tmp_path) not in first_lock.decode("utf-8")


def test_auto_cli_conflict_writes_typed_manifest_without_outputs(
    tmp_path: Path,
) -> None:
    (tmp_path / "libs").mkdir()
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

    assert cli.main(_auto_args(tmp_path, digikey, mouser)) == 1

    payload = cast(
        dict[str, object],
        json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")),
    )
    discovery = cast(dict[str, object], payload["cad_discovery"])
    action = cast(dict[str, object], discovery["action_required"])
    assert discovery["requested_source"] == "auto"
    assert discovery["status"] == CAD_SOURCE_CONFLICT
    assert action["code"] == CAD_SOURCE_CONFLICT
    assert payload["cad"] is None
    assert not (tmp_path / "libs" / "parts.kicad_sym").exists()
    assert not (tmp_path / "libs" / "parts.pretty").exists()
    assert not (tmp_path / "libs" / "parts.3dshapes").exists()
    assert not (tmp_path / "libs" / "parts.cad-source-lock.json").exists()


def test_auto_cli_registers_selected_package_in_disposable_project(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    libraries = project / "libs"
    libraries.mkdir(parents=True)
    (project / "board.kicad_pro").write_text("{}\n", encoding="utf-8")
    digikey = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "digikey.zip",
    )
    mouser = _zip_tree(
        FIXTURE_ROOT / "samacsys-kicad-v1",
        tmp_path / "mouser.zip",
    )
    arguments = _auto_args(tmp_path, digikey, mouser)
    output_index = arguments.index("--output") + 1
    manifest_index = arguments.index("--manifest-json") + 1
    arguments[output_index] = str(libraries / "parts")
    arguments[manifest_index] = str(project / "manifest.json")
    arguments.extend(
        [
            "--project",
            str(project),
            "--register-project-libraries",
        ]
    )

    assert cli.main(arguments) == 0
    assert "${KIPRJMOD}/libs/parts.kicad_sym" in (project / "sym-lib-table").read_text(
        encoding="utf-8"
    )
    assert "${KIPRJMOD}/libs/parts.pretty" in (project / "fp-lib-table").read_text(
        encoding="utf-8"
    )
    footprint = libraries / "parts.pretty" / "SYNTH_FP.kicad_mod"
    assert "${KIPRJMOD}/libs/parts.3dshapes/SYNTH_FP.wrl" in footprint.read_text(
        encoding="utf-8"
    )
    assert (libraries / "parts.cad-source-lock.json").is_file()


def test_source_lock_cannot_overwrite_manifest_or_cad_tree(
    tmp_path: Path,
) -> None:
    (tmp_path / "libs").mkdir()
    digikey = _zip_tree(
        FIXTURE_ROOT / "ultralibrarian-kicad-v1",
        tmp_path / "digikey.zip",
    )
    mouser = _zip_tree(
        FIXTURE_ROOT / "samacsys-kicad-v1",
        tmp_path / "mouser.zip",
    )
    arguments = _auto_args(tmp_path, digikey, mouser)
    manifest = str(tmp_path / "manifest.json")
    arguments.extend(["--cad-source-lock", manifest])
    assert cli.main(arguments) == 1
    assert not Path(manifest).exists()
    assert not (tmp_path / "libs" / "parts.kicad_sym").exists()

    arguments = _auto_args(tmp_path, digikey, mouser)
    arguments.extend(
        [
            "--cad-source-lock",
            str(tmp_path / "libs" / "parts.pretty" / "lock.json"),
        ]
    )
    assert cli.main(arguments) == 1
    assert not (tmp_path / "libs" / "parts.pretty").exists()
