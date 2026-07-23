from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, cast

import pytest

from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.metadata.service import create_metadata_provider
from easyeda2kicad.providers import (
    AmbiguousMatchError,
    CacheCorruptError,
    EasyedaProvider,
    InvalidResponseError,
    LcscProvider,
    NetworkError,
    NotFoundError,
    OfflineCacheMissError,
)
from easyeda2kicad.providers.lcsc_client import JlcpcbCatalogueClient


def _search_item(
    lcsc: str,
    mpn: str,
    manufacturer: str = "Texas Instruments",
) -> Dict[str, Any]:
    return {
        "lcsc": lcsc,
        "model": mpn,
        "brand": manufacturer,
        "package": "SOT-23-5",
        "stock": 123,
        "min_qty": 1,
        "reel_qty": 3000,
        "description": "test component",
        "url": "https://www.lcsc.com/product-detail/%s.html" % lcsc,
        "datasheet": "https://example.test/%s.pdf" % mpn.replace("/", "-"),
        "price_breaks": [
            {"qty": 1, "price": 0.75},
            {"qty": 10, "price": 0.60},
        ],
    }


def test_lcsc_factory_uses_dedicated_catalogue_client_not_cad_api() -> None:
    cad_capable_api = EasyedaApi(use_cache=True)

    provider = create_metadata_provider("lcsc", cad_capable_api)

    assert isinstance(provider, LcscProvider)
    assert isinstance(provider.api, JlcpcbCatalogueClient)
    assert cast(object, provider.api) is not cast(object, cad_capable_api)


class _FakeApi:
    def __init__(
        self,
        *,
        pages: Optional[Mapping[int, Mapping[str, Any]]] = None,
        cad: Optional[Mapping[str, Any]] = None,
        last_error: Optional[str] = None,
        offline: bool = False,
    ) -> None:
        self.pages = dict(pages or {})
        self.cad = dict(cad or {})
        self.last_error = last_error
        self.offline = offline
        self.search_calls: List[tuple[str, int, int, Optional[str]]] = []
        self.cad_calls: List[str] = []

    def search_jlcpcb_components(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 10,
        part_type: Optional[str] = None,
    ) -> Mapping[str, Any]:
        self.search_calls.append((keyword, page, page_size, part_type))
        return self.pages.get(page, {"total": 0, "results": []})

    def get_cad_data_of_component(self, lcsc_id: str) -> Mapping[str, Any]:
        self.cad_calls.append(lcsc_id)
        return self.cad


def test_lcsc_search_maps_existing_jlcpcb_adapter_fields() -> None:
    api = _FakeApi(
        pages={1: {"total": 1, "results": [_search_item("C30878", "OPA333AIDBVR")]}}
    )
    provider = LcscProvider(
        api=cast(Any, api),
        clock=lambda: 1_700_000_000.0,
        sleeper=lambda _delay: None,
    )
    record = provider.search_exact_mpn("Texas Instruments", "OPA333AIDBVR")

    assert api.search_calls == [("OPA333AIDBVR", 1, 50, None)]
    assert record.provider == "lcsc"
    assert record.distributor_part_number == "C30878"
    assert record.mpn == "OPA333AIDBVR"
    assert record.package == "SOT-23-5"
    assert record.stock == 123
    assert record.minimum_order_quantity == 1
    assert record.packaging == "Reel"
    assert [(item.quantity, item.unit_price) for item in record.price_breaks] == [
        (1, 0.75),
        (10, 0.60),
    ]


def test_lcsc_exact_query_sends_normalized_mpn_and_preserves_record_display() -> None:
    api = _FakeApi(
        pages={1: {"total": 1, "results": [_search_item("C12345", "AB-12 XY")]}}
    )
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)

    record = provider.search_exact_mpn(None, "　ＡＢ‐１２   ＸＹ　")

    assert api.search_calls == [("AB-12 XY", 1, 50, None)]
    assert record.mpn == "AB-12 XY"


def test_lcsc_prefers_english_manufacturer_from_same_catalogue_record() -> None:
    item = _search_item("C30878", "OPA333AIDBVR", manufacturer="TI(德州仪器)")
    item["componentBrandEn"] = "Texas Instruments"
    api = _FakeApi(pages={1: {"total": 1, "results": [item]}})
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)

    record = provider.search_exact_mpn(None, "OPA333AIDBVR")

    assert record.manufacturer == "Texas Instruments"


def test_lcsc_empty_normalized_exact_query_stops_before_search() -> None:
    api = _FakeApi()
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "　 ")

    assert api.search_calls == []


def test_lcsc_unknown_mpn_blocks_mixed_exact_success_and_raw_replay() -> None:
    response = {
        "total": 2,
        "results": [
            {"description": "unknown"},
            _search_item("C30878", "OPA333AIDBVR"),
        ],
    }
    api = _FakeApi(pages={1: response})
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)

    with pytest.raises(InvalidResponseError) as live_error:
        provider.search_exact_mpn(None, "OPA333AIDBVR")
    with pytest.raises(InvalidResponseError) as replay_error:
        provider._normalize_exact_response(response, "OPA333AIDBVR")

    assert live_error.value.operation == "exact-normalize"
    assert replay_error.value.operation == "exact-normalize"


