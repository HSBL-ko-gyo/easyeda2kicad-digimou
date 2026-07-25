"""Policy-safe Mouser Search API CAD handoff discovery."""

from __future__ import annotations

# Global imports
from typing import Optional, Protocol, Sequence, runtime_checkable
from urllib.parse import urlsplit

# Local imports
from easyeda2kicad.metadata.cache import sanitize_public_url
from easyeda2kicad.metadata.models import (
    CAD_DOWNLOAD_UNAVAILABLE,
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CadActionRequired,
    CadDiscoveryResult,
    CadProvenance,
    CadRequest,
    DistributorRecord,
)
from easyeda2kicad.providers.base import InvalidResponseError


@runtime_checkable
class MouserProductApi(Protocol):
    """The authenticated Mouser API surface needed by the CAD source adapter."""

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


class MouserCadSource:
    """Return an exact official product handoff without browsing its web page."""

    name = "mouser"

    def __init__(self, product_api: MouserProductApi) -> None:
        self._product_api = product_api

    def discover(
        self,
        request: CadRequest,
        *,
        exact_record: Optional[DistributorRecord] = None,
    ) -> CadDiscoveryResult:
        if request.source != self.name:
            raise ValueError("MouserCadSource requires a mouser CAD request")
        record = exact_record or self._product_api.search_exact_mpn(
            request.manufacturer,
            request.mpn,
        )
        record = self._product_api.validate_exact_match(
            [record],
            request.manufacturer,
            request.mpn,
        )
        if record.provider != self.name:
            raise InvalidResponseError(self.name, operation="cad-provider")
        if not (record.distributor_part_number or "").strip():
            raise InvalidResponseError(self.name, operation="cad-product-number")

        handoff_url = _safe_mouser_product_url(record.product_url)
        provenance = CadProvenance(
            distributor="mouser",
            delivery_partner=("samacsys" if handoff_url else None),
            model_creator=None,
            landing_url=handoff_url,
            retrieval_mode="official-api-product-handoff",
        )
        if handoff_url is None:
            return CadDiscoveryResult(
                requested_source=self.name,
                status=CAD_DOWNLOAD_UNAVAILABLE,
                request=request,
                provenance=provenance,
                action_required=CadActionRequired(
                    code=CAD_DOWNLOAD_UNAVAILABLE,
                    detail=(
                        "Mouser Search API V2 did not provide a safe official "
                        "Product Detail handoff for the exact part"
                    ),
                ),
            )

        return CadDiscoveryResult(
            requested_source=self.name,
            status=CAD_MANUAL_DOWNLOAD_REQUIRED,
            request=request,
            provenance=provenance,
            action_required=CadActionRequired(
                code=CAD_MANUAL_DOWNLOAD_REQUIRED,
                detail=(
                    "Open the exact official Mouser product page, use its ECAD "
                    "Model and Library Loader flow with your own session, export "
                    "KiCad plus STEP or WRL, then rerun with the resulting package "
                    "via --cad-package"
                ),
                setup_url=handoff_url,
            ),
        )


def _safe_mouser_product_url(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").casefold()
        if (
            parsed.scheme.casefold() != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or not (hostname == "mouser.com" or hostname.endswith(".mouser.com"))
        ):
            return None
    except ValueError:
        return None

    segments = [segment.casefold() for segment in parsed.path.split("/") if segment]
    try:
        product_index = segments.index("productdetail")
    except ValueError:
        return None
    if len(segments) < product_index + 3:
        return None
    return sanitize_public_url(value)


__all__ = [
    "MouserCadSource",
    "MouserProductApi",
]
