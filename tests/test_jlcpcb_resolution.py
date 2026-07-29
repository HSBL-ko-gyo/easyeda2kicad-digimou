from __future__ import annotations

# Global imports
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, cast

import pytest

# Local imports
from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.metadata import (
    JLCPCB_CACHE_CACHED,
    JLCPCB_CACHE_ERROR,
    JLCPCB_CACHE_LIVE,
    JLCPCB_CACHE_OFFLINE_MISS,
    JLCPCB_IDENTITY_AMBIGUOUS,
    JLCPCB_IDENTITY_CONFLICT,
    JLCPCB_LOOKUP_FAILED,
    JLCPCB_PART_FOUND,
    MANUAL_GLOBAL_SOURCING_REQUIRED,
    MetadataCache,
)
from easyeda2kicad.metadata.manifest import (
    CSV_COLUMNS,
    csv_manifest_rows,
    manifest_to_dict,
)
from easyeda2kicad.metadata.models import (
    DistributorRecord,
    GlobalSourcingCandidate,
    JlcpcbResolution,
    model_from_dict,
)
from easyeda2kicad.metadata.service import (
    JLCPCB_MANUAL_ACTION,
    MetadataResolution,
    resolve_metadata,
)
from easyeda2kicad.metadata.symbol_fields import build_native_symbol_fields
from easyeda2kicad.providers import (
    AmbiguousMatchError,
    MetadataProvider,
    MpnMismatchError,
    NetworkError,
    NotFoundError,
)

MANUFACTURER = "Texas Instruments"
MPN = "OPA333AIDBVR"
CHECKED_AT = "2026-07-26T12:34:56Z"


class _Provider:
    def __init__(
        self,
        name: str,
        *,
        record: Optional[DistributorRecord] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self.name = name
        self.record = record
        self.error = error
        self.exact_calls = 0
        self.id_calls = 0
        self.last_raw_response: Mapping[str, Any] = {"provider": name}

    def get_cache_context(self) -> Mapping[str, str]:
        return {}

    def search_exact_mpn(
        self, manufacturer: Optional[str], mpn: str
    ) -> DistributorRecord:
        assert manufacturer == MANUFACTURER
        assert mpn == MPN
        self.exact_calls += 1
        if self.error is not None:
            raise self.error
        assert self.record is not None
        return self.record

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord:
        del part_id
        self.id_calls += 1
        raise AssertionError("same-command exact-MPN flow used an ID lookup")


def _record(
    provider: str,
    *,
    part_number: Optional[str] = None,
    stock: Optional[int] = 10,
    product_url: Optional[str] = None,
) -> DistributorRecord:
    default_parts = {
        "lcsc": "C30878",
        "digikey": "296-26269-1-ND",
        "mouser": "595-OPA333AIDBVR",
    }
    return DistributorRecord(
        provider=provider,
        distributor_part_number=part_number or default_parts[provider],
        product_url=product_url,
        manufacturer=MANUFACTURER,
        mpn=MPN,
        stock=stock,
        retrieved_at=CHECKED_AT,
    )


def _factory(
    providers: Mapping[str, _Provider],
) -> Callable[[str, EasyedaApi], MetadataProvider]:
    def create(name: str, api: EasyedaApi) -> MetadataProvider:
        del api
        provider = providers.get(name)
        if provider is None:
            # CAD handoff discovery may request its explicit external source
            # even when this test only needs to exercise JLCPCB resolution.
            # This deliberately does not implement the source-specific CAD
            # protocol, so discovery returns the typed no-package result.
            provider = _Provider(
                name,
                error=NotFoundError(name, operation="exact-match"),
            )
        return cast(MetadataProvider, provider)

    return create


def _resolve(
    tmp_path: Path,
    providers: Mapping[str, _Provider],
    *,
    provider_names: tuple[str, ...] = (),
    cache: Optional[MetadataCache] = None,
    offline: bool = False,
    refresh: bool = False,
    cad_source: str = "digikey",
) -> MetadataResolution:
    return resolve_metadata(
        requested_mpn=MPN,
        requested_manufacturer=MANUFACTURER,
        requested_lcsc_id=None,
        provider_names=provider_names,
        cad_api=EasyedaApi(),
        cad_source=cad_source,
        cache=cache or MetadataCache(tmp_path / "cache"),
        offline=offline,
        refresh_metadata=refresh,
        provider_factory=_factory(providers),
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )


@pytest.fixture(autouse=True)
def _fixed_check_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "easyeda2kicad.metadata.service._jlcpcb_checked_at",
        lambda: CHECKED_AT,
    )


