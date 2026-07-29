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
    DigiKeyProvider,
    InvalidResponseError,
    NotFoundError,
)
from easyeda2kicad_digimou.providers.digikey import (
    DIGIKEY_KEYWORD_SEARCH_URL,
    DIGIKEY_TOKEN_URL,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "providers"
FIXTURE = FIXTURE_DIR / "digikey_keyword_opa333.json"
LM321_FIXTURE = FIXTURE_DIR / "digikey_keyword_lm321.json"


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
) -> DigiKeyProvider:
    queue = [
        _Response({"access_token": "memory-only-token", "expires_in": 3600}),
        _Response(response),
    ]

    def opener(request: urllib.request.Request, timeout: float) -> _Response:
        del timeout
        if requests is not None:
            requests.append(request)
        return queue.pop(0)

    return DigiKeyProvider(
        opener=opener,
        sleeper=lambda _delay: None,
        clock=lambda: 1_700_000_000.0,
        env={
            "DIGIKEY_CLIENT_ID": "public-client-id",
            "DIGIKEY_CLIENT_SECRET": "top-secret-client-secret",
            "DIGIKEY_LOCALE_SITE": "US",
            "DIGIKEY_LOCALE_LANGUAGE": "en",
            "DIGIKEY_LOCALE_CURRENCY": "USD",
        },
    )


def test_official_oauth_and_keyword_requests_are_formed_correctly() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider_with_response(_fixture(), requests=requests)

    record = provider.search_exact_mpn("Texas Instruments", "OPA333AIDBVR")

    assert [request.full_url for request in requests] == [
        DIGIKEY_TOKEN_URL,
        DIGIKEY_KEYWORD_SEARCH_URL,
    ]
    token_form = urllib.parse.parse_qs(cast(bytes, requests[0].data).decode("utf-8"))
    assert token_form == {
        "client_id": ["public-client-id"],
        "client_secret": ["top-secret-client-secret"],
        "grant_type": ["client_credentials"],
    }
    search_body = json.loads(cast(bytes, requests[1].data).decode("utf-8"))
    assert search_body["Keywords"] == "OPA333AIDBVR"
    headers = {key.casefold(): value for key, value in requests[1].header_items()}
    assert headers["authorization"] == "Bearer memory-only-token"
    assert headers["x-digikey-client-id"] == "public-client-id"
    assert headers["x-digikey-locale-currency"] == "USD"
    assert record.mpn == "OPA333AIDBVR"


def test_response_mapping_selects_lexical_variation_and_all_prices() -> None:
    provider = _provider_with_response(_fixture())
    record = provider.search_exact_mpn("Texas Instruments", "OPA333AIDBVR")

    assert record.provider == "digikey"
    assert record.distributor_part_number == "296-19569-1-ND"
    assert record.manufacturer == "Texas Instruments"
    assert record.package == "SOT-23-5"
    assert record.packaging == "Cut Tape (CT)"
    assert record.stock == 1220
    assert record.minimum_order_quantity == 1
    assert record.currency == "USD"
    assert [(item.quantity, item.unit_price) for item in record.price_breaks] == [
        (1, 2.18),
        (10, 1.86),
    ]
    assert record.lifecycle == "Active"
    assert record.retrieved_at == "2023-11-14T22:13:20Z"


def test_sales_changes_do_not_change_selected_dpn_or_symbol_projection() -> None:
    baseline = _provider_with_response(_fixture()).search_exact_mpn(
        "Texas Instruments", "OPA333AIDBVR"
    )
    changed_fixture = copy.deepcopy(_fixture())
    variations = changed_fixture["Products"][0]["ProductVariations"]
    for variation in variations:
        if variation["DigiKeyProductNumber"] == "296-19569-1-ND":
            variation["MinimumOrderQuantity"] = 9000
            variation["QuantityAvailableforPackageType"] = 7
            variation["StandardPricing"] = [
                {"BreakQuantity": 9000, "UnitPrice": 9.99, "Currency": "USD"}
            ]
        else:
            variation["MinimumOrderQuantity"] = 1
            variation["QuantityAvailableforPackageType"] = 99999
            variation["StandardPricing"] = [
                {"BreakQuantity": 1, "UnitPrice": 0.01, "Currency": "USD"}
            ]

    changed = _provider_with_response(changed_fixture).search_exact_mpn(
        "Texas Instruments", "OPA333AIDBVR"
    )

    assert baseline.distributor_part_number == changed.distributor_part_number
    assert changed.distributor_part_number == "296-19569-1-ND"
    assert changed.minimum_order_quantity == 9000
    assert changed.stock == 7
    assert [(item.quantity, item.unit_price) for item in changed.price_breaks] == [
        (9000, 9.99)
    ]
    baseline_fields = build_symbol_fields(merge_records([baseline], mpn="OPA333AIDBVR"))
    changed_fields = build_symbol_fields(merge_records([changed], mpn="OPA333AIDBVR"))
    assert changed_fields == baseline_fields


