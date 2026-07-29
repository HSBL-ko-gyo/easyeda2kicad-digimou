from __future__ import annotations

import hashlib
import io
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest

import easyeda2kicad_digimou.__main__ as cli
from easyeda2kicad_digimou.machine import MachineEventWriter
from easyeda2kicad_digimou.metadata.models import (
    GUEST_LOOKUP_UNSUPPORTED,
    CadRecord,
    DistributorRecord,
    MergedPart,
    PartIdentity,
    ProviderDiagnostic,
)

ROOT = Path(__file__).parents[1]
SCHEMA_ROOT = ROOT / "easyeda2kicad_digimou" / "schemas"
RESULT_SCHEMA_PATH = SCHEMA_ROOT / "machine-result-v1.schema.json"
EVENT_SCHEMA_PATH = SCHEMA_ROOT / "machine-event-v1.schema.json"
HEADLESS_SCHEMA_PATH = SCHEMA_ROOT / "headless-result-v1.schema.json"
EXTERNAL_VERIFIER = ROOT / "examples" / "verify_machine_artifacts.py"


def _schema(path: Path) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(path.read_text(encoding="utf-8")),
    )


def _assert_result_schema(document: dict[str, Any]) -> None:
    jsonschema.Draft202012Validator(_schema(RESULT_SCHEMA_PATH)).validate(document)


def _assert_event_schema(event: dict[str, Any]) -> None:
    jsonschema.Draft202012Validator(_schema(EVENT_SCHEMA_PATH)).validate(event)


def _assert_headless_schema(document: dict[str, Any]) -> None:
    jsonschema.Draft202012Validator(_schema(HEADLESS_SCHEMA_PATH)).validate(document)


def _events(output: str) -> list[dict[str, Any]]:
    return [cast(dict[str, Any], json.loads(line)) for line in output.splitlines()]


def _record(provider: str = "lcsc") -> DistributorRecord:
    return DistributorRecord(
        provider=provider,
        distributor_part_number="C30878",
        manufacturer="Texas Instruments",
        mpn="OPA333AIDBVR",
        product_url="https://example.test/part",
        retrieved_at="2026-07-29T00:00:00Z",
    )


def _merged(
    *,
    records: list[DistributorRecord] | None = None,
    errors: dict[str, str] | None = None,
    diagnostics: dict[str, ProviderDiagnostic] | None = None,
    cad: CadRecord | None = None,
) -> MergedPart:
    return MergedPart(
        identity=PartIdentity(
            manufacturer="Texas Instruments",
            mpn="OPA333AIDBVR",
        ),
        distributor_records=records or [],
        cad=cad,
        verification_status=cad.verification_status if cad is not None else "PARTIAL",
        provider_errors=errors or {},
        provider_diagnostics=diagnostics or {},
    )


def _project(root: Path) -> Path:
    root.mkdir(parents=True)
    project = root / "board.kicad_pro"
    project.write_text("{}\n", encoding="utf-8")
    return project


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _machine_result(artifact: Path, *, path: str = "part.kicad_sym") -> dict[str, Any]:
    return {
        "schema_version": "1",
        "command": "acquire",
        "artifacts": [
            {
                "kind": "symbol",
                "path": path,
                "path_base": "output",
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }
        ],
    }


def test_phase_b_schemas_are_valid_and_closed() -> None:
    for path in (EVENT_SCHEMA_PATH, HEADLESS_SCHEMA_PATH):
        schema = _schema(path)
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False


def test_phase_b_commands_are_documented_as_available() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs" / "MACHINE_JSON.md").read_text(encoding="utf-8")

    assert "`--json-events`" in readme
    assert "python -m easyeda2kicad_digimou capabilities" in readme
    assert "python -m easyeda2kicad_digimou inspect-project" in readme
    assert "python -m easyeda2kicad_digimou plan-acquire" in readme
    assert "python -m easyeda2kicad_digimou verify-artifacts" in readme
    assert "machine-event-v1.schema.json" in contract
    assert "headless-result-v1.schema.json" in contract
    assert "are planned for Phase B" not in readme
    assert "are Phase B and are not claimed here" not in contract


