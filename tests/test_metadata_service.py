from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, cast

import pytest

from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.metadata.cache import (
    CacheCorruptError as MetadataCacheCorruptError,
    MetadataCache,
    OfflineCacheMissError as MetadataOfflineCacheMissError,
)
from easyeda2kicad.metadata.manifest import csv_manifest_rows, manifest_to_dict
from easyeda2kicad.metadata.merge import CAD_NOT_FOUND, PARTIAL, VERIFIED
from easyeda2kicad.metadata.models import CadRecord, DistributorRecord
from easyeda2kicad.metadata.service import (
    MetadataServiceError,
    _cached_exact_lookup,
    resolve_metadata,
)
from easyeda2kicad.metadata.symbol_fields import build_symbol_fields
from easyeda2kicad.providers import (
    AmbiguousMatchError,
    AuthFailedError,
    AuthMissingError,
    InvalidResponseError,
    MetadataProvider,
    NetworkError,
    NotFoundError,
)


class FakeMetadataProvider:
    def __init__(
        self,
        name: str,
        record: DistributorRecord | None = None,
        error: Exception | None = None,
        cache_context: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.record = record
        self.error = error
        self.exact_calls = 0
        self.id_calls = 0
        self.last_raw_response: dict[str, Any] = {"provider": name}
        self.cache_context = cache_context or {}

    def get_cache_context(self) -> dict[str, str]:
        return dict(self.cache_context)

    def search_exact_mpn(self, manufacturer: str | None, mpn: str) -> DistributorRecord:
        del manufacturer, mpn
        self.exact_calls += 1
        return self._result()

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord:
        del part_id
        self.id_calls += 1
        return self._result()

    def _result(self) -> DistributorRecord:
        if self.error is not None:
            raise self.error
        assert self.record is not None
        return self.record


class FakeCadProvider:
    name = "easyeda"

    def __init__(
        self,
        raw: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.raw = raw
        self.error = error
        self.calls: list[str] = []

    def get_cad_data(self, lcsc_id: str) -> tuple[CadRecord, dict[str, Any]]:
        self.calls.append(lcsc_id)
        if self.error is not None:
            raise self.error
        assert self.raw is not None
        return (
            CadRecord(
                source="easyeda",
                lcsc_part_number=lcsc_id,
                verification_status=PARTIAL,
            ),
            self.raw,
        )


class FakeCatalogueApi:
    """Anonymous catalogue transport that fails if treated as a CAD API."""

    def __init__(self, page: dict[str, Any]) -> None:
        self.page = page
        self.offline = False
        self.last_error: str | None = None
        self.search_calls: list[tuple[str, int, int]] = []
        self.cad_calls: list[str] = []

    def search_jlcpcb_components(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 10,
        part_type: str | None = None,
    ) -> dict[str, Any]:
        del part_type
        self.search_calls.append((keyword, page, page_size))
        return self.page

    def get_cad_data_of_component(self, lcsc_id: str) -> dict[str, Any]:
        self.cad_calls.append(lcsc_id)
        raise AssertionError("LCSC metadata provider crossed the CAD boundary")


def cad_payload(
    mpn: str = "OPA333AIDBVR",
    lcsc: str = "C30878",
    manufacturer: str = "Texas Instruments",
) -> dict[str, Any]:
    identity = {
        "Manufacturer": manufacturer,
        "Manufacturer Part": mpn,
        "Supplier Part": lcsc,
    }
    return {
        "uuid": "easyeda-uuid",
        "lcsc": {"number": lcsc},
        "dataStr": {"head": {"c_para": identity}},
        "packageDetail": {"dataStr": {"head": {"c_para": dict(identity)}}},
    }


def cad_payload_without_mpn() -> dict[str, Any]:
    payload = cad_payload()
    payload["dataStr"]["head"]["c_para"].pop("Manufacturer Part")
    payload["packageDetail"]["dataStr"]["head"]["c_para"].pop("Manufacturer Part")
    return payload


def record(
    provider: str,
    mpn: str = "OPA333AIDBVR",
    manufacturer: str = "Texas Instruments",
) -> DistributorRecord:
    part = {
        "lcsc": "C30878",
        "digikey": "296-OPA333AIDBVRCT-ND",
        "mouser": "595-OPA333AIDBVR",
    }[provider]
    return DistributorRecord(
        provider=provider,
        distributor_part_number=part,
        manufacturer=manufacturer,
        mpn=mpn,
        datasheet_url="https://example.invalid/{0}.pdf".format(provider),
        retrieved_at="2026-07-22T00:00:00Z",
    )


def make_factory(
    providers: dict[str, FakeMetadataProvider],
) -> Callable[[str, EasyedaApi], MetadataProvider]:
    def factory(name: str, api: EasyedaApi) -> MetadataProvider:
        del api
        return cast(MetadataProvider, providers[name])

    return factory


def test_mpn_only_resolves_lcsc_before_other_metadata(tmp_path: Path) -> None:
    providers = {
        name: FakeMetadataProvider(name, record(name))
        for name in ("lcsc", "digikey", "mouser")
    }
    cad = FakeCadProvider(cad_payload())

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id=None,
        provider_names=("lcsc", "digikey", "mouser"),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory(providers),
        cad_provider_factory=lambda api: cad,
    )
    merged = result.to_merged(VERIFIED)

    assert cad.calls == ["C30878"]
    assert providers["lcsc"].exact_calls == 1
    assert [item.provider for item in merged.distributor_records] == [
        "lcsc",
        "digikey",
        "mouser",
    ]
    assert merged.verification_status == VERIFIED


def test_explicit_manufacturer_accepts_part_scoped_cad_display_alias(
    tmp_path: Path,
) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer="Texas Instruments",
        requested_lcsc_id="C30878",
        provider_names=("lcsc",),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc}),
        cad_provider_factory=lambda api: FakeCadProvider(
            cad_payload(manufacturer="TI(德州仪器)")
        ),
    )
    merged = result.to_merged(VERIFIED)

    assert lcsc.id_calls == 1
    assert result.cad_identity is not None
    assert result.cad_identity.manufacturer == "TI(德州仪器)"
    assert merged.identity.manufacturer == "Texas Instruments"
    assert [item.provider for item in merged.distributor_records] == ["lcsc"]


