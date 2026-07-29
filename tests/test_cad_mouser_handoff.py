from __future__ import annotations

# Global imports
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, cast

import pytest

# Local imports
from easyeda2kicad import __main__ as cli
from easyeda2kicad.cad import MouserCadSource
from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.metadata.cache import MetadataCache
from easyeda2kicad.metadata.manifest import manifest_to_dict
from easyeda2kicad.metadata.models import (
    CAD_AUTH_REQUIRED,
    CAD_DOWNLOAD_UNAVAILABLE,
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CAD_NOT_ACQUIRED,
    CadActionRequired,
    CadDiscoveryResult,
    CadProvenance,
    CadRequest,
    DistributorRecord,
)
from easyeda2kicad.metadata.service import MetadataResolution, resolve_metadata
from easyeda2kicad.providers import (
    InvalidResponseError,
    MetadataProvider,
    MouserProvider,
    NotFoundError,
)
from easyeda2kicad.providers.mouser import MOUSER_SEARCH_URL

MANUFACTURER = "Rectron"
MPN = "FM220A-W"
MOUSER_PART = "583-FM220A-W"
PRODUCT_URL = (
    "https://www.mouser.com/ProductDetail/Rectron/FM220A-W"
    "?qs=P1rOgYsovGAifjKJwGIvBQ%3D%3D"
)


class _Response(io.BytesIO):
    def __init__(self, payload: Mapping[str, Any]) -> None:
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = 200
        self.headers: Dict[str, str] = {}


class _UnusedLcscProvider:
    name = "lcsc"

    def get_cache_context(self) -> Dict[str, str]:
        return {}

    def search_exact_mpn(
        self, manufacturer: Optional[str], mpn: str
    ) -> DistributorRecord:
        del manufacturer, mpn
        raise AssertionError("LCSC metadata lookup was not requested")

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord:
        del part_id
        raise AssertionError("LCSC metadata lookup was not requested")


def _response(*, product_url: Optional[str] = PRODUCT_URL) -> Dict[str, Any]:
    return {
        "SearchResults": {
            "NumberOfResult": 1,
            "Parts": [
                {
                    "MouserPartNumber": MOUSER_PART,
                    "ManufacturerPartNumber": MPN,
                    "Manufacturer": MANUFACTURER,
                    "ProductDetailUrl": product_url,
                    "Description": "SMB 2A 20V Schottky",
                    "PriceBreaks": [],
                }
            ],
        }
    }


def _provider(
    response: Mapping[str, Any],
    *,
    requests: Optional[List[urllib.request.Request]] = None,
    credentials: bool = True,
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
        env={"MOUSER_API_KEY": "fixture-key"} if credentials else {},
    )


def _record(
    *,
    provider: str = "mouser",
    manufacturer: str = MANUFACTURER,
    mpn: str = MPN,
    product_url: Optional[str] = PRODUCT_URL,
    distributor_part_number: Optional[str] = MOUSER_PART,
) -> DistributorRecord:
    return DistributorRecord(
        provider=provider,
        distributor_part_number=distributor_part_number,
        product_url=product_url,
        manufacturer=manufacturer,
        mpn=mpn,
    )


def _request() -> CadRequest:
    return CadRequest(
        manufacturer=MANUFACTURER,
        mpn=MPN,
        source="mouser",
    )


def _provider_factory(
    mouser: MouserProvider,
) -> Any:
    def factory(name: str, _api: EasyedaApi) -> MetadataProvider:
        if name == "mouser":
            return cast(MetadataProvider, mouser)
        return cast(MetadataProvider, _UnusedLcscProvider())

    return factory


def test_official_api_product_handoff_is_manual_sanitized_and_never_fetched() -> None:
    requests: List[urllib.request.Request] = []
    response = _response(
        product_url=(
            "https://www.mouser.com/ProductDetail/Rectron/FM220A-W"
            "?token=private&qs=public"
        )
    )
    provider = _provider(response, requests=requests)

    result = MouserCadSource(provider).discover(_request())

    assert len(requests) == 1
    parsed_api_url = urllib.parse.urlsplit(requests[0].full_url)
    assert (
        "{0}://{1}{2}".format(
            parsed_api_url.scheme,
            parsed_api_url.netloc,
            parsed_api_url.path,
        )
        == MOUSER_SEARCH_URL
    )
    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.request == _request()
    assert result.package is None
    assert result.provenance.distributor == "mouser"
    assert result.provenance.delivery_partner == "samacsys"
    assert result.provenance.model_creator is None
    assert result.provenance.retrieval_mode == "official-api-product-handoff"
    assert result.provenance.landing_url == (
        "https://www.mouser.com/ProductDetail/Rectron/FM220A-W?qs=public"
    )
    assert result.action_required is not None
    assert result.action_required.code == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.action_required.setup_url == result.provenance.landing_url
    assert "Library Loader" in result.action_required.detail
    assert "private" not in json.dumps(result.to_dict(), sort_keys=True)


