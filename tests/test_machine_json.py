from __future__ import annotations

import hashlib
import io
import json
import logging
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest

import easyeda2kicad_digimou.__main__ as cli
from easyeda2kicad_digimou.machine import (
    EXIT_ACTION_REQUIRED,
    EXIT_CAD,
    EXIT_IDENTITY,
    EXIT_INTERNAL,
    EXIT_NOT_FOUND,
    EXIT_PROJECT,
    EXIT_PROVIDER,
    build_machine_result,
    write_machine_json,
)
from easyeda2kicad_digimou.metadata.manifest import (
    write_csv_manifest,
    write_json_manifest,
)
from easyeda2kicad_digimou.metadata.models import (
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    GUEST_LOOKUP_UNSUPPORTED,
    JLCPCB_CACHE_LIVE,
    JLCPCB_PART_FOUND,
    MANUAL_GLOBAL_SOURCING_REQUIRED,
    CadActionRequired,
    CadDiscoveryResult,
    CadProvenance,
    CadRecord,
    CadRequest,
    DistributorRecord,
    JlcpcbResolution,
    MergedPart,
    PartIdentity,
    ProviderDiagnostic,
)
from easyeda2kicad_digimou.project_registration import (
    LibraryEntry,
    LibraryTableUpdate,
    ProjectContext,
    ProjectRegistrationPlan,
)


SCHEMA_PATH = (
    Path(__file__).parents[1]
    / "easyeda2kicad_digimou"
    / "schemas"
    / "machine-result-v1.schema.json"
)
README_PATH = Path(__file__).parents[1] / "README.md"
MACHINE_DOC_PATH = Path(__file__).parents[1] / "docs" / "MACHINE_JSON.md"


def load_schema() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8")),
    )


def assert_schema(document: dict[str, Any]) -> None:
    jsonschema.Draft202012Validator(load_schema()).validate(document)


def found_record(provider: str = "lcsc") -> DistributorRecord:
    part_number = {
        "lcsc": "C30878",
        "digikey": "296-OPA333AIDBVRCT-ND",
        "mouser": "595-OPA333AIDBVR",
    }[provider]
    return DistributorRecord(
        provider=provider,
        distributor_part_number=part_number,
        manufacturer="Texas Instruments",
        mpn="OPA333AIDBVR",
        product_url="https://example.test/part?lang=en",
        datasheet_url="https://example.test/data.pdf",
        retrieved_at="2026-07-29T00:00:00Z",
    )


def merged_result(
    *,
    records: list[DistributorRecord] | None = None,
    provider_errors: dict[str, str] | None = None,
    provider_diagnostics: dict[str, ProviderDiagnostic] | None = None,
    cad: CadRecord | None = None,
    jlcpcb: JlcpcbResolution | None = None,
) -> MergedPart:
    return MergedPart(
        identity=PartIdentity(
            manufacturer="Texas Instruments",
            mpn="OPA333AIDBVR",
        ),
        distributor_records=records or [],
        cad=cad,
        verification_status=(cad.verification_status if cad is not None else "PARTIAL"),
        provider_errors=provider_errors or {},
        provider_diagnostics=provider_diagnostics or {},
        jlcpcb=jlcpcb,
    )


def test_schema_is_valid_and_is_packaged_contract() -> None:
    schema = load_schema()

    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"]["const"] == "1"
    assert schema["additionalProperties"] is False


def test_readme_and_contract_document_machine_boundaries() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    contract = MACHINE_DOC_PATH.read_text(encoding="utf-8")

    assert "### Machine JSON for automation" in readme
    assert "stdout is exactly one schema-v1 UTF-8 JSON document" in readme
    assert "`path_base=project|output|cwd`" in readme
    assert "`--require-provider`" in readme
    assert "`--require-jlcpcb-resolution`" in readme
    assert "`--require-project-registration`" in readme
    assert "does not prompt, open a browser, or launch KiCad" in contract
    assert "The process exit code always equals the JSON `exit_code`" in contract
    assert "unknown top-level and nested fields" in contract
    assert "`--json-events`" in contract
    assert "machine-event-v1.schema.json" in contract