def test_explicit_cad_manufacturer_alias_requires_lcsc_id_evidence(
    tmp_path: Path,
) -> None:
    lcsc = FakeMetadataProvider(
        "lcsc", error=NetworkError("lcsc", operation="id-lookup")
    )
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    with pytest.raises(MetadataServiceError) as exc_info:
        resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer="Texas Instruments",
            requested_lcsc_id="C30878",
            provider_names=("digikey",),
            cad_api=EasyedaApi(),
            cache=MetadataCache(tmp_path),
            provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
            cad_provider_factory=lambda api: FakeCadProvider(
                cad_payload(manufacturer="TI(德州仪器)")
            ),
        )

    assert exc_info.value.code == "NETWORK_ERROR"
    assert lcsc.id_calls == 1
    assert digikey.exact_calls == 0


def test_unproven_inferred_manufacturer_alias_is_rejected(
    tmp_path: Path,
) -> None:
    providers = {
        "lcsc": FakeMetadataProvider(
            "lcsc", record("lcsc", manufacturer="TI(德州仪器)")
        ),
        "digikey": FakeMetadataProvider("digikey", record("digikey")),
    }

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id=None,
        provider_names=("lcsc", "digikey"),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory(providers),
        cad_provider_factory=lambda api: FakeCadProvider(
            cad_payload(manufacturer="TI(德州仪器)")
        ),
    )

    assert [item.provider for item in result.distributor_records] == ["lcsc"]
    assert result.provider_errors == {"digikey": "MANUFACTURER_UNVERIFIED"}
    assert result.rejected_manufacturers == {"digikey": "Texas Instruments"}
    assert result.trusted_manufacturer == "TI(德州仪器)"
    merged = result.to_merged(VERIFIED)
    assert [item.provider for item in merged.distributor_records] == ["lcsc"]
    assert merged.verification_status == PARTIAL
    conflict = next(item for item in merged.conflicts if item.field == "manufacturer")
    assert conflict.values == {
        "lcsc": "TI(德州仪器)",
        "easyeda": "TI(德州仪器)",
        "digikey": "Texas Instruments",
    }
    assert conflict.reason == (
        "manufacturer value is not supported by exact part-scoped evidence"
    )


def test_easyeda_manufacturer_alias_is_retained_when_only_digikey_is_selected(
    tmp_path: Path,
) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=("digikey",),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
        cad_provider_factory=lambda api: FakeCadProvider(
            cad_payload(manufacturer="TI(德州仪器)")
        ),
    )

    merged = result.to_merged(VERIFIED)

    assert lcsc.id_calls == 1
    assert [item.provider for item in merged.distributor_records] == ["digikey"]
    assert merged.identity.manufacturer == "TI(德州仪器)"
    assert merged.provenance["identity.manufacturer"][0].provider == "easyeda"
    assert merged.provenance["identity.manufacturer"][0].source_field == (
        "dataStr.head.c_para.Manufacturer"
    )
    assert (
        merged.provenance["identity.manufacturer_normalized"][0].provider == "easyeda"
    )
    conflict = next(item for item in merged.conflicts if item.field == "manufacturer")
    assert conflict.values == {
        "easyeda": "TI(德州仪器)",
        "lcsc": "Texas Instruments",
        "digikey": "Texas Instruments",
    }
    assert conflict.selected_value == merged.identity.manufacturer
    assert conflict.reason == "inferred manufacturer display names disagree"