@pytest.mark.parametrize("stock", [0, 42])
@pytest.mark.parametrize("cad_source", ["digikey", "mouser"])
def test_same_command_finds_canonical_part_independent_of_stock_and_selection(
    tmp_path: Path,
    stock: int,
    cad_source: str,
) -> None:
    lcsc = _Provider("lcsc", record=_record("lcsc", stock=stock))

    result = _resolve(tmp_path, {"lcsc": lcsc}, cad_source=cad_source)
    merged = result.to_merged()

    assert lcsc.exact_calls == 1
    assert result.jlcpcb is not None
    assert result.jlcpcb.match_status == JLCPCB_PART_FOUND
    assert result.jlcpcb.jlcpcb_part_number == "C30878"
    assert result.jlcpcb.lcsc_part_number == "C30878"
    assert result.jlcpcb.stock == stock
    assert result.jlcpcb.cache_state == JLCPCB_CACHE_LIVE
    assert result.jlcpcb.checked_at == CHECKED_AT
    assert result.jlcpcb.manual_action_required is None
    assert merged.distributor_records == []
    assert build_native_symbol_fields(merged)["LCSC Part"] == "C30878"
    assert result.cad_discovery is not None
    assert result.cad_discovery.request is not None
    assert result.cad_discovery.request.source == cad_source
    redacted = manifest_to_dict(merged, include_stock=False)
    assert redacted["jlcpcb"]["stock"] is None
    assert csv_manifest_rows(merged, include_stock=False)[0]["JLCPCB Stock"] == ""


def test_no_match_keeps_rows_and_exact_distributor_candidates(tmp_path: Path) -> None:
    lcsc = _Provider(
        "lcsc",
        error=NotFoundError("lcsc", operation="exact-match"),
    )
    digikey = _Provider(
        "digikey",
        record=_record(
            "digikey",
            product_url=(
                "https://www.digikey.com/en/products/detail/example"
                "?token=secret&part=OPA333"
            ),
        ),
    )
    mouser = _Provider(
        "mouser",
        record=_record(
            "mouser",
            product_url=(
                "https://www.mouser.com/ProductDetail/example?api_key=secret&qs=public"
            ),
        ),
    )

    result = _resolve(
        tmp_path,
        {"lcsc": lcsc, "digikey": digikey, "mouser": mouser},
        provider_names=("digikey", "mouser"),
    )
    merged = result.to_merged()
    payload = manifest_to_dict(merged)
    rows = csv_manifest_rows(merged)

    assert result.jlcpcb is not None
    assert result.jlcpcb.match_status == MANUAL_GLOBAL_SOURCING_REQUIRED
    assert result.jlcpcb.jlcpcb_part_number is None
    assert result.jlcpcb.lcsc_part_number is None
    assert result.jlcpcb.stock is None
    assert result.jlcpcb.manual_action_required == JLCPCB_MANUAL_ACTION
    assert [
        candidate.provider for candidate in result.jlcpcb.global_sourcing_candidates
    ] == [
        "digikey",
        "mouser",
    ]
    assert len(rows) == 2
    assert all(row["JLCPCB Part #"] == "" for row in rows)
    assert all(row["LCSC Part #"] == "" for row in rows)
    assert all(row["LCSC Part"] == "" for row in rows)
    assert all(
        row["JLCPCB Match Status"] == MANUAL_GLOBAL_SOURCING_REQUIRED for row in rows
    )
    assert all(row["Manual Action Required"] == JLCPCB_MANUAL_ACTION for row in rows)
    assert tuple(rows[0]) == CSV_COLUMNS
    assert build_native_symbol_fields(merged).get("LCSC Part") is None
    candidate_urls = [
        candidate["product_url"]
        for candidate in payload["jlcpcb"]["global_sourcing_candidates"]
    ]
    assert all("secret" not in (url or "") for url in candidate_urls)
    assert all("token=" not in (url or "") for url in candidate_urls)
    assert all("api_key=" not in (url or "") for url in candidate_urls)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (
            NetworkError("lcsc", operation="catalogue-search"),
            JLCPCB_LOOKUP_FAILED,
        ),
        (
            AmbiguousMatchError("lcsc", operation="exact-match"),
            JLCPCB_IDENTITY_AMBIGUOUS,
        ),
        (
            MpnMismatchError("lcsc", operation="exact-match"),
            JLCPCB_IDENTITY_CONFLICT,
        ),
    ],
)
def test_lookup_failure_ambiguity_and_conflict_remain_distinct(
    tmp_path: Path,
    error: Exception,
    expected_status: str,
) -> None:
    lcsc = _Provider("lcsc", error=error)

    result = _resolve(tmp_path, {"lcsc": lcsc})

    assert result.jlcpcb is not None
    assert result.jlcpcb.match_status == expected_status
    assert result.jlcpcb.cache_state == JLCPCB_CACHE_LIVE
    assert result.jlcpcb.jlcpcb_part_number is None
    assert result.jlcpcb.lcsc_part_number is None
    assert result.jlcpcb.manual_action_required is None
    assert result.provider_errors["lcsc"] == getattr(error, "code")