def test_json_events_are_versioned_ordered_and_end_with_phase_a_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    merged = _merged(records=[_record()])

    def run(arguments: dict[str, Any]) -> int:
        arguments["_machine_merged"] = merged
        return 0

    monkeypatch.setattr(cli, "_run_metadata_mode", run)

    exit_code = cli.main(
        [
            "acquire",
            "--manufacturer",
            "Texas Instruments",
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "lcsc",
            "--json-events",
        ]
    )

    captured = capsys.readouterr()
    events = _events(captured.out)
    assert exit_code == 0
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert {event["request_id"] for event in events} == {events[0]["request_id"]}
    assert [event["type"] for event in events] == [
        "started",
        "provider",
        "cad",
        "validation",
        "project",
        "completed",
    ]
    for event in events:
        _assert_event_schema(event)
    result = events[-1]["payload"]["result"]
    _assert_result_schema(result)
    assert result["exit_code"] == exit_code
    assert "-- easyeda2kicad.py" not in captured.out


def test_json_events_keep_typed_manual_handoff_in_completed_event(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    diagnostic = ProviderDiagnostic(
        code=GUEST_LOOKUP_UNSUPPORTED,
        setup_url="https://developer.digikey.com/products",
    )
    merged = _merged(
        errors={"digikey": GUEST_LOOKUP_UNSUPPORTED},
        diagnostics={"digikey": diagnostic},
    )

    def run(arguments: dict[str, Any]) -> int:
        arguments["_machine_merged"] = merged
        return 0

    monkeypatch.setattr(cli, "_run_metadata_mode", run)

    exit_code = cli.main(
        [
            "acquire",
            "--mpn",
            "OPA333AIDBVR",
            "--require-provider",
            "digikey",
            "--json-events",
        ]
    )

    events = _events(capsys.readouterr().out)
    completed = events[-1]["payload"]["result"]
    assert exit_code == 3
    assert completed["status"] == "ACTION_REQUIRED"
    assert completed["actions_required"][0]["code"] == GUEST_LOOKUP_UNSUPPORTED
    validation = next(event for event in events if event["type"] == "validation")
    assert validation["payload"]["action_codes"] == [GUEST_LOOKUP_UNSUPPORTED]


def test_json_events_emit_typed_completion_when_interrupted(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def interrupt(arguments: dict[str, Any]) -> int:
        del arguments
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_run_metadata_mode", interrupt)

    exit_code = cli.main(["acquire", "--mpn", "OPA333AIDBVR", "--json-events"])

    events = _events(capsys.readouterr().out)
    result = events[-1]["payload"]["result"]
    assert exit_code == 70
    assert events[0]["type"] == "started"
    assert events[-1]["type"] == "completed"
    assert result["errors"] == [{"code": "INTERRUPTED", "provider": None}]
    for event in events:
        _assert_event_schema(event)


def test_machine_output_modes_are_mutually_exclusive_and_still_end_typed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "acquire",
            "--mpn",
            "OPA333AIDBVR",
            "--machine-json",
            "--json-events",
        ]
    )

    captured = capsys.readouterr()
    events = _events(captured.out)
    assert exit_code == 2
    assert events[-1]["type"] == "completed"
    assert events[-1]["payload"]["result"]["exit_code"] == 2


def test_event_writer_bypasses_cp932_and_keeps_unicode() -> None:
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp932")
    writer = MachineEventWriter("a" * 32, stream=stream.buffer)

    writer.emit("started", {"command": "acquire", "label": "TI(德州仪器)"})
    payload = buffer.getvalue()
    stream.detach()

    assert "德州仪器".encode("utf-8") in payload
    assert json.loads(payload.decode("utf-8"))["payload"]["label"] == "TI(德州仪器)"