@pytest.mark.parametrize(
    ("provider_name", "part_field", "url_field"),
    (
        ("digikey", "DigiKey Part", "DigiKey Product URL"),
        ("mouser", "Mouser Part", "Mouser Product URL"),
    ),
)
def test_unverified_external_manufacturer_is_diagnostic_only(
    tmp_path: Path,
    provider_name: str,
    part_field: str,
    url_field: str,
) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc", manufacturer="Acme Devices"))
    external_record = record(provider_name, manufacturer="Other Devices")
    external_record.package = "UNTRUSTED-PACKAGE"
    external_record.lifecycle = "UNTRUSTED-LIFECYCLE"
    external_record.product_url = "https://other.example.invalid/product"
    external_record.datasheet_url = "https://other.example.invalid/datasheet.pdf"
    external = FakeMetadataProvider(provider_name, external_record)

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=(provider_name,),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc, provider_name: external}),
        cad_provider_factory=lambda api: FakeCadProvider(
            cad_payload(manufacturer="Acme Devices")
        ),
    )

    assert lcsc.id_calls == 1
    assert result.distributor_records == []
    assert result.provider_errors == {provider_name: "MANUFACTURER_UNVERIFIED"}
    assert result.rejected_manufacturers == {provider_name: "Other Devices"}

    merged = result.to_merged(VERIFIED)
    assert merged.verification_status == PARTIAL
    assert merged.distributor_records == []
    assert merged.identity.manufacturer == "Acme Devices"
    assert merged.identity.package is None
    assert merged.identity.lifecycle is None
    assert merged.identity.manufacturer_datasheet_url is None
    assert all(
        entry.provider != provider_name
        for entries in merged.provenance.values()
        for entry in entries
    )
    conflict = next(item for item in merged.conflicts if item.field == "manufacturer")
    assert conflict.values == {
        "easyeda": "Acme Devices",
        "lcsc": "Acme Devices",
        provider_name: "Other Devices",
    }
    assert conflict.reason == (
        "manufacturer value is not supported by exact part-scoped evidence"
    )

    manifest = manifest_to_dict(merged)
    assert manifest["distributor_records"] == []
    rows = csv_manifest_rows(merged)
    assert len(rows) == 1
    assert rows[0]["Provider"] == ""
    assert rows[0]["Distributor Part Number"] == ""
    assert rows[0][part_field] == ""
    assert rows[0][url_field] == ""
    symbol_fields = build_symbol_fields(merged)
    assert part_field not in symbol_fields
    assert url_field not in symbol_fields


def test_combined_identity_mismatch_stops_before_distributor_calls(
    tmp_path: Path,
) -> None:
    providers = {
        name: FakeMetadataProvider(name, record(name))
        for name in ("lcsc", "digikey", "mouser")
    }
    cad = FakeCadProvider(cad_payload(mpn="OPA333AIDBVR-T"))

    with pytest.raises(MetadataServiceError) as exc_info:
        resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer=None,
            requested_lcsc_id="C30878",
            provider_names=("lcsc", "digikey", "mouser"),
            cad_api=EasyedaApi(),
            cache=MetadataCache(tmp_path),
            provider_factory=make_factory(providers),
            cad_provider_factory=lambda api: cad,
        )

    assert exc_info.value.code == "MPN_MISMATCH"
    assert all(provider.exact_calls == 0 for provider in providers.values())
    assert all(provider.id_calls == 0 for provider in providers.values())


def test_cad_missing_mpn_uses_unselected_lcsc_identity_lookup(
    tmp_path: Path,
) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=("digikey",),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
        cad_provider_factory=lambda api: FakeCadProvider(cad_payload_without_mpn()),
    )

    assert result.cad_data is not None
    assert result.cad_identity is not None
    assert result.cad_identity.lcsc_id == "C30878"
    assert result.cad_identity.mpn is None
    assert lcsc.id_calls == 1
    assert [item.provider for item in result.distributor_records] == ["digikey"]
    assert digikey.exact_calls == 1


def test_cad_missing_mpn_rejects_lcsc_identity_mismatch(tmp_path: Path) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc", mpn="OPA333AIDBVT"))
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    with pytest.raises(MetadataServiceError) as exc_info:
        resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer=None,
            requested_lcsc_id="C30878",
            provider_names=("digikey",),
            cad_api=EasyedaApi(),
            cache=MetadataCache(tmp_path),
            provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
            cad_provider_factory=lambda api: FakeCadProvider(cad_payload_without_mpn()),
        )

    assert exc_info.value.code == "MPN_MISMATCH"
    assert lcsc.id_calls == 1
    assert digikey.exact_calls == 0


