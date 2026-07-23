from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any, List, Mapping, Optional

import pytest

from easyeda2kicad.metadata.models import DistributorRecord, normalize_mpn
from easyeda2kicad.providers.base import (
    AmbiguousMatchError,
    BaseMetadataProvider,
    NetworkError,
    NotFoundError,
    ProviderError,
    RateLimitedError,
    canonical_request,
    optional_float,
    optional_int,
)


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


class _Provider(BaseMetadataProvider):
    name = "test-provider"

    def request(self) -> Mapping[str, Any]:
        request = urllib.request.Request("https://provider.example/search")
        return self._request_json(request, operation="search")


def _record(manufacturer: str, mpn: str, part: str) -> DistributorRecord:
    return DistributorRecord(
        provider="test-provider",
        manufacturer=manufacturer,
        mpn=mpn,
        distributor_part_number=part,
        minimum_order_quantity=1,
    )


def test_exact_normalization_preserves_separator_positions() -> None:
    assert normalize_mpn(" AB‑12 / xy ") == "AB-12 / XY"
    assert normalize_mpn("AB-12") != normalize_mpn("A-B12")
    assert normalize_mpn("LM321MF/NOPB") == "LM321MF/NOPB"


def test_optional_numeric_parsers_reject_nonfinite_and_overflowing_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        optional_int(float("inf"))
    with pytest.raises(ValueError, match="finite"):
        optional_float(float("nan"))
    with pytest.raises(ValueError, match="range"):
        optional_float(10**400)
    with pytest.raises(ValueError, match="finite"):
        optional_float("9" * 400)


def test_exact_match_rejects_false_separator_collision() -> None:
    provider = _Provider(sleeper=lambda _delay: None)
    with pytest.raises(NotFoundError):
        provider.validate_exact_match(
            [_record("Acme", "A-B12", "one")], "Acme", "AB-12"
        )


def test_exact_match_detects_multiple_manufacturers_without_hint() -> None:
    provider = _Provider(sleeper=lambda _delay: None)
    candidates = [
        _record("Acme", "ZX-1", "one"),
        _record("Other", "ZX-1", "two"),
    ]
    with pytest.raises(AmbiguousMatchError):
        provider.validate_exact_match(candidates, None, "ZX-1")


def test_cache_key_excludes_secrets_and_secret_query_values() -> None:
    provider = _Provider(sleeper=lambda _delay: None)
    first = provider.get_cache_key(
        {
            "mpn": "OPA333AIDBVR",
            "apiKey": "first-secret",
            "url": "https://example.test/search?apiKey=first-secret&lang=en",
        }
    )
    second = provider.get_cache_key(
        {
            "mpn": "OPA333AIDBVR",
            "apiKey": "second-secret",
            "url": "https://example.test/search?apiKey=second-secret&lang=en",
        }
    )
    assert first == second
    assert "first-secret" not in first
    assert "second-secret" not in second


def test_canonical_request_removes_url_userinfo_and_generic_token_query() -> None:
    request = canonical_request(
        "test-provider",
        {
            "url": (
                "https://fake-user:fake-password@example.test/search?"
                "token=fake-token&lang=ja-JP&part=OPA333AIDBVR"
            ),
            "tokenizer": "public-tokenizer-name",
            "authToken": "fake-auth-token",
            "oauthAccessToken": "fake-prefixed-access-token",
            "myClientSecret": "fake-prefixed-client-secret",
            "databasePassword": "fake-prefixed-password",
            "client_id": "fake-client-id",
            "clientId": "fake-camel-client-id",
            "X-DIGIKEY-Client-Id": "fake-header-client-id",
        },
    )

    serialized = json.dumps(request, sort_keys=True)
    assert "fake-user" not in serialized
    assert "fake-password" not in serialized
    assert "fake-token" not in serialized
    assert "fake-auth-token" not in serialized
    assert "fake-prefixed-access-token" not in serialized
    assert "fake-prefixed-client-secret" not in serialized
    assert "fake-prefixed-password" not in serialized
    assert "fake-client-id" not in serialized
    assert "fake-camel-client-id" not in serialized
    assert "fake-header-client-id" not in serialized
    assert request["request"]["url"] == (
        "https://example.test/search?lang=ja-JP&part=OPA333AIDBVR"
    )
    assert request["request"]["tokenizer"] == "public-tokenizer-name"


def test_canonical_request_fails_closed_for_malformed_http_url() -> None:
    request = canonical_request(
        "test-provider",
        {"url": "https:/search?apiKey=fake-secret&lang=ja-JP"},
    )

    assert request["request"]["url"] == "<invalid-url>"
    assert "fake-secret" not in json.dumps(request, sort_keys=True)


def test_retry_honors_bounded_retry_after_and_stops_after_three() -> None:
    attempts: List[int] = []
    delays: List[float] = []

    def opener(_request: object, timeout: float) -> _Response:
        del timeout
        attempts.append(1)
        return _Response({}, status=429, headers={"Retry-After": "9999"})

    provider = _Provider(opener=opener, sleeper=delays.append)
    with pytest.raises(RateLimitedError) as raised:
        provider.request()

    assert len(attempts) == 3
    assert delays == [30.0, 30.0]
    assert raised.value.code == "RATE_LIMITED"
    assert raised.value.status == 429


def test_transport_exception_is_retried_without_leaking_details() -> None:
    attempts: List[int] = []

    def opener(_request: object, timeout: float) -> _Response:
        del timeout
        attempts.append(1)
        raise urllib.error.URLError("secret-bearing transport detail")

    provider = _Provider(opener=opener, sleeper=lambda _delay: None)
    with pytest.raises(NetworkError) as raised:
        provider.request()

    assert len(attempts) == 3
    assert "secret-bearing" not in str(raised.value)
    assert raised.value.provider == "test-provider"


def test_provider_error_string_is_structured_and_safe() -> None:
    error = ProviderError("mouser", status=403, operation="part-search")
    assert error.provider == "mouser"
    assert error.code == "PROVIDER_ERROR"
    assert str(error) == "mouser: PROVIDER_ERROR: part-search: HTTP 403"
