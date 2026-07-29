from __future__ import annotations

# Global imports
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace
from typing import Any, cast

import pytest

import easyeda2kicad.__main__ as cli
from easyeda2kicad.__main__ import (
    get_parser,
    is_safe_cad_artifact_basename,
    main,
    normalize_footprint_pad_number,
    parse_providers,
    relative_path_if_within,
    valid_arguments,
    verify_symbol_footprint_pins,
)


def _arguments(*argv: str) -> dict[str, object]:
    return vars(get_parser().parse_args(list(argv)))


def test_legacy_lcsc_command_remains_legacy(tmp_path: Path) -> None:
    arguments = _arguments(
        "--lcsc_id", "C2040", "--symbol", "--output", str(tmp_path / "lib")
    )

    assert valid_arguments(arguments)
    assert arguments["metadata_mode"] is False
    assert arguments["provider_names"] == []
    assert arguments["output"] == str(tmp_path / "lib")


def test_mpn_manifest_only_activates_metadata_without_cad_output(
    tmp_path: Path,
) -> None:
    arguments = _arguments(
        "--mpn", "OPA333AIDBVR", "--manifest-json", str(tmp_path / "part.json")
    )

    assert valid_arguments(arguments)
    assert arguments["metadata_mode"] is True
    assert arguments["provider_names"] == ["lcsc"]
    assert arguments["output"] is None


def test_metadata_mode_rejects_multiple_lcsc_ids() -> None:
    arguments = _arguments("--lcsc_id", "C1", "C2", "--mpn", "PART", "--symbol")
    assert not valid_arguments(arguments)


def test_offline_and_refresh_are_mutually_exclusive() -> None:
    arguments = _arguments(
        "--mpn",
        "PART",
        "--manifest-json",
        "part.json",
        "--offline",
        "--refresh-metadata",
    )
    assert not valid_arguments(arguments)


def test_missing_identity_is_rejected() -> None:
    arguments = _arguments("--manifest-json", "part.json")
    assert not valid_arguments(arguments)


def test_main_preserves_argparse_status_for_missing_identity() -> None:
    assert main([]) == 2


def test_metadata_mode_requires_canonical_lcsc_id() -> None:
    arguments = _arguments("--lcsc_id", "C0", "--manifest-json", "part.json")
    assert not valid_arguments(arguments)


def test_legacy_mode_preserves_original_lcsc_validation(tmp_path: Path) -> None:
    arguments = _arguments(
        "--lcsc_id", "CUSTOM", "--symbol", "--output", str(tmp_path / "lib")
    )
    assert valid_arguments(arguments)


def test_legacy_main_processes_multiple_lcsc_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    processed: list[str] = []

    def fake_process_component(
        component_id: str, arguments: dict[str, Any], _api: Any
    ) -> bool:
        assert arguments["metadata_mode"] is False
        processed.append(component_id)
        return True

    monkeypatch.setattr(cli, "_process_component", fake_process_component)

    exit_code = cli.main(
        [
            "--lcsc_id",
            "C100",
            "C200",
            "C300",
            "--symbol",
            "--output",
            str(tmp_path / "lib"),
        ]
    )

    assert exit_code == 0
    assert processed == ["C100", "C200", "C300"]


def test_legacy_main_continues_after_component_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    processed: list[str] = []

    def fake_process_component(
        component_id: str, arguments: dict[str, Any], _api: Any
    ) -> bool:
        assert arguments["metadata_mode"] is False
        processed.append(component_id)
        return component_id != "CFAIL"

    monkeypatch.setattr(cli, "_process_component", fake_process_component)

    exit_code = cli.main(
        [
            "--lcsc_id",
            "C100",
            "CFAIL",
            "C300",
            "--footprint",
            "--output",
            str(tmp_path / "lib"),
        ]
    )

    assert exit_code == 1
    assert processed == ["C100", "CFAIL", "C300"]


def test_provider_parser_deduplicates_in_user_order() -> None:
    assert parse_providers("mouser,lcsc,mouser,digikey", True) == [
        "mouser",
        "lcsc",
        "digikey",
    ]


def test_provider_parser_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        parse_providers("lcsc,octopart", True)