def test_cad_missing_mpn_fails_closed_when_lcsc_identity_is_unavailable(
    tmp_path: Path,
) -> None:
    lcsc = FakeMetadataProvider(
        "lcsc", error=NetworkError("lcsc", operation="id-lookup")
    )
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    with pytest.raises(MetadataServiceError) as exc_info:
        resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer=None,
            requested_lcsc_id="C30878",
            provider_names=("digikey",),
            cad_api=EasyedaApi(),
            cache=MetadataCache(tmp_path),
            provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
            cad_provider_factory=lambda api: FakeCadProvider(cad_payload_without_mpn()),
        )

    assert exc_info.value.code == "NETWORK_ERROR"
    assert lcsc.id_calls == 1
    assert digikey.exact_calls == 0


def test_confirmed_cad_not_found_keeps_distributor_metadata(tmp_path: Path) -> None:
    digikey = FakeMetadataProvider("digikey", record("digikey"))
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    cad = FakeCadProvider(error=NotFoundError("easyeda", operation="cad-fetch"))

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer="Texas Instruments",
        requested_lcsc_id="C30878",
        provider_names=("digikey",),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
        cad_provider_factory=lambda api: cad,
    )
    merged = result.to_merged(CAD_NOT_FOUND)

    assert merged.verification_status == CAD_NOT_FOUND
    assert [item.provider for item in merged.distributor_records] == ["digikey"]
    assert lcsc.id_calls == 1
    assert result.blocking_error is None


def test_id_only_cad_not_found_resolves_unselected_lcsc_before_external(
    tmp_path: Path,
) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    result = resolve_metadata(
        requested_mpn=None,
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=("digikey",),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
        cad_provider_factory=lambda api: FakeCadProvider(
            error=NotFoundError("easyeda", operation="cad-fetch")
        ),
    )

    assert result.trusted_mpn == "OPA333AIDBVR"
    assert lcsc.id_calls == 1
    assert digikey.exact_calls == 1
    assert [item.provider for item in result.distributor_records] == ["digikey"]
    assert result.to_merged(CAD_NOT_FOUND).verification_status == CAD_NOT_FOUND


def test_id_only_cad_missing_mpn_resolves_unselected_lcsc_before_external(
    tmp_path: Path,
) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    result = resolve_metadata(
        requested_mpn=None,
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=("digikey",),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
        cad_provider_factory=lambda api: FakeCadProvider(cad_payload_without_mpn()),
    )

    assert result.cad_identity is not None
    assert result.cad_identity.mpn is None
    assert result.trusted_mpn == "OPA333AIDBVR"
    assert lcsc.id_calls == 1
    assert digikey.exact_calls == 1
    assert [item.provider for item in result.distributor_records] == ["digikey"]


@pytest.mark.parametrize(
    ("identity_error", "expected_code"),
    [
        (NotFoundError("lcsc", operation="id-lookup"), "NOT_FOUND"),
        (NetworkError("lcsc", operation="id-lookup"), "NETWORK_ERROR"),
        (AmbiguousMatchError("lcsc", operation="id-lookup"), "AMBIGUOUS"),
    ],
)
def test_id_only_external_provider_fails_closed_when_lcsc_identity_unavailable(
    tmp_path: Path,
    identity_error: Exception,
    expected_code: str,
) -> None:
    lcsc = FakeMetadataProvider("lcsc", error=identity_error)
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    with pytest.raises(MetadataServiceError) as exc_info:
        resolve_metadata(
            requested_mpn=None,
            requested_manufacturer=None,
            requested_lcsc_id="C30878",
            provider_names=("digikey",),
            cad_api=EasyedaApi(),
            cache=MetadataCache(tmp_path),
            provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
            cad_provider_factory=lambda api: FakeCadProvider(
                error=NotFoundError("easyeda", operation="cad-fetch")
            ),
        )

    assert exc_info.value.code == expected_code
    assert lcsc.id_calls == 1
    assert digikey.exact_calls == 0


def test_cad_not_found_rejects_unselected_lcsc_mpn_mismatch(
    tmp_path: Path,
) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc", mpn="OPA333AIDBVT"))
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    with pytest.raises(MetadataServiceError) as exc_info:
        resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer=None,
            requested_lcsc_id="C30878",
            provider_names=("digikey",),
            cad_api=EasyedaApi(),
            cache=MetadataCache(tmp_path),
            provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
            cad_provider_factory=lambda api: FakeCadProvider(
                error=NotFoundError("easyeda", operation="cad-fetch")
            ),
        )

    assert exc_info.value.code == "MPN_MISMATCH"
    assert lcsc.id_calls == 1
    assert digikey.exact_calls == 0