def test_lookup_failure_does_not_stop_requested_provider_metadata(
    tmp_path: Path,
) -> None:
    lcsc = _Provider(
        "lcsc",
        error=NetworkError("lcsc", operation="catalogue-search"),
    )
    digikey = _Provider("digikey", record=_record("digikey"))

    result = _resolve(
        tmp_path,
        {"lcsc": lcsc, "digikey": digikey},
        provider_names=("digikey",),
        cad_source="easyeda",
    )

    assert result.blocking_error == "NETWORK_ERROR"
    assert digikey.exact_calls == 1
    assert [record.provider for record in result.distributor_records] == ["digikey"]
    assert result.jlcpcb is not None
    assert result.jlcpcb.match_status == JLCPCB_LOOKUP_FAILED


def test_cache_live_refresh_and_offline_states_are_observable(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path / "cache")
    first_provider = _Provider("lcsc", record=_record("lcsc"))

    first = _resolve(
        tmp_path,
        {"lcsc": first_provider},
        cache=cache,
    )
    assert first.jlcpcb is not None
    assert first.jlcpcb.cache_state == JLCPCB_CACHE_LIVE
    assert first_provider.exact_calls == 1

    cached_provider = _Provider(
        "lcsc",
        error=AssertionError("cache hit called provider"),
    )
    cached = _resolve(
        tmp_path,
        {"lcsc": cached_provider},
        cache=cache,
        offline=True,
    )
    assert cached.jlcpcb is not None
    assert cached.jlcpcb.cache_state == JLCPCB_CACHE_CACHED
    assert cached_provider.exact_calls == 0

    refresh_provider = _Provider("lcsc", record=_record("lcsc", stock=0))
    refreshed = _resolve(
        tmp_path,
        {"lcsc": refresh_provider},
        cache=cache,
        refresh=True,
    )
    assert refreshed.jlcpcb is not None
    assert refreshed.jlcpcb.cache_state == JLCPCB_CACHE_LIVE
    assert refreshed.jlcpcb.stock == 0
    assert refresh_provider.exact_calls == 1

    miss_provider = _Provider(
        "lcsc",
        error=AssertionError("offline miss called provider"),
    )
    missed = _resolve(
        tmp_path,
        {"lcsc": miss_provider},
        cache=MetadataCache(tmp_path / "empty-cache"),
        offline=True,
    )
    assert missed.jlcpcb is not None
    assert missed.jlcpcb.match_status == JLCPCB_LOOKUP_FAILED
    assert missed.jlcpcb.cache_state == JLCPCB_CACHE_OFFLINE_MISS
    assert miss_provider.exact_calls == 0


