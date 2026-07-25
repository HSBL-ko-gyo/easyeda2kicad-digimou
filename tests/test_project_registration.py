from __future__ import annotations

import json
import os
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

from easyeda2kicad import __main__ as cli
from easyeda2kicad import project_registration as registration_module
from easyeda2kicad.cad.kicad import parse_document
from easyeda2kicad.project_registration import (
    ProjectRegistrationError,
    apply_project_registration,
    plan_project_registration,
    resolve_project,
)

CAD_FIXTURE = (
    Path(__file__).parent / "fixtures" / "cad_packages" / "ultralibrarian-kicad-v1"
)


def _project(root: Path, name: str = "validation") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    project = root / "{0}.kicad_pro".format(name)
    project.write_text("{}\n", encoding="utf-8")
    return project


def _artifacts(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".kicad_sym").write_text(
        "(kicad_symbol_lib (version 20220914) (generator test))\n",
        encoding="utf-8",
    )
    footprint_directory = output.with_suffix(".pretty")
    footprint_directory.mkdir()
    (footprint_directory / "TEST.kicad_mod").write_text(
        '(footprint "TEST" (version 20211014) (generator test) (layer "F.Cu")'
        ' (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")))\n',
        encoding="utf-8",
    )


def _table(root_name: str, body: str = "") -> str:
    return "({0}\n  (version 7)\n{1})\n".format(root_name, body)


def _lib(name: str, uri: str, *, extra: str = "") -> str:
    return (
        '  (lib (name "{0}")(type "KiCad")(uri "{1}")(options "")(descr ""){2})\n'
    ).format(name, uri, extra)


