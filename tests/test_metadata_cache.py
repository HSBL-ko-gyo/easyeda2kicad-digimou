from __future__ import annotations

# Global imports
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from easyeda2kicad.metadata.cache import (
    CACHE_SCHEMA_VERSION,
    CacheCorruptError,
    MetadataCache,
    OfflineCacheMissError,
    canonical_request,
    make_cache_key,
    sanitize_public_url,
    sanitize_url,
    strip_secrets,
)

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _cache(tmp_path: Path) -> MetadataCache:
    return MetadataCache(tmp_path / ".easyeda_cache" / "metadata", now=lambda: NOW)


def _request(api_key: str = "do-not-store") -> dict[str, object]:
    return canonical_request(
        "mouser",
        "search_exact_mpn",
        mpn=" LM321MF/NOPB ",
        manufacturer="Texas Instruments",
        options={
            "locale": "en-US",
            "api_key": api_key,
            "url": "https://api.example/search?apiKey=" + api_key + "&q=LM321",
        },
    )


def test_canonical_key_is_deterministic_and_excludes_secrets() -> None:
    first = _request("first-secret")
    second = _request("second-secret")

    assert first == second
    assert "first-secret" not in json.dumps(first)
    assert "second-secret" not in json.dumps(second)
    assert first["mpn_normalized"] == "LM321MF/NOPB"
    assert make_cache_key("mouser", first) == make_cache_key("mouser", second)