@pytest.mark.parametrize(
    ("identity_error", "expected_code"),
    [
        (NotFoundError("lcsc", operation="id-lookup"), "NOT_FOUND"),
        (NetworkError("lcsc", operation="id-lookup"), "NETWORK_ERROR"),
        (AmbiguousMatchError("lcsc", operation="id-lookup"), "AMBIGUOUS"),
    ],
)
def test_cad_not_found_fails_closed_when_unselected_lcsc_identity_is_unavailable(
    tmp_path: Path,
    identity_error: Exception,
    expected_code: str,
) -> None:
    lcsc = FakeMetadataProvider("lcsc", error=identity_error)
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    with pytest.raises(MetadataServiceError) as exc_info:
        resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer=None,
            requested_lcsc_id="C30878",
            provider_names=("digikey",),
            cad_api=EasyedaApi(),
            cache=MetadataCache(tmp_path),
            provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
            cad_provider_factory=lambda api: FakeCadProvider(
                error=NotFoundError("easyeda", operation="cad-fetch")
            ),
        )

    assert exc_info.value.code == expected_code
    assert lcsc.id_calls == 1
    assert digikey.exact_calls == 0


def test_cad_not_found_explicit_pair_fails_closed_on_offline_identity_cache_miss(
    tmp_path: Path,
) -> None:
    lcsc = FakeMetadataProvider(
        "lcsc", error=AssertionError("offline identity lookup used network")
    )
    digikey = FakeMetadataProvider("digikey", record("digikey"))

    with pytest.raises(MetadataServiceError) as exc_info:
        resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer=None,
            requested_lcsc_id="C30878",
            provider_names=("digikey",),
            cad_api=EasyedaApi(),
            cache=MetadataCache(tmp_path),
            offline=True,
            provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
            cad_provider_factory=lambda api: FakeCadProvider(
                error=NotFoundError("easyeda", operation="cad-fetch")
            ),
        )

    assert exc_info.value.code == "OFFLINE_CACHE_MISS"
    assert lcsc.id_calls == 0
    assert digikey.exact_calls == 0


def test_cad_network_error_is_not_cad_not_found(tmp_path: Path) -> None:
    cad = FakeCadProvider(error=NetworkError("easyeda", operation="cad-fetch"))
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=(),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc}),
        cad_provider_factory=lambda api: cad,
    )
    merged = result.to_merged(PARTIAL)

    assert result.blocking_error == "NETWORK_ERROR"
    assert merged.verification_status == PARTIAL
    assert merged.verification_status != CAD_NOT_FOUND


def test_offline_metadata_cache_hit_performs_no_provider_request(
    tmp_path: Path,
) -> None:
    cache = MetadataCache(tmp_path)
    request = cache.canonical_request(
        "lcsc",
        "search_exact_mpn",
        mpn="OPA333AIDBVR",
        manufacturer=None,
        options={"provider_context": {}},
    )
    cache_key = cache.get_cache_key("lcsc", request)
    cached_record = record("lcsc")
    cached_record.raw_response_cache_key = cache_key
    cache.save("lcsc", request, {"cached": True}, cached_record.to_dict())
    lcsc = FakeMetadataProvider(
        "lcsc", error=AssertionError("offline provider must not be called")
    )
    cad = FakeCadProvider(cad_payload())

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id=None,
        provider_names=("lcsc",),
        cad_api=EasyedaApi(),
        cache=cache,
        offline=True,
        provider_factory=make_factory({"lcsc": lcsc}),
        cad_provider_factory=lambda api: cad,
    )

    assert result.cad_data is not None
    assert lcsc.exact_calls == 0
    assert lcsc.id_calls == 0


def test_offline_metadata_cache_miss_does_not_call_provider(tmp_path: Path) -> None:
    lcsc = FakeMetadataProvider(
        "lcsc", error=AssertionError("offline provider must not be called")
    )

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id=None,
        provider_names=("lcsc",),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        offline=True,
        provider_factory=make_factory({"lcsc": lcsc}),
        cad_provider_factory=lambda api: FakeCadProvider(cad_payload()),
    )

    assert result.blocking_error == "OFFLINE_CACHE_MISS"
    assert result.to_merged(PARTIAL).verification_status == PARTIAL
    assert lcsc.exact_calls == 0


