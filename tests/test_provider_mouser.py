from __future__ import annotations

# Global imports
import copy
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, cast

import pytest

from easyeda2kicad_digimou.metadata.merge import merge_records
from easyeda2kicad_digimou.metadata.symbol_fields import build_symbol_fields
from easyeda2kicad_digimou.providers import (
    AmbiguousMatchError,
    AuthFailedError,
    AuthMissingError,
    InvalidResponseError,
    MouserProvider,
    NotFoundError,
)
from easyeda2kicad_digimou.providers.mouser import MOUSER_SEARCH_URL

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "providers"
FIXTURE = FIXTURE_DIR / "mouser_search_lm321.json"
OPA333_FIXTURE = FIXTURE_DIR / "mouser_search_opa333.json"


class _Response(io.BytesIO):
    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        status: int = 200,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = status
        self.headers = dict(headers or {})


def _load_fixture(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    assert isinstance(value, dict)
    return value


def _fixture() -> Dict[str, Any]:
    return _load_fixture(FIXTURE)


def _provider_with_response(
    response: Mapping[str, Any],
    *,
    requests: Optional[List[urllib.request.Request]] = None,
) -> MouserProvider:
    def opener(request: urllib.request.Request, timeout: float) -> _Response:
        del timeout
        if requests is not None:
            requests.append(request)
        return _Response(response)

    return MouserProvider(
        opener=opener,
        sleeper=lambda _delay: None,
        clock=lambda: 1_700_000_000.0,
        env={"MOUSER_API_KEY": "mouser-super-secret"},
    )


def test_official_part_and_manufacturer_request_schema() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider_with_response(_fixture(), requests=requests)
    record = provider.search_exact_mpn("Texas Instruments", "LM321MF/NOPB")

    assert len(requests) == 1
    parsed_url = urllib.parse.urlsplit(requests[0].full_url)
    assert (
        "%s://%s%s"
        % (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
        )
        == MOUSER_SEARCH_URL
    )
    assert urllib.parse.parse_qs(parsed_url.query) == {
        "apiKey": ["mouser-super-secret"]
    }
    body = json.loads(cast(bytes, requests[0].data).decode("utf-8"))
    assert body == {
        "SearchByPartMfrNameRequest": {
            "manufacturerName": "Texas Instruments",
            "mouserPartNumber": "LM321MF/NOPB",
            "partSearchOptions": "Exact",
        }
    }
    assert record.mpn == "LM321MF/NOPB"


def test_response_mapping_preserves_slash_suffix_prices_and_inventory() -> None:
    provider = _provider_with_response(_fixture())
    record = provider.search_exact_mpn("Texas Instruments", "LM321MF/NOPB")

    assert record.provider == "mouser"
    assert record.distributor_part_number == "926-LM321MF/NOPB"
    assert record.manufacturer == "Texas Instruments"
    assert record.mpn == "LM321MF/NOPB"
    assert record.package == "SOT-23-5"
    assert record.packaging == "Cut Tape"
    assert record.stock == 1824
    assert record.minimum_order_quantity == 1
    assert record.currency == "USD"
    assert [(item.quantity, item.unit_price) for item in record.price_breaks] == [
        (1, 1.42),
        (10, 1.17),
    ]
    assert record.lifecycle == "Active"
    assert record.retrieved_at == "2023-11-14T22:13:20Z"


def test_official_shape_opa333_fixture_maps_exact_part() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider_with_response(_load_fixture(OPA333_FIXTURE), requests=requests)
    record = provider.search_exact_mpn("Texas Instruments", "OPA333AIDBVR")

    search_body = json.loads(cast(bytes, requests[0].data).decode("utf-8"))
    assert search_body["SearchByPartMfrNameRequest"]["mouserPartNumber"] == (
        "OPA333AIDBVR"
    )
    assert record.provider == "mouser"
    assert record.mpn == "OPA333AIDBVR"
    assert record.distributor_part_number == "595-OPA333AIDBVR"
    assert record.manufacturer == "Texas Instruments"
    assert record.package == "SOT-23-5"
    assert record.packaging == "Cut Tape"
    assert record.stock == 950
    assert record.minimum_order_quantity == 1
    assert [(item.quantity, item.unit_price) for item in record.price_breaks] == [
        (1, 2.21),
        (10, 1.88),
    ]


def test_near_suffix_match_is_rejected_locally() -> None:
    fixture = _fixture()
    fixture["SearchResults"]["Parts"] = [fixture["SearchResults"]["Parts"][1]]
    fixture["SearchResults"]["NumberOfResult"] = 1
    provider = _provider_with_response(fixture)
    with pytest.raises(NotFoundError):
        provider.search_exact_mpn("Texas Instruments", "LM321MF/NOPB")


def test_exact_query_sends_normalized_mpn_but_preserves_record_display() -> None:
    fixture = _fixture()
    fixture["SearchResults"]["Parts"][0]["ManufacturerPartNumber"] = "AB-12 XY"
    requests: List[urllib.request.Request] = []
    provider = _provider_with_response(fixture, requests=requests)

    record = provider.search_exact_mpn("Texas Instruments", "　ＡＢ‐１２   ＸＹ　")

    body = json.loads(cast(bytes, requests[0].data).decode("utf-8"))
    assert body["SearchByPartMfrNameRequest"]["mouserPartNumber"] == "AB-12 XY"
    assert record.mpn == "AB-12 XY"


def test_empty_normalized_exact_query_stops_before_http() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider_with_response(_fixture(), requests=requests)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "　 ")

    assert requests == []