def test_cache_separates_raw_and_normalized_and_reads_fresh(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    request = _request()
    key = cache.get_cache_key("mouser", request)

    raw_path, normalized_path = cache.write(
        "mouser",
        key,
        raw={"SearchResults": {"Parts": [1]}},
        normalized={"provider": "mouser", "raw_response_cache_key": key},
        request=request,
        retrieved_at="2026-07-22T11:00:00Z",
    )

    assert raw_path == cache.root / "mouser" / key / "raw.json"
    assert normalized_path.name == "normalized.json"
    assert cache.read_raw("mouser", key) == {"SearchResults": {"Parts": [1]}}
    assert cache.read_normalized("mouser", key) == {
        "provider": "mouser",
        "raw_response_cache_key": key,
    }
    raw_envelope = json.loads(raw_path.read_text(encoding="utf-8"))
    normalized_envelope = json.loads(normalized_path.read_text(encoding="utf-8"))
    assert raw_envelope["payload_type"] == "redacted_raw"
    assert normalized_envelope["payload_type"] == "normalized"
    assert raw_envelope["generation_id"] == normalized_envelope["generation_id"]
    assert raw_envelope["raw_sha256"] == normalized_envelope["raw_sha256"]
    assert list(raw_path.parent.glob("*.tmp")) == []


def test_online_stale_is_miss_but_offline_accepts_stale(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    request = _request()
    key = cache.save(
        "mouser",
        request,
        raw={"value": 1},
        normalized={"value": 2},
        retrieved_at="2026-07-20T00:00:00Z",
    )

    assert cache.read_normalized("mouser", key) is None
    assert cache.read_normalized("mouser", key, offline=True) == {"value": 2}
    assert cache.read_normalized("mouser", key, refresh=True) is None
    with pytest.raises(ValueError, match="mutually exclusive"):
        cache.read_normalized("mouser", key, offline=True, refresh=True)


def test_corrupt_cache_online_misses_and_offline_is_explicit(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    key = cache.get_cache_key("digikey", {"operation": "search"})
    path = cache.path("digikey", key, "normalized")
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    assert cache.read_normalized("digikey", key) is None
    with pytest.raises(CacheCorruptError) as error:
        cache.read_normalized("digikey", key, offline=True)
    assert error.value.category == "CACHE_CORRUPT"
    assert "{not-json" not in str(error.value)


@pytest.mark.parametrize("missing_kind", ["raw", "normalized"])
def test_incomplete_evidence_pair_is_corrupt_offline(
    tmp_path: Path, missing_kind: str
) -> None:
    cache = _cache(tmp_path)
    request = _request()
    key = cache.save("mouser", request, {"raw": 1}, {"normalized": 2})
    cache.path("mouser", key, missing_kind).unlink()

    assert cache.read_normalized("mouser", key) is None
    with pytest.raises(CacheCorruptError, match="incomplete"):
        cache.read_normalized("mouser", key, offline=True)


def test_missing_evidence_pair_is_offline_miss(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    key = cache.get_cache_key("mouser", _request())

    with pytest.raises(OfflineCacheMissError):
        cache.read_normalized("mouser", key, offline=True)


def test_modified_redacted_raw_payload_invalidates_normalized_hit(
    tmp_path: Path,
) -> None:
    cache = _cache(tmp_path)
    request = _request()
    key = cache.save("mouser", request, {"raw": 1}, {"normalized": 2})
    raw_path = cache.path("mouser", key, "raw")
    envelope = json.loads(raw_path.read_text(encoding="utf-8"))
    envelope["data"] = {"raw": "tampered"}
    raw_path.write_text(json.dumps(envelope), encoding="utf-8")

    assert cache.read_normalized("mouser", key) is None
    with pytest.raises(CacheCorruptError):
        cache.read_normalized("mouser", key, offline=True)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("generation_id", "f" * 32),
        ("raw_sha256", "f" * 64),
        ("canonical_request", {"operation": "different"}),
        ("retrieved_at", "2026-07-22T10:59:59Z"),
    ],
)
def test_mismatched_pair_binding_is_corrupt_offline(
    tmp_path: Path, field: str, replacement: object
) -> None:
    cache = _cache(tmp_path)
    request = _request()
    key = cache.save("mouser", request, {"raw": 1}, {"normalized": 2})
    normalized_path = cache.path("mouser", key, "normalized")
    envelope = json.loads(normalized_path.read_text(encoding="utf-8"))
    envelope[field] = replacement
    normalized_path.write_text(json.dumps(envelope), encoding="utf-8")

    assert cache.read_normalized("mouser", key) is None
    with pytest.raises(CacheCorruptError):
        cache.read_normalized("mouser", key, offline=True)


def test_raw_provider_envelope_mismatch_invalidates_normalized_hit(
    tmp_path: Path,
) -> None:
    cache = _cache(tmp_path)
    request = _request()
    key = cache.save("mouser", request, {"raw": 1}, {"normalized": 2})
    raw_path = cache.path("mouser", key, "raw")
    envelope = json.loads(raw_path.read_text(encoding="utf-8"))
    envelope["provider"] = "digikey"
    raw_path.write_text(json.dumps(envelope), encoding="utf-8")

    assert cache.read_normalized("mouser", key) is None
    with pytest.raises(CacheCorruptError):
        cache.read_normalized("mouser", key, offline=True)


def test_pair_request_must_also_match_cache_key(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    request = _request()
    key = cache.save("mouser", request, {"raw": 1}, {"normalized": 2})
    for kind in ("raw", "normalized"):
        path = cache.path("mouser", key, kind)
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope["canonical_request"] = {"operation": "different"}
        path.write_text(json.dumps(envelope), encoding="utf-8")

    assert cache.read_normalized("mouser", key) is None
    with pytest.raises(CacheCorruptError):
        cache.read_normalized("mouser", key, offline=True)


def test_schema_v2_pair_is_not_reused_after_exact_completeness_fix(
    tmp_path: Path,
) -> None:
    assert CACHE_SCHEMA_VERSION == 3
    cache = _cache(tmp_path)
    request = _request()
    key = cache.save("mouser", request, {"raw": 1}, {"normalized": 2})
    for kind in ("raw", "normalized"):
        path = cache.path("mouser", key, kind)
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope["schema_version"] = 2
        path.write_text(json.dumps(envelope), encoding="utf-8")

    assert cache.read_normalized("mouser", key) is None
    with pytest.raises(CacheCorruptError):
        cache.read_normalized("mouser", key, offline=True)


def test_individually_replaced_generation_is_never_accepted_as_pair(
    tmp_path: Path,
) -> None:
    cache = _cache(tmp_path)
    request = _request()
    key = cache.save("mouser", request, {"raw": 1}, {"normalized": 2})

    # This models an interrupted/concurrent pair publication after raw.json was
    # replaced but before the matching normalized.json became visible.
    cache.write_raw("mouser", key, {"raw": "new"}, request=request)

    assert cache.read_normalized("mouser", key) is None
    with pytest.raises(CacheCorruptError):
        cache.read_normalized("mouser", key, offline=True)


def test_interrupted_pair_publication_leaves_no_acceptable_mixed_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache(tmp_path)
    request = _request()
    key = cache.save("mouser", request, {"raw": "old"}, {"normalized": "old"})
    original_replace = Path.replace

    def interrupt_normalized_replace(source: Path, target: Path) -> Path:
        if Path(target).name == "normalized.json":
            raise OSError("simulated interrupted publication")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", interrupt_normalized_replace)
    with pytest.raises(OSError, match="interrupted"):
        cache.write(
            "mouser",
            key,
            {"raw": "new"},
            {"normalized": "new"},
            request=request,
        )

    assert list(cache.entry_dir("mouser", key).glob("*.tmp")) == []
    assert cache.read_normalized("mouser", key) is None
    with pytest.raises(CacheCorruptError):
        cache.read_normalized("mouser", key, offline=True)


def test_missing_offline_entry_has_stable_error_category(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    key = cache.get_cache_key("lcsc", {"operation": "search"})

    with pytest.raises(OfflineCacheMissError) as error:
        cache.read_raw("lcsc", key, offline=True)
    assert error.value.category == "OFFLINE_CACHE_MISS"


def test_cache_write_strips_credentials_from_request_and_data(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    key = cache.get_cache_key("digikey", {"operation": "search"})
    path = cache.write_raw(
        "digikey",
        key,
        {
            "access_token": "secret-token",
            "url": "https://api.example/x?Authorization=secret-token&public=1",
            "part": "OPA333AIDBVR",
        },
        request={"client_secret": "client-secret", "locale": "US"},
    )

    content = path.read_text(encoding="utf-8")
    assert "secret-token" not in content
    assert "client-secret" not in content
    assert "OPA333AIDBVR" in content
    assert "public=1" in content


def test_strip_secrets_handles_camel_case_and_nested_headers_conservatively() -> None:
    sanitized = strip_secrets(
        {
            "AuthorizationHeader": "fake-authorization",
            "accessToken": "fake-access-token",
            "clientSecret": "fake-client-secret",
            "apiKey": "fake-api-key",
            "client_id": "fake-client-id",
            "clientId": "fake-camel-client-id",
            "oauthAccessToken": "fake-prefixed-access-token",
            "myClientSecret": "fake-prefixed-client-secret",
            "databasePassword": "fake-prefixed-password",
            "headers": {
                "Authorization": "fake-nested-authorization",
                "X-DIGIKEY-Client-Id": "fake-header-client-id",
                "Accept-Language": "ja-JP",
            },
            "url": (
                "https://api.example.test/search?"
                "AuthorizationHeader=fake-query-authorization&public=1"
            ),
            "accessTokenExpiresAt": "2026-07-22T12:00:00Z",
            "tokenizer": "public-parser-name",
            "part": "OPA333AIDBVR",
        }
    )

    serialized = json.dumps(sanitized, sort_keys=True)
    for secret in (
        "fake-authorization",
        "fake-access-token",
        "fake-client-secret",
        "fake-api-key",
        "fake-client-id",
        "fake-camel-client-id",
        "fake-prefixed-access-token",
        "fake-prefixed-client-secret",
        "fake-prefixed-password",
        "fake-header-client-id",
        "fake-nested-authorization",
        "fake-query-authorization",
    ):
        assert secret not in serialized
    assert sanitized["headers"] == {"Accept-Language": "ja-JP"}
    assert sanitized["accessTokenExpiresAt"] == "2026-07-22T12:00:00Z"
    assert sanitized["tokenizer"] == "public-parser-name"
    assert sanitized["part"] == "OPA333AIDBVR"
    assert "public=1" in sanitized["url"]


def test_secret_suffix_query_parameters_are_removed() -> None:
    sanitized = sanitize_url(
        "https://example.test/search?oauthAccessToken=fake-token&public=1"
    )

    assert sanitized == "https://example.test/search?public=1"


@pytest.mark.parametrize(
    "value",
    [
        "https://fake-user:fake-password@example.test:bad/search?apiKey=fake-secret",
        "https://fake-user:fake-password@[broken/search?apiKey=fake-secret",
        "https:/search?apiKey=fake-secret",
    ],
)
def test_malformed_http_urls_fail_closed(value: str) -> None:
    sanitized = sanitize_url(value)

    assert sanitized == "<invalid-url>"
    assert "fake-secret" not in str(strip_secrets({"url": value}))


def test_public_url_sanitizer_retains_only_nonsecret_query_parameters() -> None:
    sanitized = sanitize_public_url(
        "https://fake-user:fake-password@example.test/item?lang=ja&apiKey=fake&q=PART"
    )

    assert sanitized == "https://example.test/item?lang=ja&q=PART"
    assert sanitize_public_url("javascript:alert(1)") is None


def test_normalized_cache_supports_domain_revalidation(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    request = {"operation": "search"}
    key = cache.get_cache_key("mouser", request)
    cache.write(
        "mouser",
        key,
        raw={"evidence": True},
        normalized={"unexpected": True},
        request=request,
    )

    def require_provider(value: object) -> object:
        if not isinstance(value, dict) or "provider" not in value:
            raise ValueError("missing provider")
        return value

    assert cache.read_normalized("mouser", key, validator=require_provider) is None
    with pytest.raises(CacheCorruptError, match="revalidation"):
        cache.read_normalized("mouser", key, offline=True, validator=require_provider)


def test_normalized_cache_maps_overflowing_validator_to_cache_semantics(
    tmp_path: Path,
) -> None:
    cache = _cache(tmp_path)
    request = {"operation": "search"}
    key = cache.save(
        "mouser",
        request,
        raw={"evidence": True},
        normalized={"provider": "mouser"},
    )

    def overflow(_value: object) -> object:
        raise OverflowError("simulated numeric overflow")

    assert cache.read_normalized("mouser", key, validator=overflow) is None
    with pytest.raises(CacheCorruptError, match="revalidation"):
        cache.read_normalized("mouser", key, offline=True, validator=overflow)


@pytest.mark.parametrize("provider", ["../mouser", "mouser/key", ""])
def test_cache_rejects_provider_path_traversal(tmp_path: Path, provider: str) -> None:
    with pytest.raises(ValueError, match="provider"):
        _cache(tmp_path).entry_dir(provider, "a" * 64)