def test_official_shape_lm321_fixture_preserves_exact_slash_suffix() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider_with_response(_load_fixture(LM321_FIXTURE), requests=requests)
    record = provider.search_exact_mpn("Texas Instruments", "LM321MF/NOPB")

    search_body = json.loads(cast(bytes, requests[1].data).decode("utf-8"))
    assert search_body["Keywords"] == "LM321MF/NOPB"
    assert record.provider == "digikey"
    assert record.mpn == "LM321MF/NOPB"
    assert record.distributor_part_number == "296-LM321MF/NOPBCT-ND"
    assert record.manufacturer == "Texas Instruments"
    assert record.package == "SOT-23-5"
    assert record.packaging == "Cut Tape (CT)"
    assert record.stock == 850
    assert record.minimum_order_quantity == 1
    assert [(item.quantity, item.unit_price) for item in record.price_breaks] == [
        (1, 1.36),
        (10, 1.11),
    ]


def test_near_mpn_is_rejected_after_remote_search() -> None:
    fixture = _fixture()
    fixture["Products"] = [fixture["Products"][1]]
    fixture["ProductsCount"] = 1
    provider = _provider_with_response(fixture)

    with pytest.raises(NotFoundError):
        provider.search_exact_mpn("Texas Instruments", "OPA333AIDBVR")


def test_exact_query_sends_normalized_mpn_but_preserves_record_display() -> None:
    fixture = _fixture()
    fixture["Products"][0]["ManufacturerProductNumber"] = "AB-12 XY"
    requests: List[urllib.request.Request] = []
    provider = _provider_with_response(fixture, requests=requests)

    record = provider.search_exact_mpn("Texas Instruments", "　ＡＢ‐１２   ＸＹ　")

    search_body = json.loads(cast(bytes, requests[1].data).decode("utf-8"))
    assert search_body["Keywords"] == "AB-12 XY"
    assert record.mpn == "AB-12 XY"


def test_empty_normalized_exact_query_stops_before_http() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider_with_response(_fixture(), requests=requests)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "　 ")

    assert requests == []


@pytest.mark.parametrize("lookup", ["exact", "distributor-id"])
def test_products_count_truncation_fails_closed_for_all_lookup_paths(
    lookup: str,
) -> None:
    fixture = _fixture()
    fixture["ProductsCount"] = 3
    provider = _provider_with_response(fixture)

    with pytest.raises(AmbiguousMatchError) as exc_info:
        if lookup == "exact":
            provider.search_exact_mpn("Texas Instruments", "OPA333AIDBVR")
        else:
            provider.get_part_by_distributor_id("296-19569-1-ND")

    assert exc_info.value.operation == "keyword-search-truncated"


def test_products_count_equal_to_returned_candidates_is_not_truncated() -> None:
    fixture = _fixture()
    fixture["ProductsCount"] = 2
    provider = _provider_with_response(fixture)

    assert provider.search_exact_mpn(None, "OPA333AIDBVR").mpn == "OPA333AIDBVR"


@pytest.mark.parametrize("count", [None, -1, "not-a-count", True, 1.5])
def test_products_count_malformed_or_negative_is_invalid(count: object) -> None:
    fixture = _fixture()
    fixture["ProductsCount"] = count
    provider = _provider_with_response(fixture)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


def test_missing_products_count_is_invalid_response() -> None:
    fixture = _fixture()
    fixture.pop("ProductsCount")
    provider = _provider_with_response(fixture)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


@pytest.mark.parametrize("malformed", [None, "not-an-object", 7, []])
def test_malformed_exact_matches_entry_is_invalid(malformed: object) -> None:
    fixture = _fixture()
    fixture["ExactMatches"] = [malformed]
    provider = _provider_with_response(fixture)

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