def test_lcsc_raw_exact_parse_failure_blocks_other_exact_candidate() -> None:
    response = {
        "total": 2,
        "results": [
            {"model": "OPA333AIDBVR", "description": "missing identity"},
            _search_item("C30878", "OPA333AIDBVR"),
        ],
    }
    provider = LcscProvider(
        api=cast(Any, _FakeApi(pages={1: response})),
        sleeper=lambda _delay: None,
    )

    with pytest.raises(InvalidResponseError) as error:
        provider.search_exact_mpn(None, "OPA333AIDBVR")

    assert error.value.operation == "exact-normalize"


def test_lcsc_overflowing_exact_candidate_is_typed_for_live_and_raw_replay() -> None:
    item = _search_item("C30878", "OPA333AIDBVR")
    item["price_breaks"][0]["price"] = 10**400
    response = {"total": 1, "results": [item]}
    provider = LcscProvider(
        api=cast(Any, _FakeApi(pages={1: response})),
        sleeper=lambda _delay: None,
    )

    with pytest.raises(InvalidResponseError) as live_error:
        provider.search_exact_mpn(None, "OPA333AIDBVR")
    with pytest.raises(InvalidResponseError) as replay_error:
        provider._normalize_exact_response(response, "OPA333AIDBVR")

    assert live_error.value.operation == "exact-normalize"
    assert replay_error.value.operation == "exact-normalize"


def test_lcsc_proven_mpn_mismatch_can_skip_other_field_parse_failure() -> None:
    response = {
        "total": 2,
        "results": [
            {
                "model": "OTHER-PART",
                "brand": 7,
                "description": "invalid manufacturer",
            },
            _search_item("C30878", "OPA333AIDBVR"),
        ],
    }
    provider = LcscProvider(
        api=cast(Any, _FakeApi(pages={1: response})),
        sleeper=lambda _delay: None,
    )

    record = provider.search_exact_mpn("Texas Instruments", "OPA333AIDBVR")

    assert record.distributor_part_number == "C30878"


def test_lcsc_all_unknown_mpn_candidates_are_invalid_not_not_found() -> None:
    response = {"total": 1, "results": [{"description": "unknown"}]}
    provider = LcscProvider(
        api=cast(Any, _FakeApi(pages={1: response})),
        sleeper=lambda _delay: None,
    )

    with pytest.raises(InvalidResponseError) as error:
        provider.search_exact_mpn(None, "OPA333AIDBVR")

    assert error.value.code == "INVALID_RESPONSE"
    assert error.value.operation == "exact-normalize"


def test_lcsc_search_pages_before_proving_unique_exact_identity() -> None:
    api = _FakeApi(
        pages={
            1: {
                "total": 51,
                "results": [
                    _search_item("C%d" % index, "SIMILAR-%d" % index)
                    for index in range(1, 51)
                ],
            },
            2: {
                "total": 51,
                "results": [_search_item("C30878", "OPA333AIDBVR")],
            },
        }
    )
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)
    record = provider.search_exact_mpn(None, "OPA333AIDBVR")

    assert record.distributor_part_number == "C30878"
    assert [call[1] for call in api.search_calls] == [1, 2]


@pytest.mark.parametrize("total", [True, 1.5, "1 result", -1])
def test_lcsc_search_rejects_non_strict_result_totals(total: object) -> None:
    api = _FakeApi(
        pages={
            1: {
                "total": total,
                "results": [_search_item("C30878", "OPA333AIDBVR")],
            }
        }
    )
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


def test_lcsc_search_accepts_canonical_integer_string_total() -> None:
    api = _FakeApi(
        pages={
            1: {
                "total": "1",
                "results": [_search_item("C30878", "OPA333AIDBVR")],
            }
        }
    )
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)

    assert provider.search_exact_mpn(None, "OPA333AIDBVR").mpn == "OPA333AIDBVR"


def test_lcsc_search_rejects_conflicting_totals_within_one_page() -> None:
    api = _FakeApi(
        pages={
            1: {
                "total": 1,
                "data": {"componentPageInfo": {"total": 2}},
                "results": [_search_item("C30878", "OPA333AIDBVR")],
            }
        }
    )
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


@pytest.mark.parametrize("second_page", [{"total": 52}, {}])
def test_lcsc_search_rejects_changed_or_missing_total_on_later_page(
    second_page: dict[str, object],
) -> None:
    page_two = {
        **second_page,
        "results": [_search_item("C30878", "OPA333AIDBVR")],
    }
    api = _FakeApi(
        pages={
            1: {
                "total": 51,
                "results": [
                    _search_item("C%d" % index, "SIMILAR-%d" % index)
                    for index in range(1, 51)
                ],
            },
            2: page_two,
        }
    )
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


