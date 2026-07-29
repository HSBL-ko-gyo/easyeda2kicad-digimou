from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

import easyeda2kicad_digimou.__main__ as cli
from easyeda2kicad_digimou.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad_digimou.metadata.cache import MetadataCache
from easyeda2kicad_digimou.metadata.manifest import manifest_to_dict
from easyeda2kicad_digimou.metadata.models import (
    GUEST_LOOKUP_UNSUPPORTED,
    CadRecord,
    DistributorRecord,
    ProviderDiagnostic,
)
from easyeda2kicad_digimou.metadata.service import MetadataResolution, resolve_metadata
from easyeda2kicad_digimou.providers import (
    DigiKeyProvider,
    MetadataProvider,
    MouserProvider,
    NotFoundError,
)


class _NoMatchLcscProvider:
    name = "lcsc"
    last_raw_response: dict[str, Any] = {}

    def get_cache_context(self) -> dict[str, str]:
        return {}

    def search_exact_mpn(self, manufacturer: str | None, mpn: str) -> DistributorRecord:
        del manufacturer, mpn
        raise NotFoundError(self.name, operation="search_exact_mpn")

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord:
        del part_id
        raise NotFoundError(self.name, operation="get_part_by_distributor_id")


def test_no_credentials_report_guest_unsupported_without_any_http_request(
    tmp_path: Path,
) -> None:
    requests: list[Any] = []

    def forbidden_http(request: Any, **kwargs: Any) -> Any:
        requests.append((request, kwargs))
        raise AssertionError("guest capability detection must not make HTTP requests")

    providers: dict[str, MetadataProvider] = {
        "lcsc": cast(MetadataProvider, _NoMatchLcscProvider()),
        "digikey": DigiKeyProvider(env={}, opener=forbidden_http),
        "mouser": MouserProvider(env={}, opener=forbidden_http),
    }

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer="Texas Instruments",
        requested_lcsc_id=None,
        provider_names=("digikey", "mouser"),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path / "cache"),
        provider_factory=lambda name, api: providers[name],
        cad_provider_factory=lambda api: pytest.fail("EasyEDA must not be called"),
    )

    assert requests == []
    assert result.provider_errors == {
        "digikey": GUEST_LOOKUP_UNSUPPORTED,
        "mouser": GUEST_LOOKUP_UNSUPPORTED,
    }
    assert result.provider_diagnostics["digikey"].operation == "oauth"
    assert result.provider_diagnostics["digikey"].setup_url == (
        "https://developer.digikey.com/tutorials-and-resources/oauth-20-2-legged-flow"
    )
    assert result.provider_diagnostics["mouser"].operation == "part-search"
    assert result.provider_diagnostics["mouser"].setup_url == (
        "https://www.mouser.com/api-search/"
    )
    assert "NOT_FOUND" not in result.provider_errors.values()

    payload = manifest_to_dict(result.to_merged())
    assert payload["provider_diagnostics"]["digikey"]["setup_url"].startswith(
        "https://developer.digikey.com/"
    )
    assert payload["provider_diagnostics"]["mouser"]["setup_url"] == (
        "https://www.mouser.com/api-search/"
    )


def test_provider_diagnostic_setup_url_is_additive_and_round_trips() -> None:
    legacy = ProviderDiagnostic(code="AUTH_FAILED", status=401)
    diagnostic = ProviderDiagnostic(
        code=GUEST_LOOKUP_UNSUPPORTED,
        operation="oauth",
        setup_url="https://developer.digikey.com/products",
    )

    assert legacy.to_dict() == {
        "code": "AUTH_FAILED",
        "operation": None,
        "status": 401,
    }
    assert ProviderDiagnostic.from_dict(diagnostic.to_dict()) == diagnostic


def _guest_resolution() -> MetadataResolution:
    return MetadataResolution(
        cad=CadRecord(source="easyeda", verification_status="CAD_NOT_FOUND"),
        trusted_mpn="OPA333AIDBVR",
        trusted_manufacturer="Texas Instruments",
        provider_errors={"digikey": GUEST_LOOKUP_UNSUPPORTED},
        provider_diagnostics={
            "digikey": ProviderDiagnostic(
                code=GUEST_LOOKUP_UNSUPPORTED,
                operation="oauth",
                setup_url="https://developer.digikey.com/products",
            )
        },
    )


def test_require_providers_is_opt_in_and_writes_manifest_before_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(cli, "resolve_metadata", lambda **kwargs: _guest_resolution())
    optional_manifest = tmp_path / "optional.json"
    strict_manifest = tmp_path / "strict.json"

    optional_exit = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "digikey",
            "--manifest-json",
            str(optional_manifest),
        ]
    )
    strict_exit = cli.main(
        [
            "--mpn",
            "OPA333AIDBVR",
            "--providers",
            "digikey",
            "--manifest-json",
            str(strict_manifest),
            "--require-providers",
        ]
    )

    assert optional_exit == 0
    assert strict_exit == 1
    assert optional_manifest.is_file()
    assert strict_manifest.is_file()
    assert json.loads(strict_manifest.read_text(encoding="utf-8"))[
        "provider_errors"
    ] == {"digikey": GUEST_LOOKUP_UNSUPPORTED}
    assert "Required metadata provider digikey" in caplog.text


def test_require_providers_succeeds_when_every_selected_provider_returns_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = MetadataResolution(
        cad=CadRecord(source="easyeda", verification_status="CAD_NOT_FOUND"),
        trusted_mpn="OPA333AIDBVR",
        trusted_manufacturer="Texas Instruments",
        distributor_records=[
            DistributorRecord(
                provider="digikey",
                distributor_part_number="296-OPA333AIDBVRCT-ND",
                manufacturer="Texas Instruments",
                mpn="OPA333AIDBVR",
            )
        ],
    )
    monkeypatch.setattr(cli, "resolve_metadata", lambda **kwargs: result)

    assert (
        cli.main(
            [
                "--mpn",
                "OPA333AIDBVR",
                "--providers",
                "digikey",
                "--manifest-json",
                str(tmp_path / "strict-success.json"),
                "--require-providers",
            ]
        )
        == 0
    )