def test_require_providers_preserves_the_explicit_selection_boundary() -> None:
    arguments = _arguments(
        "--mpn",
        "PART",
        "--providers",
        "mouser",
        "--datasheet-link",
        "digikey",
        "--require-providers",
    )

    assert valid_arguments(arguments)
    assert arguments["provider_names"] == ["mouser", "digikey"]
    assert arguments["required_provider_names"] == ["mouser"]


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (("--datasheet-link", "digikey"), ["lcsc", "digikey"]),
        (
            ("--providers", "mouser,lcsc", "--datasheet-link", "digikey"),
            ["mouser", "lcsc", "digikey"],
        ),
        (
            ("--providers", "mouser,digikey", "--datasheet-link", "digikey"),
            ["mouser", "digikey"],
        ),
        (
            ("--providers", "mouser", "--datasheet-link", "manufacturer"),
            ["mouser"],
        ),
    ],
)
def test_datasheet_link_includes_required_provider_without_reordering(
    argv: tuple[str, ...], expected: list[str]
) -> None:
    arguments = _arguments("--mpn", "PART", "--symbol", *argv)

    assert valid_arguments(arguments)
    assert arguments["provider_names"] == expected


def test_reserved_metadata_custom_field_is_rejected(tmp_path: Path) -> None:
    arguments = _arguments(
        "--mpn",
        "PART",
        "--manifest-json",
        str(tmp_path / "part.json"),
        "--custom-field",
        "Manufacturer:Override",
    )
    assert not valid_arguments(arguments)


def test_reserved_metadata_custom_field_is_case_insensitive(tmp_path: Path) -> None:
    arguments = _arguments(
        "--mpn",
        "PART",
        "--manifest-json",
        str(tmp_path / "part.json"),
        "--custom-field",
        "ｍｐｎ:Override",
    )
    assert not valid_arguments(arguments)


@pytest.mark.parametrize(
    "field_name",
    [
        "sToCk",
        "Ｐｒｉｃｅ",
        "PRICE BREAKS",
        "moq",
        "minimum order quantity",
        "Currency",
        "Retrieved At",
        "Raw Response Cache Key",
        "raw_response_cache_key",
        "raw cache key",
        "Raw/Cache Key",
        "CACHE KEY",
        "Packaging",
    ],
)
def test_volatile_sales_custom_fields_are_reserved_in_metadata_mode(
    field_name: str,
) -> None:
    arguments = _arguments(
        "--mpn",
        "PART",
        "--show-conflicts",
        "--custom-field",
        f"{field_name}:manual value",
    )

    assert not valid_arguments(arguments)


def test_manifest_paths_must_differ(tmp_path: Path) -> None:
    path = str(tmp_path / "manifest")
    arguments = _arguments(
        "--mpn", "PART", "--manifest-json", path, "--manifest-csv", path
    )
    assert not valid_arguments(arguments)


@pytest.mark.parametrize("manifest_option", ["--manifest-json", "--manifest-csv"])
def test_manifest_cannot_replace_selected_symbol_output(
    tmp_path: Path, manifest_option: str
) -> None:
    output = tmp_path / "parts.kicad_sym"
    arguments = _arguments(
        "--mpn",
        "PART",
        "--symbol",
        "--output",
        str(output),
        manifest_option,
        str(output),
    )

    assert not valid_arguments(arguments)


@pytest.mark.parametrize(
    ("action", "directory_suffix"),
    [
        ("--footprint", ".pretty"),
        ("--3d", ".3dshapes"),
        ("--svg", ".svgs"),
    ],
)
@pytest.mark.parametrize("manifest_option", ["--manifest-json", "--manifest-csv"])
def test_manifest_cannot_target_selected_artifact_directory(
    tmp_path: Path,
    action: str,
    directory_suffix: str,
    manifest_option: str,
) -> None:
    output = tmp_path / "parts.kicad_sym"
    selected_directory = tmp_path / f"parts{directory_suffix}"
    arguments = _arguments(
        "--mpn",
        "PART",
        action,
        "--output",
        str(output),
        manifest_option,
        str(selected_directory),
    )

    assert not valid_arguments(arguments)


def test_manifest_can_be_nested_in_selected_artifact_directory(
    tmp_path: Path,
) -> None:
    output = tmp_path / "parts.kicad_sym"
    manifest = tmp_path / "parts.pretty" / "metadata" / "part.json"
    arguments = _arguments(
        "--mpn",
        "PART",
        "--footprint",
        "--output",
        str(output),
        "--manifest-json",
        str(manifest),
    )

    assert valid_arguments(arguments)