def test_acquire_machine_json_emits_one_document_without_version_banner(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    merged = merged_result(records=[found_record()])

    def run(arguments: dict[str, Any]) -> int:
        arguments["_machine_merged"] = merged
        return 0

    monkeypatch.setattr(cli, "_run_metadata_mode", run)

    exit_code = cli.main(
        [
            "acquire",
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "lcsc",
            "--machine-json",
        ]
    )

    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert exit_code == 0
    assert len(lines) == 1
    assert "-- easyeda2kicad.py" not in captured.out
    document = json.loads(lines[0])
    assert_schema(document)
    assert document["status"] == "SUCCEEDED"
    assert document["exit_code"] == exit_code
    assert document["providers"]["lcsc"]["status"] == "FOUND"


def test_machine_logs_stay_on_stderr_and_required_provider_is_selected(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    merged = merged_result(records=[found_record("digikey")])

    def run(arguments: dict[str, Any]) -> int:
        assert arguments["provider_names"] == ["digikey"]
        assert arguments["machine_required_provider_names"] == ["digikey"]
        logging.warning("machine progress stays on stderr")
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
            "--machine-json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "machine progress" not in captured.out
    assert "machine progress" in captured.err
    assert_schema(json.loads(captured.out))


def test_machine_stderr_redacts_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = "seeded-stderr-machine-secret"
    monkeypatch.setenv("DIGIKEY_CLIENT_ID", canary)
    merged = merged_result(records=[found_record()])

    def run(arguments: dict[str, Any]) -> int:
        logging.error("provider diagnostic contained %s", canary)
        arguments["_machine_merged"] = merged
        return 0

    monkeypatch.setattr(cli, "_run_metadata_mode", run)

    exit_code = cli.main(["acquire", "--mpn", "OPA333AIDBVR", "--machine-json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert canary not in captured.out
    assert canary not in captured.err
    assert "[REDACTED]" in captured.err
    assert_schema(json.loads(captured.out))


def test_invalid_request_still_emits_schema_valid_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(["acquire", "--machine-json"])

    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert exit_code == 2
    assert document["exit_code"] == 2
    assert document["errors"] == [{"code": "INVALID_REQUEST", "provider": None}]
    assert_schema(document)


def test_help_cannot_prepend_prose_to_machine_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(["acquire", "--machine-json", "--help"])

    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert exit_code == 2
    assert document["errors"] == [
        {"code": "HELP_UNAVAILABLE_IN_MACHINE_MODE", "provider": None}
    ]
    assert "usage:" not in captured.out
    assert_schema(document)


def test_unexpected_failure_is_bounded_and_schema_valid(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(arguments: dict[str, Any]) -> int:
        del arguments
        raise RuntimeError("do not expose this private failure")

    monkeypatch.setattr(cli, "_run_metadata_mode", fail)

    exit_code = cli.main(["acquire", "--mpn", "OPA333AIDBVR", "--machine-json"])

    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert exit_code == EXIT_INTERNAL
    assert document["errors"] == [{"code": "INTERNAL_ERROR", "provider": None}]
    assert "private failure" not in captured.out
    assert_schema(document)


def test_machine_writer_bypasses_cp932_and_keeps_utf8_unicode() -> None:
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp932")
    document = {"identity": {"manufacturer": "TI(德州仪器)", "mpn": "OPA333AIDBVR"}}

    write_machine_json(document, stream=stream.buffer)
    payload = buffer.getvalue()
    stream.detach()

    assert json.loads(payload.decode("utf-8")) == document
    assert "德州仪器".encode("utf-8") in payload


def test_machine_writer_redacts_configured_secret_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "seeded-configured-machine-secret"
    monkeypatch.setenv("DIGIKEY_CLIENT_SECRET", canary)
    stream = io.BytesIO()

    write_machine_json(
        {
            "identity": {"manufacturer": canary, "mpn": "OPA333AIDBVR"},
            "errors": [{"code": "SAFE", "provider": None}],
        },
        stream=stream,
    )

    output = stream.getvalue().decode("utf-8")
    assert canary not in output
    assert "[REDACTED]" in output


def test_requested_manifests_redact_configured_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "seeded-manifest-machine-secret"
    monkeypatch.setenv("MOUSER_API_KEY", canary)
    record = found_record("mouser")
    record.description = canary
    merged = merged_result(records=[record])
    json_path = tmp_path / "part.json"
    csv_path = tmp_path / "part.csv"

    write_json_manifest(merged, json_path)
    write_csv_manifest(merged, csv_path)

    assert canary not in json_path.read_text(encoding="utf-8")
    assert canary not in csv_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("code", "expected_exit"),
    [
        (GUEST_LOOKUP_UNSUPPORTED, EXIT_ACTION_REQUIRED),
        ("NOT_FOUND", EXIT_NOT_FOUND),
        ("MPN_MISMATCH", EXIT_IDENTITY),
        ("NETWORK_ERROR", EXIT_PROVIDER),
        ("OFFLINE_CACHE_MISS", EXIT_PROVIDER),
    ],
)
def test_required_provider_codes_map_to_stable_exit_codes(
    code: str,
    expected_exit: int,
) -> None:
    setup_url = (
        "https://developer.digikey.com/products"
        if code == GUEST_LOOKUP_UNSUPPORTED
        else None
    )
    merged = merged_result(
        provider_errors={"digikey": code},
        provider_diagnostics={
            "digikey": ProviderDiagnostic(
                code=code,
                operation="exact-search",
                setup_url=setup_url,
            )
        },
    )

    document, exit_code = build_machine_result(
        {
            "provider_names": ["digikey"],
            "machine_required_provider_names": ["digikey"],
            "cad_source": "easyeda",
        },
        merged,
        core_exit_code=0,
        request_id="a" * 32,
    )

    assert exit_code == expected_exit
    assert document["exit_code"] == expected_exit
    if code == GUEST_LOOKUP_UNSUPPORTED:
        assert document["status"] == "ACTION_REQUIRED"
        assert document["actions_required"][0]["handoff_url"].startswith("https://")
    else:
        assert document["status"] == "FAILED"
    assert_schema(document)


def test_optional_provider_omission_remains_exit_zero_warning() -> None:
    merged = merged_result(
        provider_errors={"mouser": GUEST_LOOKUP_UNSUPPORTED},
        provider_diagnostics={
            "mouser": ProviderDiagnostic(
                code=GUEST_LOOKUP_UNSUPPORTED,
                operation="part-search",
                setup_url="https://www.mouser.com/api-search/",
            )
        },
    )

    document, exit_code = build_machine_result(
        {
            "provider_names": ["mouser"],
            "machine_required_provider_names": [],
            "cad_source": "easyeda",
        },
        merged,
        core_exit_code=0,
        request_id="b" * 32,
    )

    assert exit_code == 0
    assert document["status"] == "SUCCEEDED_WITH_WARNINGS"
    assert document["warnings"] == [
        {"code": GUEST_LOOKUP_UNSUPPORTED, "provider": "mouser"}
    ]
    assert document["actions_required"][0]["provider"] == "mouser"
    assert_schema(document)


def test_fatal_required_failure_precedes_manual_action_but_keeps_both() -> None:
    merged = merged_result(
        provider_errors={
            "digikey": GUEST_LOOKUP_UNSUPPORTED,
            "mouser": "MPN_MISMATCH",
        },
        provider_diagnostics={
            "digikey": ProviderDiagnostic(
                code=GUEST_LOOKUP_UNSUPPORTED,
                setup_url="https://developer.digikey.com/products",
            ),
            "mouser": ProviderDiagnostic(code="MPN_MISMATCH"),
        },
    )

    document, exit_code = build_machine_result(
        {
            "provider_names": ["digikey", "mouser"],
            "machine_required_provider_names": ["digikey", "mouser"],
            "cad_source": "easyeda",
        },
        merged,
        core_exit_code=0,
        request_id="5" * 32,
    )

    assert exit_code == EXIT_IDENTITY
    assert document["errors"] == [{"code": "MPN_MISMATCH", "provider": "mouser"}]
    assert document["actions_required"][0]["code"] == GUEST_LOOKUP_UNSUPPORTED
    assert_schema(document)


def test_require_cad_maps_missing_cad_to_exit_seven() -> None:
    document, exit_code = build_machine_result(
        {
            "provider_names": [],
            "machine_required_provider_names": [],
            "cad_source": "easyeda",
            "require_cad": True,
        },
        merged_result(),
        core_exit_code=0,
        request_id="c" * 32,
    )

    assert exit_code == EXIT_CAD
    assert document["errors"] == [{"code": "CAD_ACQUISITION_FAILED", "provider": None}]
    assert_schema(document)


def test_explicit_cad_manual_handoff_maps_to_action_required() -> None:
    merged = merged_result()
    merged.cad_discovery = CadDiscoveryResult(
        requested_source="digikey",
        status=CAD_MANUAL_DOWNLOAD_REQUIRED,
        request=CadRequest(
            manufacturer="Texas Instruments",
            mpn="OPA333AIDBVR",
            source="digikey",
        ),
        provenance=CadProvenance(
            distributor="digikey",
            delivery_partner="ultralibrarian",
            landing_url="https://www.digikey.com/en/models/123",
            retrieval_mode="official-api-handoff",
        ),
        action_required=CadActionRequired(
            code=CAD_MANUAL_DOWNLOAD_REQUIRED,
            detail="Download the package manually",
            setup_url="https://www.digikey.com/en/models/123",
        ),
    )

    document, exit_code = build_machine_result(
        {
            "provider_names": [],
            "machine_required_provider_names": [],
            "cad_source": "digikey",
        },
        merged,
        core_exit_code=1,
        request_id="4" * 32,
    )

    assert exit_code == EXIT_ACTION_REQUIRED
    assert document["cad"]["delivery_partner"] == "ultralibrarian"
    assert document["actions_required"] == [
        {
            "code": CAD_MANUAL_DOWNLOAD_REQUIRED,
            "provider": "digikey",
            "action": (
                "Download the official KiCad package and rerun with --cad-package"
            ),
            "handoff_url": "https://www.digikey.com/en/models/123",
        }
    ]
    assert_schema(document)


def test_require_jlcpcb_resolution_distinguishes_found_and_manual_action() -> None:
    found = JlcpcbResolution(
        match_status=JLCPCB_PART_FOUND,
        checked_at="2026-07-29T00:00:00Z",
        cache_state=JLCPCB_CACHE_LIVE,
        jlcpcb_part_number="C30878",
        lcsc_part_number="C30878",
    )
    manual = JlcpcbResolution(
        match_status=MANUAL_GLOBAL_SOURCING_REQUIRED,
        checked_at="2026-07-29T00:00:00Z",
        cache_state=JLCPCB_CACHE_LIVE,
        manual_action_required="Use Global Sourcing",
    )
    arguments = {
        "provider_names": [],
        "machine_required_provider_names": [],
        "cad_source": "easyeda",
        "require_jlcpcb_resolution": True,
    }

    found_document, found_exit = build_machine_result(
        arguments,
        merged_result(jlcpcb=found),
        core_exit_code=0,
        request_id="d" * 32,
    )
    manual_document, manual_exit = build_machine_result(
        arguments,
        merged_result(jlcpcb=manual),
        core_exit_code=0,
        request_id="e" * 32,
    )

    assert found_exit == 0
    assert manual_exit == EXIT_ACTION_REQUIRED
    assert manual_document["actions_required"][0]["code"] == (
        MANUAL_GLOBAL_SOURCING_REQUIRED
    )
    assert_schema(found_document)
    assert_schema(manual_document)


def test_artifacts_use_relative_path_base_and_sha256(tmp_path: Path) -> None:
    output = tmp_path / "outside" / "parts"
    output.parent.mkdir()
    symbol = output.with_suffix(".kicad_sym")
    symbol.write_text("(kicad_symbol_lib)", encoding="utf-8")
    merged = merged_result(
        cad=CadRecord(
            source="easyeda",
            symbol_path=symbol,
            verification_status="VERIFIED",
        )
    )

    document, exit_code = build_machine_result(
        {
            "provider_names": [],
            "machine_required_provider_names": [],
            "cad_source": "easyeda",
            "output": str(output),
        },
        merged,
        core_exit_code=0,
        request_id="f" * 32,
    )

    assert exit_code == 0
    assert document["artifacts"] == [
        {
            "kind": "symbol",
            "path": "parts.kicad_sym",
            "path_base": "output",
            "sha256": hashlib.sha256(symbol.read_bytes()).hexdigest(),
        }
    ]
    assert str(tmp_path) not in json.dumps(document)
    assert_schema(document)


def test_project_changes_are_project_relative_and_requirement_can_succeed(
    tmp_path: Path,
) -> None:
    project = tmp_path / "board.kicad_pro"
    project.write_text("{}", encoding="utf-8")
    entry = LibraryEntry("parts", "${KIPRJMOD}/libs/parts.kicad_sym")
    update = LibraryTableUpdate(
        path=tmp_path / "sym-lib-table",
        root_name="sym_lib_table",
        entry=entry,
        action="create",
        expected_sha256=None,
        content=b"(sym_lib_table)\n",
    )
    plan = ProjectRegistrationPlan(
        context=ProjectContext(project_file=project, project_root=tmp_path),
        output_base=tmp_path / "libs" / "parts",
        updates=(update,),
    )

    document, exit_code = build_machine_result(
        {
            "provider_names": [],
            "machine_required_provider_names": [],
            "cad_source": "easyeda",
            "require_project_registration": True,
            "_machine_project_succeeded": True,
            "_machine_project_plan": plan,
        },
        merged_result(),
        core_exit_code=0,
        request_id="1" * 32,
    )

    assert exit_code == 0
    assert document["project_changes"] == [
        {
            "path": "sym-lib-table",
            "path_base": "project",
            "action": "create",
            "nickname": "parts",
            "uri": "${KIPRJMOD}/libs/parts.kicad_sym",
        }
    ]
    assert str(tmp_path) not in json.dumps(document)
    assert_schema(document)


def test_required_project_failure_maps_to_exit_eight() -> None:
    document, exit_code = build_machine_result(
        {
            "provider_names": [],
            "machine_required_provider_names": [],
            "cad_source": "easyeda",
            "require_project_registration": True,
            "_machine_project_error": "PROJECT_CONCURRENT_MODIFICATION",
        },
        merged_result(),
        core_exit_code=1,
        request_id="2" * 32,
    )

    assert exit_code == EXIT_PROJECT
    assert document["errors"] == [
        {"code": "PROJECT_CONCURRENT_MODIFICATION", "provider": None}
    ]
    assert_schema(document)


def test_malformed_cad_package_returns_schema_valid_cad_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive = tmp_path / "malformed.zip"
    archive.write_bytes(b"not a zip archive")

    exit_code = cli.main(
        [
            "acquire",
            "--manufacturer",
            "Texas Instruments",
            "--mpn",
            "OPA333AIDBVR",
            "--cad-source",
            "digikey",
            "--cad-package",
            str(archive),
            "--output",
            str(tmp_path / "parts"),
            "--machine-json",
        ]
    )

    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert exit_code == EXIT_CAD
    assert document["exit_code"] == EXIT_CAD
    assert document["errors"][0]["code"].startswith("CAD_")
    assert str(tmp_path) not in captured.out
    assert_schema(document)


def test_secret_query_and_private_fields_never_enter_machine_result() -> None:
    canary = "seeded-machine-secret-value"
    record = found_record("digikey")
    record.product_url = (
        "https://www.digikey.com/en/products/detail/x?api_key=" + canary + "&lang=en"
    )
    record.description = canary
    merged = merged_result(records=[record])

    document, exit_code = build_machine_result(
        {
            "provider_names": ["digikey"],
            "machine_required_provider_names": [],
            "cad_source": "easyeda",
        },
        merged,
        core_exit_code=0,
        request_id="3" * 32,
    )
    serialized = json.dumps(document)

    assert exit_code == 0
    assert canary not in serialized
    assert "api_key" not in serialized
    assert document["providers"]["digikey"]["record"]["product_url"].endswith(
        "?lang=en"
    )
    assert_schema(document)