def test_valid_zero_result_envelope_is_not_found() -> None:
    provider = _provider_with_response(
        {"Products": [], "ExactMatches": [], "ProductsCount": 0}
    )

    with pytest.raises(NotFoundError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


def test_zero_count_without_result_envelope_is_invalid() -> None:
    provider = _provider_with_response({"ProductsCount": 0})

    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


def test_manufacturer_mismatch_is_not_an_exact_match() -> None:
    provider = _provider_with_response(_fixture())
    with pytest.raises(NotFoundError):
        provider.search_exact_mpn("Analog Devices", "OPA333AIDBVR")


def test_same_mpn_from_two_manufacturers_is_ambiguous_without_hint() -> None:
    fixture = _fixture()
    second = copy.deepcopy(fixture["Products"][0])
    second["Manufacturer"] = {"Name": "Other Semiconductor"}
    second["ProductUrl"] = "https://www.digikey.com/example/other"
    fixture["Products"] = [fixture["Products"][0], second]
    provider = _provider_with_response(fixture)

    with pytest.raises(AmbiguousMatchError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


def test_distributor_id_can_select_nonpreferred_reel_variation() -> None:
    provider = _provider_with_response(_fixture())
    record = provider.get_part_by_distributor_id("296-19569-2-ND")
    assert record.distributor_part_number == "296-19569-2-ND"
    assert record.minimum_order_quantity == 2500
    assert record.packaging == "Tape & Reel (TR)"


def test_missing_credentials_fail_before_any_http_request() -> None:
    called = False

    def opener(_request: object, timeout: float) -> _Response:
        nonlocal called
        del timeout
        called = True
        return _Response({})

    provider = DigiKeyProvider(opener=opener, env={})
    with pytest.raises(AuthMissingError) as raised:
        provider.search_exact_mpn(None, "OPA333AIDBVR")
    assert not called
    assert raised.value.code == "AUTH_MISSING"


def test_auth_failure_does_not_leak_secret_or_error_url() -> None:
    secret = "-".join(("top", "secret", "client", "credential"))

    def opener(request: urllib.request.Request, timeout: float) -> _Response:
        del timeout
        raise urllib.error.HTTPError(
            "https://provider.invalid/?secret=%s" % secret,
            401,
            "token rejected",
            cast(Any, {}),
            None,
        )

    provider = DigiKeyProvider(
        opener=opener,
        sleeper=lambda _delay: None,
        env={
            "DIGIKEY_CLIENT_ID": "client",
            "DIGIKEY_CLIENT_SECRET": secret,
        },
    )
    with pytest.raises(AuthFailedError) as raised:
        provider.search_exact_mpn(None, "OPA333AIDBVR")
    assert secret not in str(raised.value)
    assert "provider.invalid" not in str(raised.value)


def test_malformed_product_identity_is_invalid_response() -> None:
    provider = _provider_with_response(
        {"ExactMatches": [], "Products": [{"Description": {}}]}
    )
    with pytest.raises(InvalidResponseError):
        provider.search_exact_mpn(None, "OPA333AIDBVR")


def test_unknown_mpn_candidate_blocks_mixed_exact_success_and_raw_replay() -> None:
    fixture = _fixture()
    exact = copy.deepcopy(fixture["Products"][0])
    fixture["Products"] = [{"Description": {}}, exact]
    fixture["ProductsCount"] = 2
    provider = _provider_with_response(fixture)

    with pytest.raises(InvalidResponseError) as live_error:
        provider.search_exact_mpn(None, "OPA333AIDBVR")
    with pytest.raises(InvalidResponseError) as replay_error:
        provider._normalize_exact_response(copy.deepcopy(fixture), "OPA333AIDBVR")

    assert live_error.value.operation == "exact-normalize"
    assert replay_error.value.operation == "exact-normalize"


def test_raw_exact_candidate_parse_failure_blocks_other_exact_candidate() -> None:
    fixture = _fixture()
    exact = copy.deepcopy(fixture["Products"][0])
    incomplete_exact = {
        "ManufacturerProductNumber": "OPA333AIDBVR",
        "Description": {},
    }
    fixture["Products"] = [incomplete_exact, exact]
    fixture["ProductsCount"] = 2

    with pytest.raises(InvalidResponseError) as error:
        _provider_with_response(fixture).search_exact_mpn(None, "OPA333AIDBVR")

    assert error.value.operation == "exact-normalize"


def test_overflowing_exact_candidate_is_typed_for_live_and_raw_replay() -> None:
    fixture = _fixture()
    for variation in fixture["Products"][0]["ProductVariations"]:
        variation["StandardPricing"] = [
            {"BreakQuantity": 1, "UnitPrice": 10**400, "Currency": "USD"}
        ]
    provider = _provider_with_response(fixture)

    with pytest.raises(InvalidResponseError) as live_error:
        provider.search_exact_mpn(None, "OPA333AIDBVR")
    with pytest.raises(InvalidResponseError) as replay_error:
        provider._normalize_exact_response(copy.deepcopy(fixture), "OPA333AIDBVR")

    assert live_error.value.operation == "exact-normalize"
    assert replay_error.value.operation == "exact-normalize"


def test_proven_mpn_mismatch_can_skip_other_field_parse_failure() -> None:
    fixture = _fixture()
    exact = copy.deepcopy(fixture["Products"][0])
    proven_mismatch = {
        "ManufacturerProductNumber": "OTHER-PART",
        "Manufacturer": 7,
        "Description": {},
    }
    fixture["Products"] = [proven_mismatch, exact]
    fixture["ProductsCount"] = 2

    record = _provider_with_response(fixture).search_exact_mpn(
        "Texas Instruments", "OPA333AIDBVR"
    )

    assert record.mpn == "OPA333AIDBVR"


def test_all_unknown_mpn_candidates_are_invalid_not_not_found() -> None:
    fixture = _fixture()
    fixture["Products"] = [{"Description": {}}]
    fixture["ProductsCount"] = 1

    with pytest.raises(InvalidResponseError) as error:
        _provider_with_response(fixture).search_exact_mpn(None, "OPA333AIDBVR")

    assert error.value.code == "INVALID_RESPONSE"
    assert error.value.operation == "exact-normalize"


def test_access_token_is_reused_in_memory_but_never_cache_key_input() -> None:
    fixture = _fixture()
    queue = [
        _Response({"access_token": "token-that-must-not-leak", "expires_in": 3600}),
        _Response(fixture),
        _Response(fixture),
    ]
    requests: List[urllib.request.Request] = []

    def opener(request: urllib.request.Request, timeout: float) -> _Response:
        del timeout
        requests.append(request)
        return queue.pop(0)

    provider = DigiKeyProvider(
        opener=opener,
        sleeper=lambda _delay: None,
        clock=lambda: 1_700_000_000.0,
        env={
            "DIGIKEY_CLIENT_ID": "client",
            "DIGIKEY_CLIENT_SECRET": "secret",
        },
    )
    provider.search_exact_mpn(None, "OPA333AIDBVR")
    provider.search_exact_mpn(None, "OPA333AIDBVR")

    assert len(requests) == 3
    key = provider.get_cache_key(
        {
            "operation": "search",
            "mpn": "OPA333AIDBVR",
            "access_token": "token-that-must-not-leak",
        }
    )
    assert "token-that-must-not-leak" not in key


def test_cache_context_varies_by_public_locale_and_excludes_credentials() -> None:
    common = {
        "DIGIKEY_CLIENT_ID": "client-one",
        "DIGIKEY_CLIENT_SECRET": "credential-one",
        "DIGIKEY_LOCALE_SITE": "US",
        "DIGIKEY_LOCALE_LANGUAGE": "en",
    }
    usd = DigiKeyProvider(env={**common, "DIGIKEY_LOCALE_CURRENCY": "USD"})
    eur = DigiKeyProvider(env={**common, "DIGIKEY_LOCALE_CURRENCY": "EUR"})

    assert usd.get_cache_context() == {
        "site": "US",
        "language": "en",
        "currency": "USD",
    }
    assert usd.get_cache_key({"mpn": "OPA333AIDBVR"}) != eur.get_cache_key(
        {"mpn": "OPA333AIDBVR"}
    )
    assert "client-one" not in str(usd.get_cache_context())
    assert "credential-one" not in str(usd.get_cache_context())


def test_keyword_search_retries_rate_limit_then_succeeds() -> None:
    requests: List[urllib.request.Request] = []
    delays: List[float] = []
    queue = [
        _Response({"access_token": "memory-only-token", "expires_in": 3600}),
        _Response({}, status=429, headers={"Retry-After": "2"}),
        _Response(_fixture()),
    ]

    def opener(request: urllib.request.Request, timeout: float) -> _Response:
        del timeout
        requests.append(request)
        return queue.pop(0)

    provider = DigiKeyProvider(
        opener=opener,
        sleeper=delays.append,
        clock=lambda: 1_700_000_000.0,
        env={
            "DIGIKEY_CLIENT_ID": "client",
            "DIGIKEY_CLIENT_SECRET": "credential",
        },
    )
    record = provider.search_exact_mpn(None, "OPA333AIDBVR")

    assert record.mpn == "OPA333AIDBVR"
    assert len(requests) == 3
    assert delays == [2.0]