def test_existing_exact_record_avoids_a_second_api_request() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider(_response(), requests=requests)

    result = MouserCadSource(provider).discover(
        _request(),
        exact_record=_record(),
    )

    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert requests == []


@pytest.mark.parametrize(
    "url",
    [
        "http://www.mouser.com/ProductDetail/Rectron/FM220A-W",
        "https://user:password@www.mouser.com/ProductDetail/Rectron/FM220A-W",
        "https://www.mouser.com:444/ProductDetail/Rectron/FM220A-W",
        "https://www.mouser.com/example/Rectron/FM220A-W",
        "https://mouser.example/ProductDetail/Rectron/FM220A-W",
        "javascript:alert(1)",
    ],
)
def test_unsafe_or_non_product_handoff_fails_closed(url: str) -> None:
    result = MouserCadSource(_provider(_response())).discover(
        _request(),
        exact_record=_record(product_url=url),
    )

    assert result.status == CAD_DOWNLOAD_UNAVAILABLE
    assert result.package is None
    assert result.provenance.delivery_partner is None
    assert result.provenance.landing_url is None
    assert result.action_required is not None
    assert result.action_required.code == CAD_DOWNLOAD_UNAVAILABLE
    assert result.action_required.setup_url is None


@pytest.mark.parametrize(
    "record",
    [
        _record(mpn="FM220A"),
        _record(manufacturer="Other Rectifier Company"),
    ],
)
def test_exact_identity_is_revalidated_before_handoff(
    record: DistributorRecord,
) -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider(_response(), requests=requests)

    with pytest.raises(NotFoundError):
        MouserCadSource(provider).discover(_request(), exact_record=record)

    assert requests == []


@pytest.mark.parametrize(
    ("record", "operation"),
    [
        (_record(provider="digikey"), "cad-provider"),
        (_record(distributor_part_number=None), "cad-product-number"),
    ],
)
def test_malformed_exact_record_is_rejected(
    record: DistributorRecord,
    operation: str,
) -> None:
    with pytest.raises(InvalidResponseError) as error:
        MouserCadSource(_provider(_response())).discover(
            _request(),
            exact_record=record,
        )

    assert error.value.operation == operation


def test_wrong_cad_request_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="mouser CAD request"):
        MouserCadSource(_provider(_response())).discover(
            CadRequest(
                manufacturer=MANUFACTURER,
                mpn=MPN,
                source="digikey",
            )
        )


@pytest.mark.parametrize("provider_names", [(), ("mouser",)])
def test_service_returns_typed_auth_action_without_network_or_easyeda(
    provider_names: tuple[str, ...],
) -> None:
    requests: List[urllib.request.Request] = []
    mouser = _provider({}, requests=requests, credentials=False)

    result = resolve_metadata(
        requested_mpn=MPN,
        requested_manufacturer=MANUFACTURER,
        requested_lcsc_id=None,
        provider_names=provider_names,
        cad_api=EasyedaApi(),
        cad_source="mouser",
        provider_factory=_provider_factory(mouser),
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )

    assert result.cad is None
    assert result.cad_data is None
    assert result.cad_discovery is not None
    assert result.cad_discovery.status == CAD_AUTH_REQUIRED
    assert result.blocking_error == CAD_AUTH_REQUIRED
    assert result.provider_errors == {"mouser": "AUTH_MISSING"}
    assert result.cad_discovery.provenance.delivery_partner is None
    assert requests == []
    payload = manifest_to_dict(result.to_merged())
    assert payload["cad_discovery"]["action_required"]["setup_url"].startswith(
        "https://www.mouser.com/"
    )


def test_service_reuses_exact_metadata_record_for_product_handoff(
    tmp_path: Path,
) -> None:
    requests: List[urllib.request.Request] = []
    mouser = _provider(_response(), requests=requests)
    cache_root = tmp_path / "cache"

    result = resolve_metadata(
        requested_mpn=MPN,
        requested_manufacturer=MANUFACTURER,
        requested_lcsc_id=None,
        provider_names=("mouser",),
        cad_api=EasyedaApi(),
        cad_source="mouser",
        cache=MetadataCache(root=cache_root),
        provider_factory=_provider_factory(mouser),
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )

    assert result.cad_discovery is not None
    assert result.cad_discovery.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert len(result.distributor_records) == 1
    assert result.distributor_records[0].raw_response_cache_key is None
    assert len(requests) == 1
    assert requests[0].full_url.startswith(MOUSER_SEARCH_URL + "?")
    assert mouser.last_raw_response is None
    assert not cache_root.exists()


def test_service_offline_handoff_performs_no_mouser_or_easyeda_request() -> None:
    requests: List[urllib.request.Request] = []
    mouser = _provider(_response(), requests=requests)

    result = resolve_metadata(
        requested_mpn=MPN,
        requested_manufacturer=MANUFACTURER,
        requested_lcsc_id=None,
        provider_names=(),
        cad_api=EasyedaApi(),
        cad_source="mouser",
        offline=True,
        provider_factory=_provider_factory(mouser),
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )

    assert result.cad_discovery is not None
    assert result.cad_discovery.status == CAD_NOT_ACQUIRED
    assert result.cad_discovery.provenance.retrieval_mode == "offline"
    assert result.blocking_error == CAD_NOT_ACQUIRED
    assert requests == []


