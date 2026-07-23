from __future__ import annotations

# Global imports
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from easyeda2kicad import __main__ as cli
from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.metadata.cache import MetadataCache
from easyeda2kicad.metadata.merge import CAD_NOT_FOUND, PARTIAL, VERIFIED
from easyeda2kicad.metadata.models import (
    CadRecord,
    DistributorRecord,
    PriceBreak,
)
from easyeda2kicad.metadata.service import (
    MetadataResolution,
)
from easyeda2kicad.metadata.service import resolve_metadata as resolve_metadata_service
from easyeda2kicad.providers import CadProvider, MetadataProvider


def distributor(provider: str) -> DistributorRecord:
    part_number = {
        "lcsc": "C30878",
        "digikey": "296-OPA333AIDBVRCT-ND",
        "mouser": "595-OPA333AIDBVR",
    }[provider]
    return DistributorRecord(
        provider=provider,
        distributor_part_number=part_number,
        product_url="https://example.invalid/{0}/product".format(provider),
        manufacturer="Texas Instruments",
        mpn="OPA333AIDBVR",
        datasheet_url="https://example.invalid/{0}/datasheet.pdf".format(provider),
        stock=123,
        currency="USD",
        price_breaks=[PriceBreak(1, 1.25, "USD")],
        retrieved_at="2026-07-22T00:00:00Z",
    )


def found_resolution() -> MetadataResolution:
    return MetadataResolution(
        distributor_records=[
            distributor("lcsc"),
            distributor("digikey"),
            distributor("mouser"),
        ],
        cad=CadRecord(
            source="easyeda",
            lcsc_part_number="C30878",
            easyeda_component_id="uuid-1",
            symbol_name="OPA333AIDBVR",
            footprint_name="SOT-23-5",
            verification_status=PARTIAL,
        ),
        cad_data={"public": "fixture"},
        trusted_mpn="OPA333AIDBVR",
        trusted_manufacturer="Texas Instruments",
    )


class _ExactMetadataProvider:
    def __init__(
        self,
        name: str,
        response: DistributorRecord,
        calls: list[str],
    ) -> None:
        self.name = name
        self.response = response
        self.calls = calls
        self.last_raw_response: dict[str, str] = {"fixture": name}

    def get_cache_context(self) -> dict[str, str]:
        return {}

    def search_exact_mpn(self, manufacturer: str | None, mpn: str) -> DistributorRecord:
        assert manufacturer == "Texas Instruments"
        assert mpn == "OPA333AIDBVR"
        self.calls.append(self.name)
        return self.response

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord:
        raise AssertionError("unexpected distributor-ID lookup: {0}".format(part_id))


class _ExactCadProvider:
    name = "easyeda"

    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def get_cad_data(self, lcsc_id: str) -> tuple[CadRecord, dict[str, Any]]:
        assert lcsc_id == "C30878"
        self.calls.append(self.name)
        identity = {
            "Manufacturer": "Texas Instruments",
            "Manufacturer Part": "OPA333AIDBVR",
            "Supplier Part": "C30878",
        }
        payload = {
            "uuid": "mock-easyeda-uuid",
            "lcsc": {"number": "C30878"},
            "dataStr": {"head": {"c_para": identity}},
            "packageDetail": {"dataStr": {"head": {"c_para": dict(identity)}}},
        }
        return (
            CadRecord(
                source="easyeda",
                lcsc_part_number="C30878",
                verification_status=PARTIAL,
            ),
            payload,
        )


def install_found_fakes(
    monkeypatch: pytest.MonkeyPatch,
    result: MetadataResolution,
    captured: dict[str, Any],
) -> None:
    def resolve(**kwargs: Any) -> MetadataResolution:
        captured["provider_names"] = kwargs["provider_names"]
        return result

    monkeypatch.setattr(cli, "resolve_metadata", resolve)
    symbol = SimpleNamespace(
        info=SimpleNamespace(name="OPA333AIDBVR", datasheet="source-default")
    )
    footprint = SimpleNamespace(info=SimpleNamespace(name="SOT-23-5"))
    monkeypatch.setattr(
        cli,
        "_verify_metadata_cad",
        lambda resolution, **_kwargs: (VERIFIED, symbol, footprint),
    )

    def process(
        component_id: str,
        arguments: dict[str, Any],
        api: Any,
        **kwargs: Any,
    ) -> bool:
        del api
        captured.update(kwargs)
        captured["component_id"] = component_id
        if arguments["symbol"]:
            Path("{0}.kicad_sym".format(arguments["output"])).write_text(
                "mock symbol", encoding="utf-8"
            )
        return True

    monkeypatch.setattr(cli, "_process_component", process)