@pytest.mark.parametrize(
    "output_suffix",
    [
        "planned/kicad",
        "planned/deep/nested/kicad",
    ],
)
def test_manifest_cannot_be_an_ancestor_of_selected_cad_directory(
    tmp_path: Path, output_suffix: str
) -> None:
    manifest = tmp_path / "planned"
    arguments = _arguments(
        "--mpn",
        "PART",
        "--footprint",
        "--output",
        str(tmp_path / output_suffix),
        "--manifest-json",
        str(manifest),
    )

    assert not valid_arguments(arguments)
    assert not manifest.exists()


def test_manifest_ancestor_collision_normalizes_relative_parent_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(
        "--mpn",
        "PART",
        "--footprint",
        "--output",
        str(Path("planned") / "nested" / ".." / "kicad"),
        "--manifest-json",
        "planned",
    )

    assert not valid_arguments(arguments)
    assert not (tmp_path / "planned").exists()


def test_manifest_adjacent_prefix_is_not_a_collision(tmp_path: Path) -> None:
    arguments = _arguments(
        "--mpn",
        "PART",
        "--footprint",
        "--output",
        str(tmp_path / "parts.kicad_sym"),
        "--manifest-json",
        str(tmp_path / "parts.pretty-adjacent" / "manifest.json"),
    )

    assert valid_arguments(arguments)


def test_manifest_ancestor_comparison_uses_windows_path_semantics() -> None:
    assert cli._same_or_descendant(
        PureWindowsPath(r"C:\OUTPUT\kicad.pretty"),
        PureWindowsPath(r"c:\output"),
    )
    assert not cli._same_or_descendant(
        PureWindowsPath(r"C:\output-prefix\kicad.pretty"),
        PureWindowsPath(r"c:\output"),
    )


def test_manifest_ancestor_collision_stops_before_any_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    planned_root = tmp_path / "planned"
    output = planned_root / "kicad"

    def unexpected_resolution(**_kwargs: Any) -> None:
        raise AssertionError(
            "metadata resolution must not start after preflight failure"
        )

    monkeypatch.setattr(cli, "resolve_metadata", unexpected_resolution)

    exit_code = main(
        [
            "--mpn",
            "PART",
            "--footprint",
            "--output",
            str(output),
            "--manifest-json",
            str(planned_root),
        ]
    )

    assert exit_code == 1
    assert not planned_root.exists()
    assert not Path(f"{output}.pretty").exists()


@pytest.mark.parametrize("manifest_option", ["--manifest-json", "--manifest-csv"])
def test_manifest_cannot_be_nested_below_selected_symbol_file_before_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_option: str,
) -> None:
    planned_root = tmp_path / "planned"
    output = planned_root / "library"
    symbol_path = Path(f"{output}.kicad_sym")
    manifest = symbol_path / (
        "manifest.json" if manifest_option == "--manifest-json" else "manifest.csv"
    )

    def unexpected_resolution(**_kwargs: Any) -> None:
        raise AssertionError(
            "metadata resolution must not start after preflight failure"
        )

    monkeypatch.setattr(cli, "resolve_metadata", unexpected_resolution)

    exit_code = main(
        [
            "--mpn",
            "PART",
            "--symbol",
            "--output",
            str(output),
            manifest_option,
            str(manifest),
        ]
    )

    assert exit_code == 1
    assert not planned_root.exists()
    assert not symbol_path.exists()
    assert not manifest.exists()


@pytest.mark.parametrize(
    ("json_suffix", "csv_suffix"),
    [
        ("manifest", "manifest/rows.csv"),
        ("manifest/data.json", "manifest"),
    ],
)
def test_manifest_paths_cannot_contain_one_another(
    tmp_path: Path, json_suffix: str, csv_suffix: str
) -> None:
    arguments = _arguments(
        "--mpn",
        "PART",
        "--manifest-json",
        str(tmp_path / json_suffix),
        "--manifest-csv",
        str(tmp_path / csv_suffix),
    )

    assert not valid_arguments(arguments)


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        r"..\escape",
        "C:drive",
        "CON",
        "com1.step",
        "trailing.",
        "trailing ",
        "control\x1f",
        ".",
        "..",
    ],
)
def test_unsafe_cad_artifact_basenames_are_rejected(name: str) -> None:
    assert not is_safe_cad_artifact_basename(name)


@pytest.mark.parametrize(
    "name",
    ["SOT-23-5", "OPA333AIDBVR", "Package (Metric)", "部品パッケージ"],
)
def test_safe_cad_artifact_basenames_are_preserved(name: str) -> None:
    assert is_safe_cad_artifact_basename(name)