@pytest.mark.parametrize("lookup", ["exact", "distributor-id"])
def test_result_count_truncation_fails_closed_for_all_lookup_paths(
    lookup: str,
) -> None:
    fixture = _fixture()
    fixture["SearchResults"]["NumberOfResult"] = 3
    provider = _provider_with_response(fixture)

    with pytest.raises(AmbiguousMatchError) as exc_info:
        if lookup == "exact":
            provider.search_exact_mpn("Texas Instruments", "LM321MF/NOPB")
        else:
            provider.get_part_by_distributor_id("926-LM321MF/NOPB")

    assert exc_info.value.operation == "part-search-truncated"


def test_result_count_equal_to_returned_parts_is_not_truncated() -> None:
    fixture = _fixture()
    fixture["SearchResults"]["NumberOfResult"] = 2
    provider = _provider_with_response(fixture)

    assert provider.search_exact_mpn(None, "LM321MF/NOPB").mpn == "LM321MF/NOPB"


@pytest.mark.parametrize("count", [None, -1, "not-a-count", True, 1.5])
def test_result_count_malformed_or_negative_is_invalid(count: object) -> None:
    fixture = _fixture()
    fixture["SearchResults"]["NumberOfResult"] = count
    provider = _provider_with_response(fixture)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "LM321MF/NOPB")


def test_missing_result_count_is_invalid_response() -> None:
    fixture = _fixture()
    fixture["SearchResults"].pop("NumberOfResult")
    provider = _provider_with_response(fixture)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "LM321MF/NOPB")


@pytest.mark.parametrize("parts_state", ["missing", "null"])
def test_zero_result_requires_present_list_valued_parts(parts_state: str) -> None:
    fixture: Dict[str, Any] = {"SearchResults": {"NumberOfResult": 0, "Parts": []}}
    if parts_state == "missing":
        fixture["SearchResults"].pop("Parts")
    else:
        fixture["SearchResults"]["Parts"] = None

    with pytest.raises(InvalidResponseError):
        _provider_with_response(fixture).search_exact_mpn(None, "LM321MF/NOPB")


def test_unknown_mpn_candidate_blocks_mixed_exact_success_and_raw_replay() -> None:
    fixture = _fixture()
    exact = copy.deepcopy(fixture["SearchResults"]["Parts"][0])
    fixture["SearchResults"]["Parts"] = [{"Description": "unknown"}, exact]
    fixture["SearchResults"]["NumberOfResult"] = 2
    provider = _provider_with_response(fixture)

    with pytest.raises(InvalidResponseError) as live_error:
        provider.search_exact_mpn(None, "LM321MF/NOPB")
    with pytest.raises(InvalidResponseError) as replay_error:
        provider._normalize_exact_response(copy.deepcopy(fixture), "LM321MF/NOPB")

    assert live_error.value.operation == "exact-normalize"
    assert replay_error.value.operation == "exact-normalize"