@pytest.mark.parametrize(
    ("require_symbol", "require_footprint", "expected_calls"),
    [
        (False, False, []),
        (True, False, ["symbol"]),
        (False, True, ["footprint"]),
        (True, True, ["symbol", "footprint", "compare"]),
    ],
)
def test_metadata_cad_parser_action_matrix(
    monkeypatch: pytest.MonkeyPatch,
    require_symbol: bool,
    require_footprint: bool,
    expected_calls: list[str],
) -> None:
    calls: list[str] = []
    symbol = SimpleNamespace(info=SimpleNamespace(name="PART"))
    footprint = SimpleNamespace(info=SimpleNamespace(name="SOT-23"))

    class SymbolImporter:
        def __init__(self, **_kwargs: Any) -> None:
            calls.append("symbol")

        def get_symbol(self) -> Any:
            return symbol

    class FootprintImporter:
        def __init__(self, **_kwargs: Any) -> None:
            calls.append("footprint")

        def get_footprint(self) -> Any:
            return footprint

    def compare(_symbol: Any, _footprint: Any) -> tuple[bool, set[str], set[str]]:
        calls.append("compare")
        return True, {"1"}, {"1"}

    monkeypatch.setattr(cli, "EasyedaSymbolImporter", SymbolImporter)
    monkeypatch.setattr(cli, "EasyedaFootprintImporter", FootprintImporter)
    monkeypatch.setattr(cli, "verify_symbol_footprint_pins", compare)

    status, parsed_symbol, parsed_footprint = cli._verify_metadata_cad(
        found_resolution(),
        require_symbol=require_symbol,
        require_footprint=require_footprint,
    )

    assert status == VERIFIED
    assert calls == expected_calls
    assert (parsed_symbol is not None) is require_symbol
    assert (parsed_footprint is not None) is require_footprint


@pytest.mark.parametrize(
    ("require_symbol", "require_footprint", "unrequested_importer"),
    [
        (True, False, "EasyedaFootprintImporter"),
        (False, True, "EasyedaSymbolImporter"),
        (False, False, "EasyedaSymbolImporter"),
    ],
)
def test_unrequested_cad_parser_cannot_fail_requested_action(
    monkeypatch: pytest.MonkeyPatch,
    require_symbol: bool,
    require_footprint: bool,
    unrequested_importer: str,
) -> None:
    class WorkingImporter:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def get_symbol(self) -> Any:
            return SimpleNamespace(info=SimpleNamespace(name="PART"))

        def get_footprint(self) -> Any:
            return SimpleNamespace(info=SimpleNamespace(name="SOT-23"))

    class FailingImporter:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("unrequested parser was called")

    monkeypatch.setattr(cli, "EasyedaSymbolImporter", WorkingImporter)
    monkeypatch.setattr(cli, "EasyedaFootprintImporter", WorkingImporter)
    monkeypatch.setattr(cli, unrequested_importer, FailingImporter)

    status, _, _ = cli._verify_metadata_cad(
        found_resolution(),
        require_symbol=require_symbol,
        require_footprint=require_footprint,
    )

    assert status == VERIFIED


def test_combined_symbol_and_footprint_request_blocks_on_parser_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = found_resolution()

    class WorkingSymbolImporter:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def get_symbol(self) -> Any:
            return SimpleNamespace(info=SimpleNamespace(name="PART"))

    class FailingFootprintImporter:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def get_footprint(self) -> Any:
            raise ValueError("invalid fixture")

    monkeypatch.setattr(cli, "EasyedaSymbolImporter", WorkingSymbolImporter)
    monkeypatch.setattr(cli, "EasyedaFootprintImporter", FailingFootprintImporter)

    status, parsed_symbol, parsed_footprint = cli._verify_metadata_cad(
        result,
        require_symbol=True,
        require_footprint=True,
    )

    assert status == PARTIAL
    assert parsed_symbol is not None
    assert parsed_footprint is None
    assert result.blocking_error == "INVALID_RESPONSE"
    assert result.provider_errors["easyeda"] == "INVALID_RESPONSE"


