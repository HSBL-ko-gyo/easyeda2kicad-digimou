"""Policy-safe DigiKey Product Information V4 CAD handoff discovery."""

from __future__ import annotations

# Global imports
from typing import (
    Any,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    cast,
    runtime_checkable,
)
from urllib.parse import urlsplit

# Local imports
from easyeda2kicad_digimou.metadata.cache import sanitize_public_url
from easyeda2kicad_digimou.metadata.models import (
    CAD_DOWNLOAD_UNAVAILABLE,
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CadActionRequired,
    CadDiscoveryResult,
    CadProvenance,
    CadRequest,
    DistributorRecord,
)
from easyeda2kicad_digimou.providers.base import InvalidResponseError


@runtime_checkable
class DigiKeyProductApi(Protocol):
    """The authenticated API surface needed by the CAD source adapter."""

    name: str

    def search_exact_mpn(
        self, manufacturer: Optional[str], mpn: str
    ) -> DistributorRecord:
        raise NotImplementedError

    def validate_exact_match(
        self,
        candidates: Sequence[DistributorRecord],
        manufacturer: Optional[str],
        mpn: str,
    ) -> DistributorRecord:
        raise NotImplementedError

    def get_product_media(self, product_number: str) -> Mapping[str, Any]:
        raise NotImplementedError


class DigiKeyCadSource:
    """Discover an official Ultra Librarian handoff without browsing websites."""

    name = "digikey"

    def __init__(self, product_api: DigiKeyProductApi) -> None:
        self._product_api = product_api

    def discover(
        self,
        request: CadRequest,
        *,
        exact_record: Optional[DistributorRecord] = None,
    ) -> CadDiscoveryResult:
        if request.source != self.name:
            raise ValueError("DigiKeyCadSource requires a digikey CAD request")
        record = exact_record or self._product_api.search_exact_mpn(
            request.manufacturer,
            request.mpn,
        )
        record = self._product_api.validate_exact_match(
            [record],
            request.manufacturer,
            request.mpn,
        )
        product_number = record.distributor_part_number
        if product_number is None:
            raise InvalidResponseError(self.name, operation="cad-product-number")

        response = self._product_api.get_product_media(product_number)
        handoff_urls = _ultralibrarian_model_urls(response)
        product_page = _digikey_product_page_url(record.product_url)
        if (
            not handoff_urls
            and not _has_model_media(response)
            and product_page is not None
        ):
            provenance = CadProvenance(
                distributor="digikey",
                delivery_partner="ultralibrarian",
                model_creator=None,
                landing_url=product_page,
                retrieval_mode="official-api-product-page-handoff",
            )
            return CadDiscoveryResult(
                requested_source=self.name,
                status=CAD_MANUAL_DOWNLOAD_REQUIRED,
                request=request,
                provenance=provenance,
                action_required=CadActionRequired(
                    code=CAD_MANUAL_DOWNLOAD_REQUIRED,
                    detail=(
                        "Open the exact official DigiKey product page, verify that "
                        "its EDA/CAD Models entry identifies the requested part, "
                        "review the model agreement, select KiCad v6+ and STEP or "
                        "WRL, then rerun with the ZIP and a hash-bound evidence file"
                    ),
                    setup_url=product_page,
                ),
            )
        provenance = CadProvenance(
            distributor="digikey",
            delivery_partner=("ultralibrarian" if handoff_urls else None),
            model_creator=None,
            landing_url=(handoff_urls[0] if len(handoff_urls) == 1 else None),
            retrieval_mode="official-api-manual-handoff",
        )
        if len(handoff_urls) != 1:
            return CadDiscoveryResult(
                requested_source=self.name,
                status=CAD_DOWNLOAD_UNAVAILABLE,
                request=request,
                provenance=provenance,
                action_required=CadActionRequired(
                    code=CAD_DOWNLOAD_UNAVAILABLE,
                    detail=(
                        "DigiKey Product Information V4 did not provide one "
                        "unambiguous Ultra Librarian model handoff for the exact part"
                    ),
                ),
            )

        handoff_url = handoff_urls[0]
        return CadDiscoveryResult(
            requested_source=self.name,
            status=CAD_MANUAL_DOWNLOAD_REQUIRED,
            request=request,
            provenance=provenance,
            action_required=CadActionRequired(
                code=CAD_MANUAL_DOWNLOAD_REQUIRED,
                detail=(
                    "Open the official DigiKey-linked Ultra Librarian handoff, "
                    "review its agreement, select KiCad v6+ and STEP or WRL, then "
                    "rerun with the ZIP and a hash-bound evidence file"
                ),
                setup_url=handoff_url,
            ),
        )


def _ultralibrarian_model_urls(response: Mapping[str, Any]) -> List[str]:
    if not isinstance(response, Mapping):
        raise InvalidResponseError("digikey", operation="media-normalize")
    raw_links = response.get("MediaLinks")
    if not isinstance(raw_links, list):
        raise InvalidResponseError("digikey", operation="media-normalize")

    matches: List[str] = []
    saw_malformed_model = False
    for raw_link in raw_links:
        if not isinstance(raw_link, Mapping):
            raise InvalidResponseError("digikey", operation="media-normalize")
        media_type = raw_link.get("MediaType")
        if not isinstance(media_type, str) or not media_type.strip():
            raise InvalidResponseError("digikey", operation="media-normalize")
        if media_type.strip().casefold() != "model":
            continue
        raw_url = raw_link.get("Url")
        if not isinstance(raw_url, str):
            saw_malformed_model = True
            continue
        safe_url = _safe_https_url(raw_url)
        if safe_url is None:
            saw_malformed_model = True
            continue
        if _delivery_partner(safe_url) != "ultralibrarian":
            continue
        matches.append(safe_url)
    if saw_malformed_model:
        raise InvalidResponseError("digikey", operation="media-normalize")
    return sorted(set(matches))


def _safe_https_url(value: str) -> Optional[str]:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme.casefold() != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            return None
    except ValueError:
        return None
    return sanitize_public_url(value)


def _has_model_media(response: Mapping[str, Any]) -> bool:
    raw_links = response.get("MediaLinks")
    if not isinstance(raw_links, list):
        return False
    return any(
        isinstance(raw_link, Mapping)
        and isinstance(raw_link.get("MediaType"), str)
        and cast(str, raw_link["MediaType"]).strip().casefold() == "model"
        for raw_link in raw_links
    )


def _delivery_partner(value: str) -> Optional[str]:
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    if hostname == "ultralibrarian.com" or hostname.endswith(".ultralibrarian.com"):
        return "ultralibrarian"
    if hostname == "mm.digikey.com" and "/opasdata/" in path:
        return "ultralibrarian"
    return None


def _digikey_product_page_url(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    safe_url = _safe_https_url(value)
    if safe_url is None:
        return None
    parsed = urlsplit(safe_url)
    if (
        parsed.hostname or ""
    ).casefold() != "www.digikey.com" or not parsed.path.casefold().startswith(
        "/en/products/detail/"
    ):
        return None
    return safe_url


__all__ = [
    "DigiKeyCadSource",
    "DigiKeyProductApi",
]