def test_unsafe_footprint_name_is_rejected_before_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments = cast(
        dict[str, Any],
        _arguments(
            "--lcsc_id", "C2040", "--footprint", "--output", str(tmp_path / "lib")
        ),
    )
    assert valid_arguments(arguments)

    class UnsafeFootprintImporter:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def get_footprint(self) -> Any:
            return SimpleNamespace(info=SimpleNamespace(name="../escape"))

    def unexpected_exporter(**_kwargs: Any) -> Any:
        raise AssertionError("unsafe footprint reached the exporter")

    monkeypatch.setattr(cli, "EasyedaFootprintImporter", UnsafeFootprintImporter)
    monkeypatch.setattr(cli, "ExporterFootprintKicad", unexpected_exporter)

    assert not cli._process_component(
        "C2040", arguments, cast(Any, object()), cad_data_override={"fixture": True}
    )


def test_unsafe_3d_model_name_is_rejected_before_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arguments = cast(
        dict[str, Any],
        _arguments("--lcsc_id", "C2040", "--3d", "--output", str(tmp_path / "lib")),
    )
    assert valid_arguments(arguments)

    class UnsafeModelImporter:
        def __init__(self, **_kwargs: Any) -> None:
            self.output = SimpleNamespace(name=r"..\escape")

    def unexpected_exporter(**_kwargs: Any) -> Any:
        raise AssertionError("unsafe 3D model reached the exporter")

    monkeypatch.setattr(cli, "Easyeda3dModelImporter", UnsafeModelImporter)
    monkeypatch.setattr(cli, "Exporter3dModelKicad", unexpected_exporter)

    assert not cli._process_component(
        "C2040", arguments, cast(Any, object()), cad_data_override={"fixture": True}
    )


def test_project_relative_accepts_relative_and_absolute_in_tree_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    library_dir = project / "libs"
    library_dir.mkdir(parents=True)
    monkeypatch.chdir(project)

    relative_arguments = _arguments(
        "--lcsc_id",
        "C2040",
        "--footprint",
        "--output",
        "libs/parts",
        "--project-relative",
    )
    absolute_arguments = _arguments(
        "--lcsc_id",
        "C2040",
        "--footprint",
        "--output",
        str(library_dir / "parts"),
        "--project-relative",
    )

    assert valid_arguments(relative_arguments)
    assert valid_arguments(absolute_arguments)
    assert relative_arguments["project_relative_3d_path"] == ("libs/parts.3dshapes")
    assert absolute_arguments["project_relative_3d_path"] == ("libs/parts.3dshapes")


def test_project_relative_rejects_out_of_tree_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    monkeypatch.chdir(project)
    arguments = _arguments(
        "--lcsc_id",
        "C2040",
        "--footprint",
        "--output",
        str(outside / "parts"),
        "--project-relative",
    )

    assert not valid_arguments(arguments)


def test_relative_path_helper_rejects_windows_out_of_tree_and_other_drive() -> None:
    root = PureWindowsPath("C:/project")

    assert relative_path_if_within(
        root, PureWindowsPath("C:/project/libs/parts.3dshapes")
    ) == PureWindowsPath("libs/parts.3dshapes")
    assert (
        relative_path_if_within(root, PureWindowsPath("C:/other/parts.3dshapes"))
        is None
    )
    assert (
        relative_path_if_within(root, PureWindowsPath("D:/project/parts.3dshapes"))
        is None
    )


def test_relative_path_helper_handles_posix_in_tree_and_out_of_tree() -> None:
    root = PurePosixPath("/srv/project")

    assert relative_path_if_within(
        root, PurePosixPath("/srv/project/libs/parts.3dshapes")
    ) == PurePosixPath("libs/parts.3dshapes")
    assert (
        relative_path_if_within(root, PurePosixPath("/srv/other/parts.3dshapes"))
        is None
    )


def test_show_conflicts_is_a_meaningful_metadata_action() -> None:
    arguments = _arguments("--mpn", "PART", "--show-conflicts")
    assert valid_arguments(arguments)


def test_console_json_writer_falls_back_to_ascii_for_cp932() -> None:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp932", newline="\n")

    cli._write_console_json(
        {
            "manufacturer": "TI(德州仪器)",
            "client_secret": "console-secret-canary",
        },
        stream=stream,
    )
    stream.flush()

    output = raw.getvalue().decode("cp932")
    assert json.loads(output) == {"manufacturer": "TI(德州仪器)"}
    assert "\\u5fb7\\u5dde\\u4eea\\u5668" in output
    assert "console-secret-canary" not in output