def test_incomplete_exact_failure_is_never_cached_or_lost_offline(
    tmp_path: Path,
) -> None:
    cache = MetadataCache(tmp_path / "metadata-cache")
    online_provider = FakeMetadataProvider(
        "mouser",
        error=InvalidResponseError("mouser", operation="exact-normalize"),
    )

    with pytest.raises(InvalidResponseError):
        _cached_exact_lookup(
            cast(MetadataProvider, online_provider),
            cache,
            "Texas Instruments",
            "OPA333AIDBVR",
            offline=False,
            refresh=False,
        )

    request = cache.canonical_request(
        "mouser",
        "search_exact_mpn",
        mpn="OPA333AIDBVR",
        manufacturer="Texas Instruments",
        options={"provider_context": {}},
    )
    key = cache.get_cache_key("mouser", request)
    assert online_provider.exact_calls == 1
    assert not cache.path("mouser", key, "raw").exists()
    assert not cache.path("mouser", key, "normalized").exists()

    offline_provider = FakeMetadataProvider("mouser", record=record("mouser"))
    with pytest.raises(MetadataOfflineCacheMissError):
        _cached_exact_lookup(
            cast(MetadataProvider, offline_provider),
            cache,
            "Texas Instruments",
            "OPA333AIDBVR",
            offline=True,
            refresh=False,
        )
    assert offline_provider.exact_calls == 0

    refresh_provider = FakeMetadataProvider(
        "mouser",
        error=InvalidResponseError("mouser", operation="exact-normalize"),
    )
    with pytest.raises(InvalidResponseError):
        _cached_exact_lookup(
            cast(MetadataProvider, refresh_provider),
            cache,
            "Texas Instruments",
            "OPA333AIDBVR",
            offline=False,
            refresh=True,
        )
    assert refresh_provider.exact_calls == 1
    assert not cache.path("mouser", key, "raw").exists()
    assert not cache.path("mouser", key, "normalized").exists()


def test_schema3_overflowing_normalized_exact_cache_is_fail_closed_in_all_modes(
    tmp_path: Path,
) -> None:
    def cache_with_overflowing_record(name: str) -> MetadataCache:
        cache = MetadataCache(
            tmp_path / name,
            freshness_seconds=1_000_000_000,
        )
        request = cache.canonical_request(
            "mouser",
            "search_exact_mpn",
            mpn="OPA333AIDBVR",
            manufacturer="Texas Instruments",
            options={"provider_context": {}},
        )
        normalized = record("mouser").to_dict()
        normalized["price_breaks"] = [
            {"quantity": 1, "unit_price": 10**400, "currency": "USD"}
        ]
        cache.save(
            "mouser",
            request,
            raw={"SearchResults": {"Parts": []}},
            normalized=normalized,
        )
        return cache

    online_cache = cache_with_overflowing_record("online")
    online_provider = FakeMetadataProvider("mouser", record=record("mouser"))
    online_record = _cached_exact_lookup(
        cast(MetadataProvider, online_provider),
        online_cache,
        "Texas Instruments",
        "OPA333AIDBVR",
        offline=False,
        refresh=False,
    )
    assert online_record.mpn == "OPA333AIDBVR"
    assert online_provider.exact_calls == 1

    offline_cache = cache_with_overflowing_record("offline")
    offline_provider = FakeMetadataProvider(
        "mouser",
        error=AssertionError("offline provider must not be called"),
    )
    with pytest.raises(MetadataCacheCorruptError):
        _cached_exact_lookup(
            cast(MetadataProvider, offline_provider),
            offline_cache,
            "Texas Instruments",
            "OPA333AIDBVR",
            offline=True,
            refresh=False,
        )
    assert offline_provider.exact_calls == 0

    refresh_cache = cache_with_overflowing_record("refresh")
    refresh_provider = FakeMetadataProvider("mouser", record=record("mouser"))
    refresh_record = _cached_exact_lookup(
        cast(MetadataProvider, refresh_provider),
        refresh_cache,
        "Texas Instruments",
        "OPA333AIDBVR",
        offline=False,
        refresh=True,
    )
    assert refresh_record.mpn == "OPA333AIDBVR"
    assert refresh_provider.exact_calls == 1


def test_external_auth_failure_is_recoverable_partial(tmp_path: Path) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    digikey = FakeMetadataProvider(
        "digikey",
        error=AuthFailedError("digikey", status=401, operation="exact-search"),
    )

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id=None,
        provider_names=("lcsc", "digikey"),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc, "digikey": digikey}),
        cad_provider_factory=lambda api: FakeCadProvider(cad_payload()),
    )
    merged = result.to_merged(VERIFIED)

    assert merged.provider_errors == {"digikey": "AUTH_FAILED"}
    assert merged.provider_diagnostics["digikey"].to_dict() == {
        "code": "AUTH_FAILED",
        "operation": "exact-search",
        "status": 401,
    }
    assert merged.verification_status == PARTIAL