def test_selected_mouser_provider_is_live_only_and_offline_never_uses_network(
    tmp_path: Path,
) -> None:
    requests: List[urllib.request.Request] = []
    mouser = _provider(_response(), requests=requests)
    cache_root = tmp_path / "cache"

    result = resolve_metadata(
        requested_mpn=MPN,
        requested_manufacturer=MANUFACTURER,
        requested_lcsc_id=None,
        provider_names=("mouser",),
        cad_api=EasyedaApi(),
        cad_source="mouser",
        cache=MetadataCache(root=cache_root),
        offline=True,
        provider_factory=_provider_factory(mouser),
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )

    assert result.provider_errors == {"mouser": "OFFLINE_CACHE_MISS"}
    assert result.cad_discovery is not None
    assert result.cad_discovery.status == CAD_NOT_ACQUIRED
    assert result.cad_discovery.provenance.retrieval_mode == "offline"
    assert requests == []
    assert not cache_root.exists()


def test_old_mouser_cache_entry_is_not_replayed_offline(tmp_path: Path) -> None:
    requests: List[urllib.request.Request] = []
    mouser = _provider(_response(), requests=requests)
    cache = MetadataCache(root=tmp_path / "cache")
    request = cache.canonical_request(
        "mouser",
        "search_exact_mpn",
        mpn=MPN,
        manufacturer=MANUFACTURER,
        options={"provider_context": {}},
    )
    cache.save(
        "mouser",
        request,
        _response(),
        _record().to_dict(),
    )

    result = resolve_metadata(
        requested_mpn=MPN,
        requested_manufacturer=MANUFACTURER,
        requested_lcsc_id=None,
        provider_names=("mouser",),
        cad_api=EasyedaApi(),
        cad_source="mouser",
        cache=cache,
        offline=True,
        provider_factory=_provider_factory(mouser),
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )

    assert result.provider_errors == {"mouser": "OFFLINE_CACHE_MISS"}
    assert result.distributor_records == []
    assert result.cad_discovery is not None
    assert result.cad_discovery.status == CAD_NOT_ACQUIRED
    assert requests == []


def test_service_missing_product_url_is_typed_unavailable(
    tmp_path: Path,
) -> None:
    mouser = _provider(_response(product_url=None))

    result = resolve_metadata(
        requested_mpn=MPN,
        requested_manufacturer=MANUFACTURER,
        requested_lcsc_id=None,
        provider_names=("mouser",),
        cad_api=EasyedaApi(),
        cad_source="mouser",
        cache=MetadataCache(root=tmp_path / "cache"),
        provider_factory=_provider_factory(mouser),
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )

    assert result.cad_discovery is not None
    assert result.cad_discovery.status == CAD_DOWNLOAD_UNAVAILABLE
    assert result.cad_discovery.action_required is not None
    assert result.cad_discovery.action_required.setup_url is None
    assert result.blocking_error == CAD_DOWNLOAD_UNAVAILABLE


def test_cli_reports_only_sanitized_manual_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    handoff = (
        "https://www.mouser.com/ProductDetail/Rectron/FM220A-W?token=private&qs=public"
    )
    request = _request()
    resolution = MetadataResolution(
        trusted_mpn=request.mpn,
        trusted_manufacturer=request.manufacturer,
        requested_mpn=request.mpn,
        requested_manufacturer=request.manufacturer,
        mpn_source="user",
        manufacturer_source="user",
        cad_discovery=CadDiscoveryResult(
            requested_source="mouser",
            status=CAD_MANUAL_DOWNLOAD_REQUIRED,
            request=request,
            provenance=CadProvenance(
                distributor="mouser",
                delivery_partner="samacsys",
                landing_url=handoff,
                retrieval_mode="official-api-product-handoff",
            ),
            action_required=CadActionRequired(
                code=CAD_MANUAL_DOWNLOAD_REQUIRED,
                detail="Use the official handoff and then --cad-package",
                setup_url=handoff,
            ),
        ),
        blocking_error=CAD_MANUAL_DOWNLOAD_REQUIRED,
    )
    monkeypatch.setattr(cli, "resolve_metadata", lambda **_kwargs: resolution)
    manifest = tmp_path / "handoff.json"

    with caplog.at_level("WARNING"):
        exit_code = cli.main(
            [
                "--manufacturer",
                request.manufacturer,
                "--mpn",
                request.mpn,
                "--cad-source",
                "mouser",
                "--manifest-json",
                str(manifest),
            ]
        )

    assert exit_code == 1
    assert "CAD_MANUAL_DOWNLOAD_REQUIRED" in caplog.text
    assert "FM220A-W?qs=public" in caplog.text
    assert "private" not in caplog.text
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["cad_discovery"]["action_required"]["setup_url"] == (
        "https://www.mouser.com/ProductDetail/Rectron/FM220A-W?qs=public"
    )
    assert "private" not in manifest.read_text(encoding="utf-8")