def test_corrupt_offline_cache_is_lookup_failure_not_no_match(tmp_path: Path) -> None:
    cache = MetadataCache(tmp_path / "cache")
    first_provider = _Provider("lcsc", record=_record("lcsc"))
    _resolve(tmp_path, {"lcsc": first_provider}, cache=cache)
    request = cache.canonical_request(
        "lcsc",
        "search_exact_mpn",
        mpn=MPN,
        manufacturer=MANUFACTURER,
        options={"provider_context": {}},
    )
    key = cache.get_cache_key("lcsc", request)
    cache.path("lcsc", key, "normalized").write_text("{}\n", encoding="utf-8")
    offline_provider = _Provider(
        "lcsc",
        error=AssertionError("corrupt offline cache called provider"),
    )

    result = _resolve(
        tmp_path,
        {"lcsc": offline_provider},
        cache=cache,
        offline=True,
    )

    assert result.jlcpcb is not None
    assert result.jlcpcb.match_status == JLCPCB_LOOKUP_FAILED
    assert result.jlcpcb.cache_state == JLCPCB_CACHE_ERROR
    assert offline_provider.exact_calls == 0


def test_jlcpcb_resolution_round_trips_separate_number_fields() -> None:
    resolution = JlcpcbResolution(
        match_status=JLCPCB_PART_FOUND,
        checked_at=CHECKED_AT,
        cache_state=JLCPCB_CACHE_LIVE,
        jlcpcb_part_number="C30878",
        lcsc_part_number="C30878",
        stock=0,
        global_sourcing_candidates=[
            GlobalSourcingCandidate(
                provider="digikey",
                manufacturer_part_number=MPN,
                distributor_part_number="296-26269-1-ND",
                product_url="https://www.digikey.com/example",
            )
        ],
    )

    assert model_from_dict(JlcpcbResolution, resolution.to_dict()) == resolution


def test_global_sourcing_candidates_deduplicate_identical_records() -> None:
    candidate = GlobalSourcingCandidate(
        provider="digikey",
        manufacturer_part_number=MPN,
        distributor_part_number="296-26269-1-ND",
        product_url="https://www.digikey.com/example",
    )

    resolution = JlcpcbResolution(
        match_status=MANUAL_GLOBAL_SOURCING_REQUIRED,
        checked_at=CHECKED_AT,
        cache_state=JLCPCB_CACHE_LIVE,
        manual_action_required=JLCPCB_MANUAL_ACTION,
        global_sourcing_candidates=[candidate, candidate],
    )

    assert resolution.global_sourcing_candidates == [candidate]


@pytest.mark.parametrize(
    "values",
    [
        {
            "match_status": "FOUND",
            "checked_at": CHECKED_AT,
            "cache_state": JLCPCB_CACHE_LIVE,
        },
        {
            "match_status": JLCPCB_PART_FOUND,
            "checked_at": CHECKED_AT,
            "cache_state": JLCPCB_CACHE_LIVE,
        },
        {
            "match_status": JLCPCB_PART_FOUND,
            "checked_at": CHECKED_AT,
            "cache_state": JLCPCB_CACHE_LIVE,
            "jlcpcb_part_number": "NOT_FOUND",
        },
        {
            "match_status": MANUAL_GLOBAL_SOURCING_REQUIRED,
            "checked_at": CHECKED_AT,
            "cache_state": JLCPCB_CACHE_LIVE,
        },
        {
            "match_status": JLCPCB_LOOKUP_FAILED,
            "checked_at": CHECKED_AT,
            "cache_state": JLCPCB_CACHE_LIVE,
            "lcsc_part_number": "C30878",
        },
    ],
)
def test_jlcpcb_resolution_rejects_invalid_or_misleading_states(
    values: Mapping[str, Any],
) -> None:
    with pytest.raises(ValueError):
        JlcpcbResolution.from_dict(values)
