from __future__ import annotations

import io
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, List, Mapping, Optional, cast

import pytest

from easyeda2kicad import __main__ as cli
from easyeda2kicad.cad.digikey import DigiKeyCadSource
from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.metadata.cache import MetadataCache
from easyeda2kicad.metadata.manifest import manifest_to_dict
from easyeda2kicad.metadata.models import (
    CAD_AUTH_REQUIRED,
    CAD_DOWNLOAD_UNAVAILABLE,
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CadActionRequired,
    CadDiscoveryResult,
    CadProvenance,
    CadRequest,
    DistributorRecord,
)
from easyeda2kicad.metadata.service import MetadataResolution, resolve_metadata
from easyeda2kicad.providers import (
    DigiKeyProvider,
    InvalidResponseError,
    MetadataProvider,
    NotFoundError,
)
from easyeda2kicad.providers.digikey import (
    DIGIKEY_KEYWORD_SEARCH_URL,
    DIGIKEY_MEDIA_URL_TEMPLATE,
    DIGIKEY_TOKEN_URL,
)


class _Response(io.BytesIO):
    def __init__(self, payload: Mapping[str, Any]) -> None:
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = 200
        self.headers: dict[str, str] = {}


class _NoMatchLcscProvider:
    name = "lcsc"

    def get_cache_context(self) -> dict[str, str]:
        return {}

    def search_exact_mpn(
        self, manufacturer: Optional[str], mpn: str
    ) -> DistributorRecord:
        del manufacturer, mpn
        raise NotFoundError("lcsc", operation="exact-match")

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord:
        del part_id
        raise NotFoundError("lcsc", operation="id-lookup")


def _record(
    *,
    manufacturer: str = "Analog Devices Inc.",
    mpn: str = "AD5314BRM",
    product_number: str = "AD5314BRM-ND",
) -> DistributorRecord:
    return DistributorRecord(
        provider="digikey",
        distributor_part_number=product_number,
        product_url=(
            "https://www.digikey.com/en/products/detail/analog-devices-inc/"
            "AD5314BRM/617418"
        ),
        manufacturer=manufacturer,
        mpn=mpn,
    )


def _provider(
    responses: List[Mapping[str, Any]],
    *,
    requests: Optional[List[urllib.request.Request]] = None,
    credentials: bool = True,
) -> DigiKeyProvider:
    queue = [_Response(response) for response in responses]

    def opener(request: urllib.request.Request, timeout: float) -> _Response:
        del timeout
        if requests is not None:
            requests.append(request)
        return queue.pop(0)

    environment = (
        {
            "DIGIKEY_CLIENT_ID": "fixture-client-id",
            "DIGIKEY_CLIENT_SECRET": "fixture-client-secret",
        }
        if credentials
        else {}
    )
    return DigiKeyProvider(
        opener=opener,
        sleeper=lambda _delay: None,
        clock=lambda: 1_700_000_000.0,
        env=environment,
    )


def _media(*urls: str) -> dict[str, object]:
    return {
        "MediaLinks": [
            {
                "MediaType": "Model",
                "Title": "Synthetic public-schema CAD model handoff",
                "Url": url,
            }
            for url in urls
        ]
    }


def test_official_media_handoff_is_manual_sanitized_and_never_scraped() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider(
        [
            {"access_token": "memory-only-token", "expires_in": 3600},
            _media(
                "https://mm.digikey.com/Volume0/opasdata/d220001/medias/"
                "common/5727/AD5314BRM.html?lang=en&token=secret#fragment"
            ),
        ],
        requests=requests,
    )
    result = DigiKeyCadSource(provider).discover(
        CadRequest(
            manufacturer="Analog Devices Inc.",
            mpn="AD5314BRM",
            source="digikey",
        ),
        exact_record=_record(),
    )

    expected_handoff = (
        "https://mm.digikey.com/Volume0/opasdata/d220001/medias/"
        "common/5727/AD5314BRM.html?lang=en"
    )
    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.action_required is not None
    assert result.action_required.setup_url == expected_handoff
    assert result.provenance == result.provenance.__class__(
        distributor="digikey",
        delivery_partner="ultralibrarian",
        model_creator=None,
        landing_url=expected_handoff,
        retrieval_mode="official-api-manual-handoff",
    )
    assert [request.full_url for request in requests] == [
        DIGIKEY_TOKEN_URL,
        DIGIKEY_MEDIA_URL_TEMPLATE.format(product_number="AD5314BRM-ND"),
    ]
    assert all(
        urllib.parse.urlsplit(request.full_url).hostname == "api.digikey.com"
        for request in requests
    )
    assert provider.last_raw_response is None
    assert "secret" not in json.dumps(result.to_dict(), sort_keys=True)