def test_lcsc_multiple_exact_ids_are_ambiguous_not_preferred() -> None:
    api = _FakeApi(
        pages={
            1: {
                "total": 2,
                "results": [
                    _search_item("C30878", "OPA333AIDBVR"),
                    _search_item("C99999", "OPA333AIDBVR"),
                ],
            }
        }
    )
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)
    with pytest.raises(AmbiguousMatchError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


def test_lcsc_truncated_search_never_claims_unique_result() -> None:
    api = _FakeApi(
        pages={
            1: {
                "total": 501,
                "results": [_search_item("C30878", "OPA333AIDBVR")],
            }
        }
    )
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)
    with pytest.raises(AmbiguousMatchError) as raised:
        provider.search_exact_mpn(None, "OPA333AIDBVR")
    assert raised.value.operation == "search-truncated"
    assert len(api.search_calls) == 1


def test_lcsc_distributor_id_uses_catalogue_only() -> None:
    cad = {
        "uuid": "easyeda-uuid",
        "title": "marketing-title-must-not-be-mpn",
        "lcsc": {"number": "C30878"},
        "dataStr": {
            "head": {
                "c_para": {
                    "Manufacturer": "Texas Instruments",
                    "Manufacturer Part": "OPA333AIDBVR",
                    "Package": "SOT-23-5",
                    "Datasheet": "https://www.ti.com/opa333.pdf",
                }
            }
        },
    }
    page = {"total": 1, "results": [_search_item("C30878", "OPA333AIDBVR")]}
    api = _FakeApi(cad=cad, pages={1: page})
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)
    record = provider.get_part_by_distributor_id("C30878")

    assert record.mpn == "OPA333AIDBVR"
    assert record.manufacturer == "Texas Instruments"
    assert api.search_calls == [("C30878", 1, 50, None)]
    assert api.cad_calls == []
    assert provider.last_raw_response == {"pages": [page]}


def test_lcsc_catalogue_identity_is_independent_of_cad_absence() -> None:
    api = _FakeApi(
        last_error="not_found",
        pages={1: {"total": 1, "results": [_search_item("C30878", "OPA333AIDBVR")]}},
    )
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)
    record = provider.get_part_by_distributor_id("C30878")

    assert record.mpn == "OPA333AIDBVR"
    assert record.distributor_part_number == "C30878"
    assert api.cad_calls == []
    assert api.search_calls == [("C30878", 1, 50, None)]


def test_lcsc_distributor_id_requires_canonical_id() -> None:
    api = _FakeApi()
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)

    with pytest.raises(InvalidResponseError):
        provider.get_part_by_distributor_id("c30878")

    assert api.cad_calls == []
    assert api.search_calls == []


def test_lcsc_offline_search_is_distinct_from_not_found() -> None:
    api = _FakeApi(last_error="offline_cache_miss", offline=True)
    provider = LcscProvider(api=cast(Any, api), sleeper=lambda _delay: None)
    with pytest.raises(OfflineCacheMissError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


def test_easyeda_success_returns_raw_data_and_partial_cad_record() -> None:
    cad = {
        "uuid": "easyeda-uuid",
        "title": "OPA333",
        "lcsc": {"number": "C30878"},
        "dataStr": {"head": {"c_para": {"Package": "SOT-23-5"}}},
        "packageDetail": {
            "title": "SOT-23-5",
            "dataStr": {"head": {"c_para": {"3D Model": "SOT-23-5 model"}}},
        },
    }
    api = _FakeApi(cad=cad)
    provider = EasyedaProvider(api=cast(Any, api))
    record, raw = provider.get_cad_data("C30878")

    assert raw == cad
    assert record.source == "easyeda"
    assert record.lcsc_part_number == "C30878"
    assert record.easyeda_component_id == "easyeda-uuid"
    assert record.symbol_name == "OPA333"
    assert record.footprint_name == "SOT-23-5"
    assert record.model_3d == "SOT-23-5 model"
    assert record.verification_status == "PARTIAL"


@pytest.mark.parametrize(
    ("last_error", "expected"),
    [
        ("not_found", NotFoundError),
        ("network_error", NetworkError),
        ("invalid_response", InvalidResponseError),
        ("cache_corrupt", CacheCorruptError),
        ("offline_cache_miss", OfflineCacheMissError),
    ],
)
def test_easyeda_maps_api_diagnostics_to_provider_errors(
    last_error: str, expected: type
) -> None:
    api = _FakeApi(last_error=last_error)
    provider = EasyedaProvider(api=cast(Any, api))
    with pytest.raises(expected):
        provider.get_cad_data("C00000")


def test_easyeda_provider_maps_semantic_offline_cache_failure_to_corrupt(
    tmp_path: Path,
) -> None:
    api = EasyedaApi(use_cache=True, offline=True)
    api.cache_dir = tmp_path
    api._get_cache_path("C-BAD-CACHE", "json").write_text(
        json.dumps({"success": True, "result": {}}), encoding="utf-8"
    )
    provider = EasyedaProvider(api=api)

    with pytest.raises(CacheCorruptError):
        provider.get_cad_data("C-BAD-CACHE")


def test_easyeda_provider_maps_semantic_network_failure_to_invalid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = EasyedaApi(use_cache=False)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: io.BytesIO(b'{"success":true,"result":{}}'),
    )
    provider = EasyedaProvider(api=api)

    with pytest.raises(InvalidResponseError):
        provider.get_cad_data("C-BAD-NETWORK")