def test_raw_exact_candidate_parse_failure_blocks_other_exact_candidate() -> None:
    fixture = _fixture()
    exact = copy.deepcopy(fixture["SearchResults"]["Parts"][0])
    incomplete_exact = {
        "ManufacturerPartNumber": "LM321MF/NOPB",
        "Description": "missing manufacturer",
    }
    fixture["SearchResults"]["Parts"] = [incomplete_exact, exact]
    fixture["SearchResults"]["NumberOfResult"] = 2

    with pytest.raises(InvalidResponseError) as error:
        _provider_with_response(fixture).search_exact_mpn(None, "LM321MF/NOPB")

    assert error.value.operation == "exact-normalize"


def test_overflowing_exact_candidate_is_typed_for_live_and_raw_replay() -> None:
    fixture = _fixture()
    fixture["SearchResults"]["Parts"][0]["PriceBreaks"][0]["Price"] = 10**400
    provider = _provider_with_response(fixture)

    with pytest.raises(InvalidResponseError) as live_error:
        provider.search_exact_mpn(None, "LM321MF/NOPB")
    with pytest.raises(InvalidResponseError) as replay_error:
        provider._normalize_exact_response(copy.deepcopy(fixture), "LM321MF/NOPB")

    assert live_error.value.operation == "exact-normalize"
    assert replay_error.value.operation == "exact-normalize"


def test_proven_mpn_mismatch_can_skip_other_field_parse_failure() -> None:
    fixture = _fixture()
    exact = copy.deepcopy(fixture["SearchResults"]["Parts"][0])
    proven_mismatch = {
        "ManufacturerPartNumber": "OTHER-PART",
        "Manufacturer": 7,
        "Description": "missing manufacturer",
    }
    fixture["SearchResults"]["Parts"] = [proven_mismatch, exact]
    fixture["SearchResults"]["NumberOfResult"] = 2

    record = _provider_with_response(fixture).search_exact_mpn(
        "Texas Instruments", "LM321MF/NOPB"
    )

    assert record.mpn == "LM321MF/NOPB"


def test_all_unknown_mpn_candidates_are_invalid_not_not_found() -> None:
    fixture = _fixture()
    fixture["SearchResults"]["Parts"] = [{"Description": "unknown"}]
    fixture["SearchResults"]["NumberOfResult"] = 1

    with pytest.raises(InvalidResponseError) as error:
        _provider_with_response(fixture).search_exact_mpn(None, "LM321MF/NOPB")

    assert error.value.code == "INVALID_RESPONSE"
    assert error.value.operation == "exact-normalize"


def test_manufacturer_mismatch_is_rejected_locally() -> None:
    provider = _provider_with_response(_fixture())
    with pytest.raises(NotFoundError):
        provider.search_exact_mpn("National Semiconductor", "LM321MF/NOPB")


def test_omitted_manufacturer_uses_empty_official_field_and_detects_ambiguity() -> None:
    fixture = _fixture()
    first = fixture["SearchResults"]["Parts"][0]
    second = dict(first)
    second["Manufacturer"] = "Other Semiconductor"
    second["MouserPartNumber"] = "999-LM321MF/NOPB"
    fixture["SearchResults"]["Parts"] = [first, second]
    requests: List[urllib.request.Request] = []
    provider = _provider_with_response(fixture, requests=requests)

    with pytest.raises(AmbiguousMatchError):
        provider.search_exact_mpn(None, "LM321MF/NOPB")
    body = json.loads(cast(bytes, requests[0].data).decode("utf-8"))
    assert body["SearchByPartMfrNameRequest"]["manufacturerName"] == ""