def test_console_json_writer_preserves_unicode_for_utf8() -> None:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="utf-8", newline="\n")

    cli._write_console_json({"manufacturer": "TI(德州仪器)"}, stream=stream)
    stream.flush()

    output = raw.getvalue().decode("utf-8")
    assert json.loads(output) == {"manufacturer": "TI(德州仪器)"}
    assert "TI(德州仪器)" in output


def test_same_custom_field_remains_valid_in_legacy_mode(tmp_path: Path) -> None:
    arguments = _arguments(
        "--lcsc_id",
        "C2040",
        "--symbol",
        "--output",
        str(tmp_path / "lib"),
        "--custom-field",
        "Manufacturer:Override",
    )
    assert valid_arguments(arguments)


def test_volatile_custom_field_remains_valid_in_legacy_mode(tmp_path: Path) -> None:
    arguments = _arguments(
        "--lcsc_id",
        "C2040",
        "--symbol",
        "--output",
        str(tmp_path / "lib"),
        "--custom-field",
        "Ｐａｃｋａｇｉｎｇ:Tray",
    )

    assert valid_arguments(arguments)


@pytest.mark.parametrize(
    ("alias", "destination"),
    [
        ("--d", "debug"),
        ("--p", "project_relative"),
        ("--pr", "project_relative"),
        ("--pro", "project_relative"),
    ],
)
def test_legacy_argparse_abbreviations_remain_unambiguous(
    alias: str, destination: str
) -> None:
    arguments = _arguments("--lcsc_id", "C2040", alias)

    assert arguments[destination] is True


def test_help_lists_new_and_existing_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--help"]) == 0
    output = capsys.readouterr().out
    assert "--lcsc_id" in output
    assert "--full" in output
    assert "--mpn" in output
    assert "--providers" in output
    assert "--manifest-json" in output
    assert "--offline" in output


def test_pad_number_normalization_matches_exporter() -> None:
    assert normalize_footprint_pad_number("A(1)") == "1"
    assert normalize_footprint_pad_number(" 2 ") == "2"


def test_pin_pad_verification_includes_sub_symbols_and_ignores_unplated() -> None:
    def pin(number: str) -> SimpleNamespace:
        return SimpleNamespace(settings=SimpleNamespace(spice_pin_number=number))

    symbol = SimpleNamespace(
        pins=[pin("1")],
        sub_symbols=[SimpleNamespace(pins=[pin("2")])],
    )
    footprint = SimpleNamespace(
        pads=[
            SimpleNamespace(number="A(1)", is_plated=True),
            SimpleNamespace(number="2", is_plated=True),
            SimpleNamespace(number="MH", is_plated=False),
        ]
    )

    compatible, pins, pads = verify_symbol_footprint_pins(
        cast(Any, symbol), cast(Any, footprint)
    )
    assert compatible
    assert pins == {"1", "2"}
    assert pads == {"1", "2"}


def test_pin_pad_verification_includes_unplated_smd_pads() -> None:
    def pin(number: str) -> SimpleNamespace:
        return SimpleNamespace(settings=SimpleNamespace(spice_pin_number=number))

    symbol = SimpleNamespace(pins=[pin("1"), pin("2")], sub_symbols=[])
    footprint = SimpleNamespace(
        pads=[
            SimpleNamespace(number="1", is_plated=False, hole_radius=0.0),
            SimpleNamespace(number="2", is_plated=False, hole_radius=0.0),
            SimpleNamespace(number="MH", is_plated=False, hole_radius=0.5),
        ]
    )

    compatible, pins, pads = verify_symbol_footprint_pins(
        cast(Any, symbol), cast(Any, footprint)
    )
    assert compatible
    assert pins == {"1", "2"}
    assert pads == {"1", "2"}


def test_pin_pad_verification_detects_mismatch() -> None:
    symbol = SimpleNamespace(
        pins=[SimpleNamespace(settings=SimpleNamespace(spice_pin_number="1"))],
        sub_symbols=[],
    )
    footprint = SimpleNamespace(pads=[SimpleNamespace(number="2", is_plated=True)])

    compatible, pins, pads = verify_symbol_footprint_pins(
        cast(Any, symbol), cast(Any, footprint)
    )
    assert not compatible
    assert pins == {"1"}
    assert pads == {"2"}