def test_metadata_cli_generates_manifests_and_stable_symbol_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    result = found_resolution()
    install_found_fakes(monkeypatch, result, captured)
    json_path = tmp_path / "part.json"
    csv_path = tmp_path / "part.csv"
    output = tmp_path / "project_parts"

    exit_code = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "lcsc,digikey,mouser",
            "--symbol",
            "--output",
            str(output),
            "--manifest-json",
            str(json_path),
            "--manifest-csv",
            str(csv_path),
        ]
    )

    assert exit_code == 0
    assert json_path.is_file()
    assert csv_path.is_file()
    assert output.with_suffix(".kicad_sym").is_file()
    assert captured["component_id"] == "C30878"
    assert captured["datasheet_url"] is None
    assert captured["symbol_identity"] == {
        "manufacturer": "Texas Instruments",
        "mpn": "OPA333AIDBVR",
        "lcsc_id": "C30878",
    }
    assert captured["symbol_metadata"] == {}
    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert {
        record["provider"]: record["distributor_part_number"]
        for record in document["distributor_records"]
    }["digikey"] == "296-OPA333AIDBVRCT-ND"


def test_no_network_service_to_cli_combines_all_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider_calls: list[str] = []
    cad_calls: list[str] = []
    providers = {
        name: _ExactMetadataProvider(name, distributor(name), provider_calls)
        for name in ("lcsc", "digikey", "mouser")
    }
    cad_provider = _ExactCadProvider(cad_calls)
    metadata_cache = MetadataCache(tmp_path / "metadata-cache")

    def provider_factory(name: str, api: EasyedaApi) -> MetadataProvider:
        del api
        return cast(MetadataProvider, providers[name])

    def cad_provider_factory(api: EasyedaApi) -> CadProvider:
        del api
        return cast(CadProvider, cad_provider)

    def injected_resolver(**kwargs: Any) -> MetadataResolution:
        return resolve_metadata_service(
            **kwargs,
            cache=metadata_cache,
            provider_factory=provider_factory,
            cad_provider_factory=cad_provider_factory,
        )

    def unexpected_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("integration test attempted network access")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_network)
    monkeypatch.setattr(cli, "resolve_metadata", injected_resolver)
    symbol = SimpleNamespace(
        info=SimpleNamespace(name="OPA333AIDBVR", datasheet="source-default")
    )
    footprint = SimpleNamespace(info=SimpleNamespace(name="SOT-23-5"))
    monkeypatch.setattr(
        cli,
        "_verify_metadata_cad",
        lambda resolution, **_kwargs: (VERIFIED, symbol, footprint),
    )
    exported: dict[str, Any] = {}

    def export_component(
        component_id: str,
        arguments: dict[str, Any],
        api: Any,
        **kwargs: Any,
    ) -> bool:
        del api
        exported.update(kwargs)
        exported["component_id"] = component_id
        Path("{0}.kicad_sym".format(arguments["output"])).write_text(
            "mock symbol export", encoding="utf-8"
        )
        return True

    monkeypatch.setattr(cli, "_process_component", export_component)
    output = tmp_path / "integrated"
    manifest = tmp_path / "integrated.json"

    exit_code = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--manufacturer",
            "Texas Instruments",
            "--providers",
            "lcsc,digikey,mouser",
            "--symbol",
            "--output",
            str(output),
            "--manifest-json",
            str(manifest),
        ]
    )

    document = json.loads(manifest.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert provider_calls == ["lcsc", "digikey", "mouser"]
    assert cad_calls == ["easyeda"]
    assert [item["provider"] for item in document["distributor_records"]] == [
        "lcsc",
        "digikey",
        "mouser",
    ]
    assert document["identity"]["manufacturer"] == "Texas Instruments"
    assert document["identity"]["mpn"] == "OPA333AIDBVR"
    assert document["verification_status"] == VERIFIED
    assert document["provider_errors"] == {}
    assert output.with_suffix(".kicad_sym").read_text(encoding="utf-8") == (
        "mock symbol export"
    )
    assert exported["component_id"] == "C30878"
    assert exported["symbol_identity"]["lcsc_id"] == "C30878"
    assert exported["symbol_metadata"] == {}
    assert {
        item["provider"]: item["distributor_part_number"]
        for item in document["distributor_records"]
    } == {
        "lcsc": "C30878",
        "digikey": "296-OPA333AIDBVRCT-ND",
        "mouser": "595-OPA333AIDBVR",
    }


def test_explicit_datasheet_uses_provider_datasheet_not_product_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    install_found_fakes(monkeypatch, found_resolution(), captured)

    exit_code = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--datasheet-link",
            "digikey",
            "--symbol",
            "--output",
            str(tmp_path / "parts"),
        ]
    )

    assert exit_code == 0
    assert captured["provider_names"] == ["lcsc", "digikey"]
    assert captured["datasheet_url"].endswith("/digikey/datasheet.pdf")
    assert not captured["datasheet_url"].endswith("/product")