def test_event_stream_and_stderr_exclude_seeded_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = "seeded-json-event-secret"
    monkeypatch.setenv("MOUSER_API_KEY", canary)
    record = _record("lcsc")
    record.product_url = "https://example.test/part?api_key=" + canary
    merged = _merged(records=[record])

    def run(arguments: dict[str, Any]) -> int:
        logging.warning("provider response contained %s", canary)
        arguments["_machine_merged"] = merged
        return 0

    monkeypatch.setattr(cli, "_run_metadata_mode", run)

    assert (
        cli.main(
            [
                "acquire",
                "--mpn",
                "OPA333AIDBVR",
                "--providers",
                "lcsc",
                "--json-events",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert canary not in captured.out
    assert canary not in captured.err
    assert "[REDACTED]" in captured.err
    for event in _events(captured.out):
        _assert_event_schema(event)


def test_capabilities_returns_only_authentication_booleans(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = "seeded-capability-secret"
    monkeypatch.setenv("DIGIKEY_CLIENT_ID", "configured-client")
    monkeypatch.setenv("DIGIKEY_CLIENT_SECRET", canary)
    monkeypatch.delenv("MOUSER_API_KEY", raising=False)

    exit_code = cli.main(["capabilities", "--machine-json"])

    captured = capsys.readouterr()
    document = cast(dict[str, Any], json.loads(captured.out))
    assert exit_code == 0
    assert canary not in captured.out
    assert "DIGIKEY_CLIENT_SECRET" not in captured.out
    assert (
        document["result"]["providers"]["digikey"]["authentication_configured"] is True
    )
    assert (
        document["result"]["providers"]["mouser"]["authentication_configured"] is False
    )
    _assert_headless_schema(document)


def test_headless_machine_help_cannot_prepend_prose(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(["capabilities", "--machine-json", "--help"])

    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert exit_code == 2
    assert "usage:" not in captured.out
    assert document["errors"] == [
        {"code": "HELP_UNAVAILABLE_IN_MACHINE_MODE", "provider": None}
    ]
    _assert_headless_schema(document)


def test_inspect_project_is_read_only_and_uses_relative_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _project(tmp_path / "project")
    before = _snapshot(project.parent)

    exit_code = cli.main(["inspect-project", str(project), "--machine-json"])

    captured = capsys.readouterr()
    document = cast(dict[str, Any], json.loads(captured.out))
    assert exit_code == 0
    assert _snapshot(project.parent) == before
    assert str(tmp_path) not in captured.out
    assert document["result"]["project_file"] == "board.kicad_pro"
    assert document["result"]["tables"]["symbol"]["exists"] is False
    assert document["result"]["tables"]["footprint"]["exists"] is False
    _assert_headless_schema(document)


def test_inspect_project_reports_existing_entries_without_reordering(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _project(tmp_path / "project")
    (project.parent / "sym-lib-table").write_text(
        "(sym_lib_table\n  (version 7)\n"
        '  (lib (name "first")(type "KiCad")(uri "${KIPRJMOD}/first.kicad_sym")'
        '(options "")(descr ""))\n'
        '  (lib (name "second")(type "KiCad")(uri "${KIPRJMOD}/second.kicad_sym")'
        '(options "")(descr ""))\n)\n',
        encoding="utf-8",
    )

    exit_code = cli.main(["inspect-project", "--project", str(project.parent)])

    document = json.loads(capsys.readouterr().out)
    entries = document["result"]["tables"]["symbol"]["entries"]
    assert exit_code == 0
    assert [entry["nickname"] for entry in entries] == ["first", "second"]
    assert document["result"]["tables"]["symbol"]["sha256"] is not None
    _assert_headless_schema(document)


def test_inspect_project_malformed_table_is_bounded_and_does_not_echo_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _project(tmp_path / "private-project-name")
    (project.parent / "sym-lib-table").write_text(
        "(sym_lib_table",
        encoding="utf-8",
    )

    exit_code = cli.main(["inspect-project", "--project", str(project)])

    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert exit_code == 8
    assert document["errors"] == [{"code": "PROJECT_TABLE_MALFORMED", "provider": None}]
    assert str(tmp_path) not in captured.out
    _assert_headless_schema(document)


def test_plan_acquire_does_not_call_provider_or_write_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _project(tmp_path / "project")
    output = project.parent / "libs" / "parts"
    before = _snapshot(project.parent)

    def forbidden(arguments: dict[str, Any]) -> int:
        del arguments
        raise AssertionError("plan-acquire must not execute acquisition")

    monkeypatch.setattr(cli, "_run_metadata_mode", forbidden)

    exit_code = cli.main(
        [
            "plan-acquire",
            "--manufacturer",
            "Texas Instruments",
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "lcsc,digikey",
            "--cad-source",
            "easyeda",
            "--project",
            str(project),
            "--output",
            str(output),
            "--register-project-libraries",
            "--require-project-registration",
            "--offline",
        ]
    )

    document = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert _snapshot(project.parent) == before
    assert [change["action"] for change in document["result"]["project_changes"]] == [
        "create",
        "create",
    ]
    assert document["result"]["network_access_planned"] is False
    assert document["result"]["requirements"]["project_registration"] is True
    _assert_headless_schema(document)


def test_plan_acquire_reports_missing_auth_without_secret_names(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DIGIKEY_CLIENT_ID", raising=False)
    monkeypatch.delenv("DIGIKEY_CLIENT_SECRET", raising=False)

    exit_code = cli.main(
        [
            "plan-acquire",
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "digikey",
            "--machine-json",
        ]
    )

    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert exit_code == 0
    assert document["result"]["authentication_configured"] == {"digikey": False}
    assert document["warnings"] == [
        {"code": "CREDENTIALS_MISSING", "provider": "digikey"}
    ]
    assert "CLIENT_SECRET" not in captured.out
    _assert_headless_schema(document)


def test_plan_acquire_requires_explicit_registration_opt_in(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(
        [
            "plan-acquire",
            "--mpn",
            "OPA333AIDBVR",
            "--require-project-registration",
        ]
    )

    document = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert document["errors"][0]["code"] == "PROJECT_REGISTRATION_NOT_REQUESTED"
    _assert_headless_schema(document)


def test_verify_artifacts_accepts_exact_hash_and_relative_output_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    artifact = output_root / "part.kicad_sym"
    artifact.write_text("(kicad_symbol_lib)\n", encoding="utf-8")
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(_machine_result(artifact)),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "verify-artifacts",
            str(result_path),
            "--machine-json",
            "--output-root",
            str(output_root),
        ]
    )

    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert exit_code == 0
    assert document["result"]["summary"] == {
        "total": 1,
        "verified": 1,
        "failed": 0,
    }
    assert document["result"]["artifacts"][0]["status"] == "VERIFIED"
    assert str(tmp_path) not in captured.out
    _assert_headless_schema(document)


def test_verify_artifacts_detects_tampering(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    artifact = output_root / "part.kicad_sym"
    artifact.write_text("before", encoding="utf-8")
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(_machine_result(artifact)),
        encoding="utf-8",
    )
    artifact.write_text("after", encoding="utf-8")

    exit_code = cli.main(
        [
            "verify-artifacts",
            "--result",
            str(result_path),
            "--output-root",
            str(output_root),
        ]
    )

    document = json.loads(capsys.readouterr().out)
    assert exit_code == 7
    assert document["result"]["artifacts"][0]["status"] == "HASH_MISMATCH"
    assert document["errors"] == [
        {"code": "ARTIFACT_VERIFICATION_FAILED", "provider": None}
    ]
    _assert_headless_schema(document)


def test_verify_artifacts_rejects_traversal_without_reading_outside_base(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    outside = tmp_path / "outside.kicad_sym"
    outside.write_text("private", encoding="utf-8")
    result = _machine_result(outside, path="../outside.kicad_sym")
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    exit_code = cli.main(
        [
            "verify-artifacts",
            "--result",
            str(result_path),
            "--output-root",
            str(output_root),
        ]
    )

    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert exit_code == 7
    assert document["result"]["artifacts"][0]["status"] == "UNSAFE_PATH"
    assert "private" not in captured.out
    _assert_headless_schema(document)


def test_verify_artifacts_invalid_result_is_typed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result_path = tmp_path / "invalid.json"
    result_path.write_text("[]", encoding="utf-8")

    exit_code = cli.main(["verify-artifacts", "--result", str(result_path)])

    document = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert document["errors"] == [{"code": "MACHINE_RESULT_INVALID", "provider": None}]
    _assert_headless_schema(document)


def test_cached_semantic_rerun_keeps_result_and_artifact_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "parts"
    artifact = output.with_suffix(".kicad_sym")
    artifact.write_text("(kicad_symbol_lib)\n", encoding="utf-8")
    merged = _merged(
        records=[_record()],
        cad=CadRecord(
            source="easyeda",
            symbol_path=artifact,
            verification_status="VERIFIED",
        ),
    )

    def cached(arguments: dict[str, Any]) -> int:
        arguments["_machine_merged"] = merged
        return 0

    monkeypatch.setattr(cli, "_run_metadata_mode", cached)
    argv = [
        "acquire",
        "--mpn",
        "OPA333AIDBVR",
        "--providers",
        "lcsc",
        "--output",
        str(output),
        "--symbol",
        "--json-events",
    ]

    assert cli.main(argv) == 0
    first = _events(capsys.readouterr().out)[-1]["payload"]["result"]
    assert cli.main(argv) == 0
    second = _events(capsys.readouterr().out)[-1]["payload"]["result"]
    first["request_id"] = "stable"
    second["request_id"] = "stable"

    assert first == second
    assert (
        first["artifacts"][0]["sha256"]
        == hashlib.sha256(artifact.read_bytes()).hexdigest()
    )


def test_external_verifier_confirms_generated_artifact_hash(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    artifact = output_root / "part.kicad_sym"
    artifact.write_text("(kicad_symbol_lib)\n", encoding="utf-8")
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(_machine_result(artifact)),
        encoding="utf-8",
    )

    completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [
            sys.executable,
            str(EXTERNAL_VERIFIER),
            str(result_path),
            "--base",
            "output={0}".format(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "status": "VERIFIED",
        "summary": {"total": 1, "verified": 1, "failed": 0},
    }
    assert str(tmp_path) not in completed.stdout