def test_empty_media_falls_back_to_exact_official_product_page_handoff() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider(
        [
            {"access_token": "memory-only-token", "expires_in": 3600},
            {"MediaLinks": []},
        ],
        requests=requests,
    )

    result = DigiKeyCadSource(provider).discover(
        CadRequest(
            manufacturer="Analog Devices Inc.",
            mpn="AD5314BRM",
            source="digikey",
        ),
        exact_record=_record(),
    )

    product_url = (
        "https://www.digikey.com/en/products/detail/analog-devices-inc/AD5314BRM/617418"
    )
    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.action_required is not None
    assert result.action_required.setup_url == product_url
    assert result.provenance == CadProvenance(
        distributor="digikey",
        delivery_partner="ultralibrarian",
        model_creator=None,
        landing_url=product_url,
        retrieval_mode="official-api-product-page-handoff",
    )
    assert [request.full_url for request in requests] == [
        DIGIKEY_TOKEN_URL,
        DIGIKEY_MEDIA_URL_TEMPLATE.format(product_number="AD5314BRM-ND"),
    ]


@pytest.mark.parametrize(
    "urls",
    [
        ("https://www.traceparts.com/example",),
        (
            "https://mm.digikey.com/Volume0/opasdata/one/model.html",
            "https://app.ultralibrarian.com/details/two",
        ),
    ],
)
def test_unknown_or_ambiguous_model_handoff_fails_closed(
    urls: tuple[str, ...],
) -> None:
    provider = _provider(
        [
            {"access_token": "memory-only-token", "expires_in": 3600},
            _media(*urls),
        ]
    )

    result = DigiKeyCadSource(provider).discover(
        CadRequest(
            manufacturer="Analog Devices Inc.",
            mpn="AD5314BRM",
            source="digikey",
        ),
        exact_record=_record(),
    )

    assert result.status == CAD_DOWNLOAD_UNAVAILABLE
    assert result.action_required is not None
    assert result.action_required.setup_url is None
    assert result.package is None


@pytest.mark.parametrize(
    "url",
    [
        "http://mm.digikey.com/Volume0/opasdata/model.html",
        "https://user:password@mm.digikey.com/Volume0/opasdata/model.html",
        "https://mm.digikey.com:444/Volume0/opasdata/model.html",
        "javascript:alert(1)",
    ],
)
def test_malformed_or_unsafe_official_model_url_is_rejected(url: str) -> None:
    provider = _provider(
        [
            {"access_token": "memory-only-token", "expires_in": 3600},
            _media(url),
        ]
    )

    with pytest.raises(InvalidResponseError, match="media-normalize"):
        DigiKeyCadSource(provider).discover(
            CadRequest(
                manufacturer="Analog Devices Inc.",
                mpn="AD5314BRM",
                source="digikey",
            ),
            exact_record=_record(),
        )


@pytest.mark.parametrize(
    "media_response",
    [
        {},
        {"MediaLinks": None},
        {"MediaLinks": [None]},
        {"MediaLinks": [{"Url": "https://mm.digikey.com/opasdata/model.html"}]},
        {"MediaLinks": [{"MediaType": "Model"}]},
    ],
)
def test_malformed_media_response_is_rejected(
    media_response: Mapping[str, Any],
) -> None:
    provider = _provider(
        [
            {"access_token": "memory-only-token", "expires_in": 3600},
            media_response,
        ]
    )

    with pytest.raises(InvalidResponseError, match="media-normalize"):
        DigiKeyCadSource(provider).discover(
            CadRequest(
                manufacturer="Analog Devices Inc.",
                mpn="AD5314BRM",
                source="digikey",
            ),
            exact_record=_record(),
        )


def test_exact_identity_is_revalidated_before_media_request() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider([], requests=requests)

    with pytest.raises(NotFoundError):
        DigiKeyCadSource(provider).discover(
            CadRequest(
                manufacturer="Analog Devices Inc.",
                mpn="AD5314BRM",
                source="digikey",
            ),
            exact_record=_record(mpn="AD5314BRMZ"),
        )

    assert requests == []


def test_media_request_encodes_distributor_number_and_keeps_secret_in_headers() -> None:
    requests: List[urllib.request.Request] = []
    provider = _provider(
        [
            {"access_token": "memory-only-token", "expires_in": 3600},
            {"MediaLinks": []},
        ],
        requests=requests,
    )

    response = provider.get_product_media("296-LM321MF/NOPBCT-ND")

    assert response == {"MediaLinks": []}
    assert requests[1].full_url == DIGIKEY_MEDIA_URL_TEMPLATE.format(
        product_number="296-LM321MF%2FNOPBCT-ND"
    )
    headers = {key.casefold(): value for key, value in requests[1].header_items()}
    assert headers["authorization"] == "Bearer memory-only-token"
    assert "memory-only-token" not in requests[1].full_url
    assert "fixture-client-secret" not in requests[1].full_url