def test_separator_difference_from_provider_is_fatal(tmp_path: Path) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc", mpn="A-B12"))

    with pytest.raises(MetadataServiceError):
        resolve_metadata(
            requested_mpn="AB-12",
            requested_manufacturer=None,
            requested_lcsc_id=None,
            provider_names=("lcsc",),
            cad_api=EasyedaApi(),
            cache=MetadataCache(tmp_path),
            provider_factory=make_factory({"lcsc": lcsc}),
            cad_provider_factory=lambda api: FakeCadProvider(cad_payload()),
        )


def test_cad_inferred_mpn_has_easyeda_provenance(tmp_path: Path) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))

    result = resolve_metadata(
        requested_mpn=None,
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=(),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc}),
        cad_provider_factory=lambda api: FakeCadProvider(cad_payload()),
    )
    merged = result.to_merged(VERIFIED)

    assert merged.identity.mpn == "OPA333AIDBVR"
    assert merged.provenance["identity.mpn"][0].provider == "easyeda"
    assert "c_para" in merged.provenance["identity.mpn"][0].source_field
    assert result.cad is not None
    assert result.cad.verification_status == PARTIAL


def test_default_merge_after_cad_network_error_stays_partial(tmp_path: Path) -> None:
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=(),
        cad_api=EasyedaApi(),
        cache=MetadataCache(tmp_path),
        provider_factory=make_factory({"lcsc": lcsc}),
        cad_provider_factory=lambda api: FakeCadProvider(
            error=NetworkError("easyeda", operation="cad-fetch")
        ),
    )

    assert result.to_merged().verification_status == PARTIAL


def test_offline_is_enforced_on_supplied_cad_api(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    api = EasyedaApi(use_cache=False, offline=False)
    observed: list[tuple[bool, bool]] = []

    def cad_factory(received: EasyedaApi) -> FakeCadProvider:
        observed.append((received.offline, received.use_cache))
        return FakeCadProvider(error=NotFoundError("easyeda", operation="cad-fetch"))

    resolve_metadata(
        requested_mpn=None,
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=(),
        cad_api=api,
        cache=cache,
        offline=True,
        provider_factory=make_factory({"lcsc": lcsc}),
        cad_provider_factory=cad_factory,
    )

    assert observed == [(True, True)]


def test_malformed_lcsc_resolver_id_stops_before_cad(tmp_path: Path) -> None:
    malformed = record("lcsc")
    malformed.distributor_part_number = "D123"
    lcsc = FakeMetadataProvider("lcsc", malformed)
    cad = FakeCadProvider(cad_payload())

    with pytest.raises(MetadataServiceError) as exc_info:
        resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer=None,
            requested_lcsc_id=None,
            provider_names=("lcsc",),
            cad_api=EasyedaApi(),
            cache=MetadataCache(tmp_path),
            provider_factory=make_factory({"lcsc": lcsc}),
            cad_provider_factory=lambda api: cad,
        )

    assert exc_info.value.code == "INVALID_RESPONSE"
    assert cad.calls == []


def test_wrong_provider_normalized_cache_is_corrupt_offline(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    request = cache.canonical_request(
        "lcsc",
        "search_exact_mpn",
        mpn="OPA333AIDBVR",
        manufacturer=None,
        options={"provider_context": {}},
    )
    key = cache.get_cache_key("lcsc", request)
    wrong = record("digikey")
    wrong.raw_response_cache_key = key
    cache.write("lcsc", key, {}, wrong.to_dict(), request=request)
    lcsc = FakeMetadataProvider(
        "lcsc", error=AssertionError("corrupt offline cache must not refetch")
    )

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id=None,
        provider_names=("lcsc",),
        cad_api=EasyedaApi(),
        cache=cache,
        offline=True,
        provider_factory=make_factory({"lcsc": lcsc}),
        cad_provider_factory=lambda api: FakeCadProvider(cad_payload()),
    )

    assert result.blocking_error == "CACHE_CORRUPT"
    assert lcsc.exact_calls == 0


def test_wrong_normalized_cache_refetches_online(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    request = cache.canonical_request(
        "lcsc",
        "search_exact_mpn",
        mpn="OPA333AIDBVR",
        manufacturer=None,
        options={"provider_context": {}},
    )
    key = cache.get_cache_key("lcsc", request)
    wrong = record("digikey")
    wrong.raw_response_cache_key = key
    cache.write("lcsc", key, {}, wrong.to_dict(), request=request)
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id=None,
        provider_names=("lcsc",),
        cad_api=EasyedaApi(),
        cache=cache,
        provider_factory=make_factory({"lcsc": lcsc}),
        cad_provider_factory=lambda api: FakeCadProvider(cad_payload()),
    )

    assert result.cad_data is not None
    assert lcsc.exact_calls == 1