def test_no_price_and_no_stock_are_manifest_only_projections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    install_found_fakes(monkeypatch, found_resolution(), captured)
    json_path = tmp_path / "part.json"

    exit_code = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--manifest-json",
            str(json_path),
            "--no-price",
            "--no-stock",
        ]
    )

    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert all(item["stock"] is None for item in document["distributor_records"])
    assert all(item["price_breaks"] == [] for item in document["distributor_records"])
    assert result_cache_values(found_resolution()) == (123, 1.25)


def result_cache_values(result: MetadataResolution) -> tuple[int | None, float]:
    record = result.distributor_records[0]
    return record.stock, record.price_breaks[0].unit_price


def test_cad_not_found_writes_manifest_without_kicad_and_is_optional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = MetadataResolution(
        distributor_records=[distributor("digikey")],
        cad=CadRecord(source="easyeda", verification_status=CAD_NOT_FOUND),
        trusted_mpn="OPA333AIDBVR",
        trusted_manufacturer="Texas Instruments",
    )
    monkeypatch.setattr(cli, "resolve_metadata", lambda **kwargs: result)
    called = False

    def should_not_export(*args: Any, **kwargs: Any) -> bool:
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(cli, "_process_component", should_not_export)
    manifest = tmp_path / "not-found.json"
    output = tmp_path / "not-found"

    exit_code = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "digikey",
            "--symbol",
            "--output",
            str(output),
            "--manifest-json",
            str(manifest),
        ]
    )

    assert exit_code == 0
    assert not called
    assert not output.with_suffix(".kicad_sym").exists()
    assert (
        json.loads(manifest.read_text(encoding="utf-8"))["verification_status"]
        == CAD_NOT_FOUND
    )
    assert "CAD_NOT_FOUND" in caplog.text
    assert any(
        record.levelno == 30 and "CAD_NOT_FOUND" in record.getMessage()
        for record in caplog.records
    )


def test_require_cad_returns_one_after_writing_not_found_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = MetadataResolution(
        cad=CadRecord(source="easyeda", verification_status=CAD_NOT_FOUND),
        trusted_mpn="OPA333AIDBVR",
    )
    monkeypatch.setattr(cli, "resolve_metadata", lambda **kwargs: result)
    manifest = tmp_path / "required.json"

    exit_code = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--manifest-json",
            str(manifest),
            "--require-cad",
        ]
    )

    assert exit_code == 1
    assert manifest.is_file()
    assert any(
        record.levelno == 40
        and "CAD_NOT_FOUND" in record.getMessage()
        and "--require-cad" in record.getMessage()
        for record in caplog.records
    )