@pytest.mark.parametrize("provider_names", [(), ("digikey",)])
def test_service_returns_typed_auth_action_without_network_or_easyeda(
    provider_names: tuple[str, ...],
) -> None:
    requests: List[urllib.request.Request] = []
    digikey = _provider([], requests=requests, credentials=False)

    def provider_factory(name: str, _api: EasyedaApi) -> MetadataProvider:
        if name == "digikey":
            return digikey
        return cast(MetadataProvider, _NoMatchLcscProvider())

    result = resolve_metadata(
        requested_mpn="AD5314BRM",
        requested_manufacturer="Analog Devices Inc.",
        requested_lcsc_id=None,
        provider_names=provider_names,
        cad_api=EasyedaApi(),
        cad_source="digikey",
        provider_factory=provider_factory,
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )

    assert result.cad is None
    assert result.cad_data is None
    assert result.cad_discovery is not None
    assert result.cad_discovery.status == CAD_AUTH_REQUIRED
    assert result.blocking_error == CAD_AUTH_REQUIRED
    assert result.provider_errors == {"digikey": "GUEST_LOOKUP_UNSUPPORTED"}
    assert result.jlcpcb is not None
    assert result.jlcpcb.match_status == "MANUAL_GLOBAL_SOURCING_REQUIRED"
    assert result.cad_discovery.provenance.delivery_partner is None
    assert requests == []
    payload = manifest_to_dict(result.to_merged())
    assert payload["cad_discovery"]["action_required"]["setup_url"].startswith(
        "https://developer.digikey.com/"
    )


def test_service_reuses_exact_metadata_record_for_media_discovery(
    tmp_path: Path,
) -> None:
    requests: List[urllib.request.Request] = []
    keyword_response = {
        "ProductsCount": 1,
        "ExactMatches": [],
        "Products": [
            {
                "ManufacturerProductNumber": "AD5314BRM",
                "Manufacturer": {"Name": "Analog Devices Inc."},
                "ProductUrl": _record().product_url,
                "ProductVariations": [
                    {
                        "DigiKeyProductNumber": "AD5314BRM-ND",
                        "PackageType": {"Name": "Tube"},
                        "StandardPricing": [],
                    }
                ],
                "Parameters": [],
            }
        ],
    }
    provider = _provider(
        [
            {"access_token": "memory-only-token", "expires_in": 3600},
            keyword_response,
            _media(
                "https://mm.digikey.com/Volume0/opasdata/d220001/medias/"
                "common/5727/AD5314BRM.html"
            ),
        ],
        requests=requests,
    )

    def provider_factory(name: str, _api: EasyedaApi) -> MetadataProvider:
        if name == "digikey":
            return provider
        return cast(MetadataProvider, _NoMatchLcscProvider())

    result = resolve_metadata(
        requested_mpn="AD5314BRM",
        requested_manufacturer="Analog Devices Inc.",
        requested_lcsc_id=None,
        provider_names=("digikey",),
        cad_api=EasyedaApi(),
        cad_source="digikey",
        cache=MetadataCache(root=tmp_path / "cache"),
        provider_factory=provider_factory,
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )

    assert result.cad_discovery is not None
    assert result.cad_discovery.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert len(result.distributor_records) == 1
    assert [request.full_url for request in requests] == [
        DIGIKEY_TOKEN_URL,
        DIGIKEY_KEYWORD_SEARCH_URL,
        DIGIKEY_MEDIA_URL_TEMPLATE.format(product_number="AD5314BRM-ND"),
    ]


def test_cli_reports_only_sanitized_manual_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    handoff = (
        "https://mm.digikey.com/Volume0/opasdata/d220001/medias/"
        "common/5727/AD5314BRM.html?token=private&lang=en"
    )
    request = CadRequest(
        manufacturer="Analog Devices Inc.",
        mpn="AD5314BRM",
        source="digikey",
    )
    resolution = MetadataResolution(
        trusted_mpn=request.mpn,
        trusted_manufacturer=request.manufacturer,
        requested_mpn=request.mpn,
        requested_manufacturer=request.manufacturer,
        mpn_source="user",
        manufacturer_source="user",
        cad_discovery=CadDiscoveryResult(
            requested_source="digikey",
            status=CAD_MANUAL_DOWNLOAD_REQUIRED,
            request=request,
            provenance=CadProvenance(
                distributor="digikey",
                delivery_partner="ultralibrarian",
                landing_url=handoff,
                retrieval_mode="official-api-manual-handoff",
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
                "digikey",
                "--manifest-json",
                str(manifest),
            ]
        )

    assert exit_code == 1
    assert "CAD_MANUAL_DOWNLOAD_REQUIRED" in caplog.text
    assert "AD5314BRM.html?lang=en" in caplog.text
    assert "private" not in caplog.text
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert (
        payload["cad_discovery"]["action_required"]["setup_url"]
        == "https://mm.digikey.com/Volume0/opasdata/d220001/medias/"
        "common/5727/AD5314BRM.html?lang=en"
    )
    assert "private" not in manifest.read_text(encoding="utf-8")