def _zip_fixture(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(CAD_FIXTURE.rglob("*")):
            if source.is_file():
                archive.write(source, source.relative_to(CAD_FIXTURE).as_posix())
    return path


def test_resolve_project_accepts_file_or_unambiguous_directory(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")

    from_file = resolve_project(project)
    from_directory = resolve_project(project.parent)

    assert from_file == from_directory
    assert from_file.project_file == project.resolve()
    assert from_file.project_root == project.parent.resolve()


def test_resolve_project_rejects_zero_multiple_and_wrong_extension(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ProjectRegistrationError, match="PROJECT_NOT_FOUND"):
        resolve_project(empty)

    multiple = tmp_path / "multiple"
    _project(multiple, "one")
    _project(multiple, "two")
    with pytest.raises(ProjectRegistrationError, match="PROJECT_AMBIGUOUS"):
        resolve_project(multiple)

    wrong = tmp_path / "wrong.txt"
    wrong.write_text("not a project", encoding="utf-8")
    with pytest.raises(ProjectRegistrationError, match="PROJECT_FILE_INVALID"):
        resolve_project(wrong)


def test_absent_tables_are_created_with_project_relative_uris(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "libs" / "parts"
    _artifacts(output)

    plan = plan_project_registration(project, output, require_artifacts=True)
    result = apply_project_registration(plan)

    assert set(result.changed_paths) == {
        project.parent / "sym-lib-table",
        project.parent / "fp-lib-table",
    }
    symbol_table = (project.parent / "sym-lib-table").read_text(encoding="utf-8")
    footprint_table = (project.parent / "fp-lib-table").read_text(encoding="utf-8")
    parse_document(symbol_table, "sym_lib_table")
    parse_document(footprint_table, "fp_lib_table")
    assert '(name "parts")' in symbol_table
    assert '(uri "${KIPRJMOD}/libs/parts.kicad_sym")' in symbol_table
    assert '(uri "${KIPRJMOD}/libs/parts.pretty")' in footprint_table


def test_populated_tables_preserve_unknown_fields_order_bom_and_crlf(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "libs" / "parts"
    _artifacts(output)
    symbol_table = project.parent / "sym-lib-table"
    original = (
        "\ufeff(sym_lib_table\r\n"
        "  (version 7)\r\n"
        '  (unknown "keep-me")\r\n'
        + _lib("existing", "${KIPRJMOD}/existing.kicad_sym").replace("\n", "\r\n")
        + ")\r\n"
    )
    symbol_table.write_bytes(original.encode("utf-8"))
    footprint_table = project.parent / "fp-lib-table"
    footprint_table.write_text(
        _table(
            "fp_lib_table",
            _lib("existing", "${KIPRJMOD}/existing.pretty"),
        ),
        encoding="utf-8",
    )

    apply_project_registration(
        plan_project_registration(project, output, require_artifacts=True)
    )
    updated_bytes = symbol_table.read_bytes()
    updated = updated_bytes.decode("utf-8")

    assert updated.startswith("\ufeff")
    assert b"\r\n" in updated_bytes
    assert updated.index('(unknown "keep-me")') < updated.index('(name "existing")')
    assert updated.index('(name "existing")') < updated.index('(name "parts")')
    assert updated.count('(name "parts")') == 1


@pytest.mark.parametrize("version", ["6", "7", "8", "9", "10"])
def test_kicad_6_through_10_table_versions_are_preserved(
    tmp_path: Path,
    version: str,
) -> None:
    project = _project(tmp_path / version)
    output = project.parent / "parts"
    _artifacts(output)
    for filename, root_name in (
        ("sym-lib-table", "sym_lib_table"),
        ("fp-lib-table", "fp_lib_table"),
    ):
        (project.parent / filename).write_text(
            "({0}\n  (version {1})\n)\n".format(root_name, version),
            encoding="utf-8",
        )

    apply_project_registration(
        plan_project_registration(project, output, require_artifacts=True)
    )

    assert "(version {0})".format(version) in (
        project.parent / "sym-lib-table"
    ).read_text(encoding="utf-8")
    assert "(version {0})".format(version) in (
        project.parent / "fp-lib-table"
    ).read_text(encoding="utf-8")


def test_idempotent_rerun_produces_no_diff(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "parts"
    _artifacts(output)
    first = plan_project_registration(project, output, require_artifacts=True)
    apply_project_registration(first)
    before = {
        filename: (project.parent / filename).read_bytes()
        for filename in ("sym-lib-table", "fp-lib-table")
    }

    second = plan_project_registration(project, output, require_artifacts=True)
    result = apply_project_registration(second)
    after = {
        filename: (project.parent / filename).read_bytes()
        for filename in ("sym-lib-table", "fp-lib-table")
    }

    assert all(update.action == "unchanged" for update in second.updates)
    assert result.changed_paths == ()
    assert after == before


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (
            _lib("parts", "${KIPRJMOD}/other.kicad_sym"),
            "PROJECT_LIBRARY_NICKNAME_CONFLICT",
        ),
        (
            _lib("other", "${KIPRJMOD}/libs/parts.kicad_sym"),
            "PROJECT_LIBRARY_URI_CONFLICT",
        ),
    ],
)
def test_nickname_and_uri_conflicts_fail_without_changes(
    tmp_path: Path,
    body: str,
    code: str,
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "libs" / "parts"
    _artifacts(output)
    symbol_table = project.parent / "sym-lib-table"
    original = _table("sym_lib_table", body)
    symbol_table.write_text(original, encoding="utf-8")

    with pytest.raises(ProjectRegistrationError, match=code):
        plan_project_registration(project, output, require_artifacts=True)

    assert symbol_table.read_text(encoding="utf-8") == original
    assert not (project.parent / "fp-lib-table").exists()


def test_windows_and_posix_uri_spellings_are_idempotent_on_windows(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "libs" / "parts"
    _artifacts(output)
    windows_uri = r"${KIPRJMOD}\\libs\\parts.kicad_sym"
    (project.parent / "sym-lib-table").write_text(
        _table("sym_lib_table", _lib("parts", windows_uri)),
        encoding="utf-8",
    )

    plan = plan_project_registration(project, output, require_artifacts=True)

    symbol_update = next(
        update for update in plan.updates if update.root_name == "sym_lib_table"
    )
    if os.name == "nt":
        assert symbol_update.action == "unchanged"
    else:
        assert symbol_update.action == "update"
    footprint_update = next(
        update for update in plan.updates if update.root_name == "fp_lib_table"
    )
    assert footprint_update.entry.uri == "${KIPRJMOD}/libs/parts.pretty"


@pytest.mark.parametrize(
    "malformed",
    [
        "(sym_lib_table",
        '(fp_lib_table (lib (name "missing-uri")))\n',
        '(sym_lib_table (lib (name "missing-uri")))\n',
        b"\xff\xfe".decode("latin-1"),
    ],
)
def test_malformed_tables_fail_without_other_table_changes(
    tmp_path: Path,
    malformed: str,
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "parts"
    _artifacts(output)
    symbol_table = project.parent / "sym-lib-table"
    if malformed.startswith("(fp_lib_table"):
        symbol_table = project.parent / "fp-lib-table"
    symbol_table.write_bytes(malformed.encode("latin-1"))

    with pytest.raises(ProjectRegistrationError):
        plan_project_registration(project, output, require_artifacts=True)

    assert symbol_table.read_bytes() == malformed.encode("latin-1")
    other = (
        project.parent / "fp-lib-table"
        if symbol_table.name == "sym-lib-table"
        else project.parent / "sym-lib-table"
    )
    assert not other.exists()


def test_concurrent_change_is_detected_before_any_commit(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "parts"
    _artifacts(output)
    symbol_table = project.parent / "sym-lib-table"
    footprint_table = project.parent / "fp-lib-table"
    symbol_table.write_text(_table("sym_lib_table"), encoding="utf-8")
    footprint_table.write_text(_table("fp_lib_table"), encoding="utf-8")
    plan = plan_project_registration(project, output, require_artifacts=True)
    footprint_before = footprint_table.read_bytes()
    symbol_table.write_text(
        _table("sym_lib_table", '  (external-change "keep")\n'),
        encoding="utf-8",
    )
    changed = symbol_table.read_bytes()

    with pytest.raises(
        ProjectRegistrationError,
        match="PROJECT_TABLE_CONCURRENT_MODIFICATION",
    ):
        apply_project_registration(plan)

    assert symbol_table.read_bytes() == changed
    assert footprint_table.read_bytes() == footprint_before


def test_second_table_failure_rolls_back_first_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "parts"
    _artifacts(output)
    symbol_table = project.parent / "sym-lib-table"
    footprint_table = project.parent / "fp-lib-table"
    symbol_table.write_text(_table("sym_lib_table"), encoding="utf-8")
    footprint_table.write_text(_table("fp_lib_table"), encoding="utf-8")
    before = {
        symbol_table: symbol_table.read_bytes(),
        footprint_table: footprint_table.read_bytes(),
    }
    plan = plan_project_registration(project, output, require_artifacts=True)
    real_replace = os.replace
    calls = 0

    def fail_second_install(source: str | Path, target: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic second table failure")
        real_replace(source, target)

    monkeypatch.setattr(
        cast(Any, registration_module).os,
        "replace",
        fail_second_install,
    )

    with pytest.raises(
        ProjectRegistrationError,
        match="PROJECT_REGISTRATION_WRITE_FAILED",
    ):
        apply_project_registration(plan)

    assert symbol_table.read_bytes() == before[symbol_table]
    assert footprint_table.read_bytes() == before[footprint_table]


def test_change_between_table_commits_rolls_back_without_overwriting_external_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "parts"
    _artifacts(output)
    symbol_table = project.parent / "sym-lib-table"
    footprint_table = project.parent / "fp-lib-table"
    symbol_table.write_text(_table("sym_lib_table"), encoding="utf-8")
    footprint_table.write_text(_table("fp_lib_table"), encoding="utf-8")
    symbol_before = symbol_table.read_bytes()
    external_footprint = _table(
        "fp_lib_table",
        '  (external-change "keep")\n',
    ).encode("utf-8")
    plan = plan_project_registration(project, output, require_artifacts=True)
    real_replace = os.replace
    first_install_done = False

    def edit_before_second_commit(source: str | Path, target: str | Path) -> None:
        nonlocal first_install_done
        real_replace(source, target)
        if Path(target) == symbol_table and not first_install_done:
            first_install_done = True
            footprint_table.write_bytes(external_footprint)

    monkeypatch.setattr(
        cast(Any, registration_module).os,
        "replace",
        edit_before_second_commit,
    )

    with pytest.raises(
        ProjectRegistrationError,
        match="PROJECT_TABLE_CONCURRENT_MODIFICATION",
    ):
        apply_project_registration(plan)

    assert symbol_table.read_bytes() == symbol_before
    assert footprint_table.read_bytes() == external_footprint


def test_require_artifacts_rejects_missing_or_empty_outputs(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "parts"

    with pytest.raises(
        ProjectRegistrationError,
        match="PROJECT_SYMBOL_LIBRARY_MISSING",
    ):
        plan_project_registration(project, output, require_artifacts=True)

    output.with_suffix(".kicad_sym").write_text("x", encoding="utf-8")
    output.with_suffix(".pretty").mkdir()
    with pytest.raises(
        ProjectRegistrationError,
        match="PROJECT_FOOTPRINT_LIBRARY_EMPTY",
    ):
        plan_project_registration(project, output, require_artifacts=True)


def test_dry_run_makes_no_network_cad_manifest_or_project_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "libs" / "parts"
    manifest = project.parent / "manifest.json"

    def no_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("dry-run attempted network access")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    with caplog.at_level("INFO"):
        exit_code = cli.main(
            [
                "--lcsc_id",
                "C2040",
                "--full",
                "--output",
                str(output),
                "--project",
                str(project),
                "--register-project-libraries",
                "--dry-run",
                "--manifest-json",
                str(manifest),
            ]
        )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "easyeda2kicad.py" in captured.out
    assert str(project) in caplog.text
    assert str(project.parent / "sym-lib-table") in caplog.text
    assert str(project.parent / "fp-lib-table") in caplog.text
    assert "${KIPRJMOD}/libs/parts.kicad_sym" in caplog.text
    assert "${KIPRJMOD}/libs/parts.pretty" in caplog.text
    assert not output.with_suffix(".kicad_sym").exists()
    assert not output.with_suffix(".pretty").exists()
    assert not output.with_suffix(".3dshapes").exists()
    assert not output.parent.exists()
    assert not manifest.exists()
    assert not (project.parent / "sym-lib-table").exists()
    assert not (project.parent / "fp-lib-table").exists()


def test_local_package_cli_registers_nested_output_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "libs" / "parts"
    output.parent.mkdir()
    archive = _zip_fixture(tmp_path / "package.zip")

    def no_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("local package registration attempted network access")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    arguments = [
        "--manufacturer",
        "Synthetic Devices",
        "--mpn",
        "SYNTH-PART-01",
        "--cad-source",
        "digikey",
        "--cad-package",
        str(archive),
        "--output",
        str(output),
        "--project",
        str(project),
        "--register-project-libraries",
    ]
    first_exit = cli.main(arguments)
    before = {
        path.relative_to(project.parent).as_posix(): path.read_bytes()
        for path in project.parent.rglob("*")
        if path.is_file()
    }
    second_exit = cli.main(arguments)
    after = {
        path.relative_to(project.parent).as_posix(): path.read_bytes()
        for path in project.parent.rglob("*")
        if path.is_file()
    }

    assert first_exit == 0
    assert second_exit == 0
    assert before == after
    assert '(property "Footprint" "parts:SYNTH_FP"' in output.with_suffix(
        ".kicad_sym"
    ).read_text(encoding="utf-8")
    footprint = output.with_suffix(".pretty") / "SYNTH_FP.kicad_mod"
    assert "${KIPRJMOD}/libs/parts.3dshapes/SYNTH_FP.wrl" in footprint.read_text(
        encoding="utf-8"
    )
    symbol_table = (project.parent / "sym-lib-table").read_text(encoding="utf-8")
    footprint_table = (project.parent / "fp-lib-table").read_text(encoding="utf-8")
    assert "${KIPRJMOD}/libs/parts.kicad_sym" in symbol_table
    assert "${KIPRJMOD}/libs/parts.pretty" in footprint_table


def test_failed_package_validation_never_changes_project_tables(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "libs" / "parts"
    output.parent.mkdir()
    archive = _zip_fixture(tmp_path / "package.zip")
    symbol_table = project.parent / "sym-lib-table"
    symbol_table.write_text(_table("sym_lib_table"), encoding="utf-8")
    before = symbol_table.read_bytes()

    exit_code = cli.main(
        [
            "--manufacturer",
            "Synthetic Devices",
            "--mpn",
            "WRONG-MPN",
            "--cad-source",
            "digikey",
            "--cad-package",
            str(archive),
            "--output",
            str(output),
            "--project",
            str(project),
            "--register-project-libraries",
        ]
    )

    assert exit_code == 1
    assert symbol_table.read_bytes() == before
    assert not (project.parent / "fp-lib-table").exists()
    assert not output.with_suffix(".kicad_sym").exists()


def test_project_registration_flags_require_explicit_opt_in_and_output(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path / "project")
    parser = cli.get_parser()

    project_only = vars(
        parser.parse_args(
            [
                "--lcsc_id",
                "C2040",
                "--full",
                "--project",
                str(project),
            ]
        )
    )
    assert not cli.valid_arguments(project_only)

    no_output = vars(
        parser.parse_args(
            [
                "--lcsc_id",
                "C2040",
                "--full",
                "--project",
                str(project),
                "--register-project-libraries",
            ]
        )
    )
    assert not cli.valid_arguments(no_output)

    project_relative_only = vars(
        parser.parse_args(
            [
                "--lcsc_id",
                "C2040",
                "--full",
                "--output",
                str(project.parent / "parts"),
                "--project",
                str(project),
                "--project-relative",
            ]
        )
    )
    assert cli.valid_arguments(project_relative_only)
    assert not (project.parent / "sym-lib-table").exists()
    assert not (project.parent / "fp-lib-table").exists()


def test_project_file_is_never_modified(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "parts"
    _artifacts(output)
    before = json.loads(project.read_text(encoding="utf-8"))

    apply_project_registration(
        plan_project_registration(project, output, require_artifacts=True)
    )

    assert json.loads(project.read_text(encoding="utf-8")) == before