def test_public_provider_context_partitions_service_cache(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path)
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    cad = FakeCadProvider(cad_payload())
    usd = FakeMetadataProvider(
        "digikey", record("digikey"), cache_context={"currency": "USD"}
    )
    jpy = FakeMetadataProvider(
        "digikey", record("digikey"), cache_context={"currency": "JPY"}
    )

    for provider in (usd, jpy):
        resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer=None,
            requested_lcsc_id="C30878",
            provider_names=("digikey",),
            cad_api=EasyedaApi(),
            cache=cache,
            provider_factory=make_factory({"lcsc": lcsc, "digikey": provider}),
            cad_provider_factory=lambda api: cad,
        )

    assert usd.exact_calls == 1
    assert jpy.exact_calls == 1


def test_lcsc_id_cache_is_catalogue_pages_and_refresh_does_not_call_cad(
    tmp_path: Path,
) -> None:
    page = {
        "total": 1,
        "results": [
            {
                "lcsc": "C30878",
                "model": "OPA333AIDBVR",
                "brand": "Texas Instruments",
                "description": "catalogue result",
            }
        ],
    }
    catalogue_api = FakeCatalogueApi(page)
    cad = FakeCadProvider(cad_payload())
    cache = MetadataCache(tmp_path)

    for refresh in (False, True):
        result = resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer=None,
            requested_lcsc_id="C30878",
            provider_names=("lcsc",),
            cad_api=EasyedaApi(),
            metadata_api=cast(EasyedaApi, catalogue_api),
            cache=cache,
            refresh_metadata=refresh,
            cad_provider_factory=lambda api: cad,
        )
        assert [record.provider for record in result.distributor_records] == ["lcsc"]

    request = cache.canonical_request(
        "lcsc",
        "get_part_by_distributor_id",
        options={"part_id": "C30878", "provider_context": {}},
    )
    cache_key = cache.get_cache_key("lcsc", request)

    assert catalogue_api.search_calls == [
        ("C30878", 1, 50),
        ("C30878", 1, 50),
    ]
    assert catalogue_api.cad_calls == []
    assert cad.calls == ["C30878", "C30878"]
    assert cache.read_raw("lcsc", cache_key) == {"pages": [page]}


def test_refresh_bypasses_metadata_cache_but_reuses_separate_cad_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cad_api = EasyedaApi(use_cache=True)
    cad_api.cache_dir = tmp_path / "cad"
    cad_api.cache_dir.mkdir()
    cad_cache_path = cad_api._get_cache_path("C30878", "json")
    cad_cache_path.write_text(
        json.dumps({"success": True, "result": cad_payload()}),
        encoding="utf-8",
    )
    original_cad_cache = cad_cache_path.read_bytes()

    def unexpected_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("CAD metadata refresh attempted network access")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_network)

    metadata_cache = MetadataCache(
        tmp_path / "metadata",
        now=lambda: datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
    )
    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    digikey = FakeMetadataProvider("digikey", record("digikey"))
    provider_factory = make_factory({"lcsc": lcsc, "digikey": digikey})

    first = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=("digikey",),
        cad_api=cad_api,
        cache=metadata_cache,
        provider_factory=provider_factory,
    )
    assert digikey.exact_calls == 1
    assert first.distributor_records[0].description is None

    refreshed_record = record("digikey")
    refreshed_record.description = "fresh provider response"
    digikey.record = refreshed_record

    cached = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=("digikey",),
        cad_api=cad_api,
        cache=metadata_cache,
        provider_factory=provider_factory,
    )
    assert digikey.exact_calls == 1
    assert cached.distributor_records[0].description is None

    refreshed = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id="C30878",
        provider_names=("digikey",),
        cad_api=cad_api,
        cache=metadata_cache,
        refresh_metadata=True,
        provider_factory=provider_factory,
    )

    assert digikey.exact_calls == 2
    assert refreshed.distributor_records[0].description == "fresh provider response"
    assert cad_cache_path.read_bytes() == original_cad_cache
    assert cad_api.last_error is None


def test_cache_write_failure_is_safe_service_error(tmp_path: Path) -> None:
    class FailingCache(MetadataCache):
        def write(self, *args: Any, **kwargs: Any) -> tuple[Path, Path]:
            raise OSError("disk failure")

    lcsc = FakeMetadataProvider("lcsc", record("lcsc"))
    with pytest.raises(MetadataServiceError) as exc_info:
        resolve_metadata(
            requested_mpn="OPA333AIDBVR",
            requested_manufacturer=None,
            requested_lcsc_id=None,
            provider_names=("lcsc",),
            cad_api=EasyedaApi(),
            cache=FailingCache(tmp_path),
            provider_factory=make_factory({"lcsc": lcsc}),
            cad_provider_factory=lambda api: FakeCadProvider(cad_payload()),
        )

    assert exc_info.value.code == "CACHE_WRITE_ERROR"