def test_sales_changes_do_not_change_selected_mouser_part_or_symbol() -> None:
    fixture = _fixture()
    first = fixture["SearchResults"]["Parts"][0]
    second = copy.deepcopy(first)
    first["MouserPartNumber"] = "926-LM321-A"
    first["Min"] = "9000"
    first["AvailabilityInStock"] = 7
    second["MouserPartNumber"] = "926-LM321-B"
    second["Min"] = "1"
    second["AvailabilityInStock"] = 99999
    fixture["SearchResults"]["Parts"] = [first, second]
    fixture["SearchResults"]["NumberOfResult"] = 2
    baseline = _provider_with_response(fixture).search_exact_mpn(
        "Texas Instruments", "LM321MF/NOPB"
    )

    changed_fixture = copy.deepcopy(fixture)
    changed_first, changed_second = changed_fixture["SearchResults"]["Parts"]
    changed_first["Min"] = "1"
    changed_first["AvailabilityInStock"] = 99999
    changed_second["Min"] = "9000"
    changed_second["AvailabilityInStock"] = 7
    changed = _provider_with_response(changed_fixture).search_exact_mpn(
        "Texas Instruments", "LM321MF/NOPB"
    )

    assert baseline.distributor_part_number == "926-LM321-A"
    assert changed.distributor_part_number == baseline.distributor_part_number
    baseline_fields = build_symbol_fields(merge_records([baseline], mpn="LM321MF/NOPB"))
    changed_fields = build_symbol_fields(merge_records([changed], mpn="LM321MF/NOPB"))
    assert changed_fields == baseline_fields


def test_get_by_mouser_number_requires_exact_distributor_id() -> None:
    provider = _provider_with_response(_fixture())
    record = provider.get_part_by_distributor_id("926-LM321MF/NOPB")
    assert record.mpn == "LM321MF/NOPB"


def test_missing_key_stops_before_http() -> None:
    provider = MouserProvider(env={}, sleeper=lambda _delay: None)
    with pytest.raises(AuthMissingError):
        provider.search_exact_mpn(None, "LM321MF/NOPB")


def test_secret_bearing_url_is_never_exposed_by_http_error() -> None:
    secret = "-".join(("mouser", "super", "secret"))

    def opener(request: urllib.request.Request, timeout: float) -> _Response:
        del timeout
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "bad API key %s" % secret,
            cast(Any, {}),
            None,
        )

    provider = MouserProvider(
        opener=opener,
        sleeper=lambda _delay: None,
        env={"MOUSER_API_KEY": secret},
    )
    with pytest.raises(AuthFailedError) as raised:
        provider.search_exact_mpn(None, "LM321MF/NOPB")
    assert secret not in str(raised.value)
    assert "apiKey" not in str(raised.value)
    assert MOUSER_SEARCH_URL not in str(raised.value)


def test_retryable_server_error_is_retried_then_succeeds() -> None:
    responses = [_Response({}, status=503), _Response(_fixture())]
    delays: List[float] = []

    def opener(_request: urllib.request.Request, timeout: float) -> _Response:
        del timeout
        return responses.pop(0)

    provider = MouserProvider(
        opener=opener,
        sleeper=delays.append,
        env={"MOUSER_API_KEY": "secret"},
    )
    record = provider.search_exact_mpn("Texas Instruments", "LM321MF/NOPB")
    assert record.mpn == "LM321MF/NOPB"
    assert delays == [0.5]


def test_api_error_envelope_is_invalid_without_echoing_message() -> None:
    provider = _provider_with_response(
        {
            "Errors": [
                {
                    "Id": 1,
                    "Message": "rejected secret mouser-super-secret",
                }
            ]
        }
    )
    with pytest.raises(InvalidResponseError) as raised:
        provider.search_exact_mpn(None, "LM321MF/NOPB")
    assert "mouser-super-secret" not in str(raised.value)


def test_api_key_error_envelope_maps_to_safe_auth_failure() -> None:
    provider = _provider_with_response(
        {"Errors": [{"Id": 1, "Message": "Invalid API Key mouser-super-secret"}]}
    )
    with pytest.raises(AuthFailedError) as raised:
        provider.search_exact_mpn(None, "LM321MF/NOPB")
    assert raised.value.code == "AUTH_FAILED"
    assert "mouser-super-secret" not in str(raised.value)