def test_provider_errors_are_logged_without_manifest_or_conflict_output(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = MetadataResolution(
        trusted_mpn="OPA333AIDBVR",
        provider_errors={"mouser": "AUTH_MISSING"},
    )
    monkeypatch.setattr(cli, "resolve_metadata", lambda **kwargs: result)

    exit_code = cli.main(["--mpn", "OPA333AIDBVR", "--providers", "mouser", "--symbol"])

    assert exit_code == 0
    assert any(
        record.levelno == 30
        and "mouser" in record.getMessage()
        and "AUTH_MISSING" in record.getMessage()
        for record in caplog.records
    )


def test_explicit_datasheet_failure_keeps_verified_cad_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = found_resolution()
    mouser = next(
        record for record in result.distributor_records if record.provider == "mouser"
    )
    mouser.datasheet_url = None
    captured: dict[str, Any] = {}
    install_found_fakes(monkeypatch, result, captured)
    manifest = tmp_path / "datasheet-failure.json"

    exit_code = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--symbol",
            "--output",
            str(tmp_path / "parts"),
            "--datasheet-link",
            "mouser",
            "--manifest-json",
            str(manifest),
        ]
    )

    document = json.loads(manifest.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert document["verification_status"] == PARTIAL
    assert document["cad"]["verification_status"] == VERIFIED
    assert document["provider_errors"]["datasheet"] == "DATASHEET_UNAVAILABLE"


def test_export_failure_keeps_verified_cad_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = found_resolution()
    captured: dict[str, Any] = {}
    install_found_fakes(monkeypatch, result, captured)
    monkeypatch.setattr(cli, "_process_component", lambda *args, **kwargs: False)
    manifest = tmp_path / "export-failure.json"

    exit_code = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--symbol",
            "--output",
            str(tmp_path / "parts"),
            "--manifest-json",
            str(manifest),
        ]
    )

    document = json.loads(manifest.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert document["verification_status"] == PARTIAL
    assert document["cad"]["verification_status"] == VERIFIED
    assert document["provider_errors"]["export"] == "EXPORT_FAILED"


def test_cad_transport_failure_is_partial_and_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = MetadataResolution(
        distributor_records=[distributor("digikey")],
        trusted_mpn="OPA333AIDBVR",
        trusted_manufacturer="Texas Instruments",
        provider_errors={"easyeda": "NETWORK_ERROR"},
        blocking_error="NETWORK_ERROR",
    )
    monkeypatch.setattr(cli, "resolve_metadata", lambda **kwargs: result)
    manifest = tmp_path / "network.json"

    exit_code = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--manifest-json",
            str(manifest),
        ]
    )

    document = json.loads(manifest.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert document["verification_status"] == PARTIAL
    assert document["verification_status"] != CAD_NOT_FOUND


def test_cad_invalid_response_is_partial_nonzero_not_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = MetadataResolution(
        trusted_mpn="OPA333AIDBVR",
        provider_errors={"easyeda": "INVALID_RESPONSE"},
        blocking_error="INVALID_RESPONSE",
    )
    monkeypatch.setattr(cli, "resolve_metadata", lambda **kwargs: result)
    manifest = tmp_path / "invalid-response.json"

    exit_code = cli.main(["--mpn", "OPA333AIDBVR", "--manifest-json", str(manifest)])

    document = json.loads(manifest.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert document["verification_status"] == PARTIAL
    assert document["verification_status"] != CAD_NOT_FOUND
    assert "INVALID_RESPONSE" in caplog.text
    assert "CAD_NOT_FOUND" not in caplog.text


def test_pin_pad_mismatch_writes_diagnostic_manifest_and_returns_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = found_resolution()
    monkeypatch.setattr(cli, "resolve_metadata", lambda **kwargs: result)
    monkeypatch.setattr(
        cli,
        "_verify_metadata_cad",
        lambda resolution, **_kwargs: (
            CAD_NOT_FOUND.replace("NOT_FOUND", "PIN_PAD_MISMATCH"),
            None,
            None,
        ),
    )
    result.blocking_error = "CAD_PIN_PAD_MISMATCH"
    result.provider_errors["cad_verification"] = "pins=1,2;pads=1,3"
    manifest = tmp_path / "mismatch.json"

    exit_code = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--manifest-json",
            str(manifest),
        ]
    )

    assert exit_code == 1
    assert (
        json.loads(manifest.read_text(encoding="utf-8"))["verification_status"]
        == "CAD_PIN_PAD_MISMATCH"
    )
