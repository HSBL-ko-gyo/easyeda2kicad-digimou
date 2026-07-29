"""Policy-safe DigiKey Product Information V4 CAD-source discovery."""

from __future__ import annotations

# Global imports
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)
from urllib.parse import urljoin, urlsplit

# Local imports
from easyeda2kicad_digimou.metadata.cache import sanitize_public_url
from easyeda2kicad_digimou.metadata.models import (
    CAD_DOWNLOAD_UNAVAILABLE,
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CadActionRequired,
    CadDiscoveryResult,
    CadProvenance,
    CadRequest,
    CadSourceAvailability,
    DistributorRecord,
)
from easyeda2kicad_digimou.providers.base import InvalidResponseError, ProviderError


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


@dataclass(frozen=True)
class _DiscoveredLink:
    delivery_partner: str
    model_creator: Optional[str]
    artifact_kinds: Tuple[str, ...]
    url: str
    support_status: str


@dataclass(frozen=True)
class _DeliveryRule:
    delivery_partner: str
    hostnames: Tuple[str, ...]
    support_status: str


_DELIVERY_RULES = (
    _DeliveryRule(
        delivery_partner="ultralibrarian",
        hostnames=("ultralibrarian.com",),
        support_status="manual-handoff",
    ),
    _DeliveryRule(
        delivery_partner="snapmagic",
        hostnames=("snapeda.com", "snapmagic.com"),
        support_status="unsupported-interactive",
    ),
    _DeliveryRule(
        delivery_partner="samacsys",
        hostnames=("componentsearchengine.com",),
        support_status="unsupported-interactive",
    ),
    _DeliveryRule(
        delivery_partner="traceparts",
        hostnames=("traceparts.com",),
        support_status="unsupported-interactive",
    ),
)

_MANUFACTURER_NAME_NOISE = frozenset(
    (
        "and",
        "company",
        "co",
        "corporation",
        "corp",
        "formerly",
        "former",
        "inc",
        "incorporated",
        "limited",
        "ltd",
        "the",
    )
)
_GENERIC_MANUFACTURER_TOKENS = frozenset(
    (
        "components",
        "devices",
        "electronics",
        "group",
        "semiconductor",
        "semiconductors",
        "systems",
        "technologies",
        "technology",
    )
)


class DigiKeyCadSource:
    """Discover the actual product-specific CAD handoffs returned by DigiKey."""

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

        product_page = _digikey_product_page_url(record.product_url)
        model_page = _digikey_model_page_url(record.product_url)
        response = self._product_api.get_product_media(product_number)
        links = _product_cad_links(response, record)
        used_public_model_page = False
        public_page_getter = getattr(self._product_api, "get_public_model_page", None)
        if not links and model_page is not None and callable(public_page_getter):
            try:
                page_html = public_page_getter(model_page)
            except ProviderError:
                page_html = None
            if page_html is not None:
                links = _public_model_page_links(page_html, model_page, record)
                used_public_model_page = bool(links)
        sources = _source_availability(links)

        if not sources:
            handoff = model_page or product_page
            status = (
                CAD_MANUAL_DOWNLOAD_REQUIRED
                if handoff is not None
                else CAD_DOWNLOAD_UNAVAILABLE
            )
            detail = (
                "Open the exact DigiKey model page and review its product-specific "
                "official CAD sources; no delivery partner was identified by the "
                "Product Information V4 media response"
                if handoff is not None
                else (
                    "DigiKey Product Information V4 did not expose a supported, "
                    "product-specific CAD source for the exact part"
                )
            )
            return CadDiscoveryResult(
                requested_source=self.name,
                status=status,
                request=request,
                provenance=CadProvenance(
                    distributor="digikey",
                    delivery_partner=None,
                    model_creator=None,
                    landing_url=handoff,
                    retrieval_mode="official-api-product-model-handoff",
                ),
                action_required=CadActionRequired(
                    code=status,
                    detail=detail,
                    setup_url=handoff,
                ),
            )

        supported = [
            source
            for source in sources
            if source.support_status != "unsupported-interactive"
            and not (
                source.delivery_partner == "ultralibrarian"
                and len(source.source_urls) != 1
            )
        ]
        primary = sources[0] if len(sources) == 1 else None
        available_kinds = {kind for source in sources for kind in source.artifact_kinds}
        missing = sorted(
            {"symbol", "footprint", "model_3d"}.difference(available_kinds)
        )
        status = CAD_MANUAL_DOWNLOAD_REQUIRED if supported else CAD_DOWNLOAD_UNAVAILABLE
        landing_url = (
            primary.source_urls[0]
            if primary is not None and len(primary.source_urls) == 1
            else model_page or product_page
        )
        if supported:
            detail = (
                "Use the product-specific official handoff, review the provider "
                "terms, download only the available artifacts, and rerun with a "
                "hash-bound evidence file. Partial footprint/3D packages are "
                "accepted without inventing a missing symbol"
            )
        else:
            detail = (
                "DigiKey exposes official CAD handoffs for the exact part, but the "
                "identified sources are ambiguous or require an unsupported "
                "interactive flow"
            )
        return CadDiscoveryResult(
            requested_source=self.name,
            status=status,
            request=request,
            provenance=CadProvenance(
                distributor="digikey",
                delivery_partner=(
                    primary.delivery_partner if primary is not None else None
                ),
                model_creator=(primary.model_creator if primary is not None else None),
                landing_url=landing_url,
                retrieval_mode=(
                    "official-api-public-model-page-handoff"
                    if used_public_model_page
                    else "official-api-product-specific-handoff"
                ),
            ),
            action_required=CadActionRequired(
                code=status,
                detail=detail,
                setup_url=landing_url,
            ),
            available_sources=sources,
            missing_artifacts=missing,
        )


def _product_cad_links(
    response: Mapping[str, Any],
    record: DistributorRecord,
) -> List[_DiscoveredLink]:
    if not isinstance(response, Mapping):
        raise InvalidResponseError("digikey", operation="media-normalize")
    raw_links = response.get("MediaLinks")
    if not isinstance(raw_links, list):
        raise InvalidResponseError("digikey", operation="media-normalize")

    matches: List[_DiscoveredLink] = []
    for raw_link in raw_links:
        if not isinstance(raw_link, Mapping):
            raise InvalidResponseError("digikey", operation="media-normalize")
        media_type = raw_link.get("MediaType")
        if not isinstance(media_type, str) or not media_type.strip():
            raise InvalidResponseError("digikey", operation="media-normalize")
        title = raw_link.get("Title")
        if title is not None and not isinstance(title, str):
            raise InvalidResponseError("digikey", operation="media-normalize")
        description = "{0} {1}".format(media_type, title or "").strip()
        artifact_kinds = _artifact_kinds(description)
        relevant = bool(artifact_kinds) or media_type.strip().casefold() == "model"
        if not relevant:
            continue
        raw_url = raw_link.get("Url")
        if not isinstance(raw_url, str):
            raise InvalidResponseError("digikey", operation="media-normalize")
        safe_url = _safe_https_url(raw_url)
        if safe_url is None:
            raise InvalidResponseError("digikey", operation="media-normalize")
        partner, model_creator, support_status = _delivery_identity(
            safe_url,
            record,
            description,
        )
        if not artifact_kinds:
            artifact_kinds = (
                ("symbol", "footprint", "model_3d")
                if partner == "ultralibrarian"
                else ("model_3d",)
            )
        matches.append(
            _DiscoveredLink(
                delivery_partner=partner,
                model_creator=model_creator,
                artifact_kinds=tuple(sorted(set(artifact_kinds))),
                url=safe_url,
                support_status=support_status,
            )
        )
    return sorted(
        set(matches),
        key=lambda item: (
            _source_priority(item),
            item.delivery_partner,
            item.url,
        ),
    )


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: List[Tuple[str, str, str]] = []
        self._href: Optional[str] = None
        self._text: List[str] = []
        self._heading_tag: Optional[str] = None
        self._heading_text: List[str] = []
        self._current_heading = ""

    def handle_starttag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        normalized_tag = tag.casefold()
        if re.fullmatch(r"h[1-6]", normalized_tag):
            self._heading_tag = normalized_tag
            self._heading_text = []
            return
        if normalized_tag != "a" or self._href is not None:
            return
        attributes = {name.casefold(): value for name, value in attrs}
        href = attributes.get("href")
        if isinstance(href, str):
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._heading_tag is not None:
            self._heading_text.append(data)
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag == self._heading_tag:
            self._current_heading = " ".join("".join(self._heading_text).split())
            self._heading_tag = None
            self._heading_text = []
            return
        if normalized_tag != "a" or self._href is None:
            return
        text = " ".join("".join(self._text).split())
        self.anchors.append((self._href, text, self._current_heading))
        self._href = None
        self._text = []


def _public_model_page_links(
    page_html: Any,
    model_page_url: str,
    record: DistributorRecord,
) -> List[_DiscoveredLink]:
    if (
        not isinstance(page_html, str)
        or len(page_html.encode("utf-8")) > 2 * 1024 * 1024
    ):
        raise InvalidResponseError("digikey", operation="model-page-normalize")
    parser = _AnchorParser()
    try:
        parser.feed(page_html)
        parser.close()
    except (TypeError, ValueError):
        raise InvalidResponseError(
            "digikey",
            operation="model-page-normalize",
        ) from None
    requested_mpn = record.mpn
    if not isinstance(requested_mpn, str) or not requested_mpn.strip():
        raise InvalidResponseError("digikey", operation="model-page-identity")
    identity_pattern = re.compile(
        r"(?<![A-Za-z0-9]){0}(?![A-Za-z0-9])".format(re.escape(requested_mpn.strip())),
        re.IGNORECASE,
    )
    links: List[_DiscoveredLink] = []
    for raw_url, text, heading in parser.anchors:
        description = "{0} {1}".format(heading, text).strip()
        artifact_kinds = _artifact_kinds(description)
        if not artifact_kinds or identity_pattern.search(description) is None:
            continue
        safe_url = _safe_https_url(urljoin(model_page_url, raw_url))
        if safe_url is None:
            raise InvalidResponseError(
                "digikey",
                operation="model-page-normalize",
            )
        partner, model_creator, support_status = _delivery_identity(
            safe_url,
            record,
            description,
        )
        links.append(
            _DiscoveredLink(
                delivery_partner=partner,
                model_creator=model_creator,
                artifact_kinds=artifact_kinds,
                url=safe_url,
                support_status=support_status,
            )
        )
    return sorted(
        set(links),
        key=lambda item: (
            _source_priority(item),
            item.delivery_partner,
            item.url,
        ),
    )


def _source_availability(
    links: Sequence[_DiscoveredLink],
) -> List[CadSourceAvailability]:
    grouped: Dict[
        Tuple[str, Optional[str], str],
        Tuple[set[str], set[str]],
    ] = {}
    for link in links:
        key = (
            link.delivery_partner,
            link.model_creator,
            link.support_status,
        )
        kinds, urls = grouped.setdefault(key, (set(), set()))
        kinds.update(link.artifact_kinds)
        urls.add(link.url)
    sources = [
        CadSourceAvailability(
            delivery_partner=partner,
            model_creator=creator,
            artifact_kinds=sorted(kinds),
            source_urls=sorted(urls),
            support_status=support_status,
        )
        for (partner, creator, support_status), (kinds, urls) in grouped.items()
    ]
    return sorted(
        sources,
        key=lambda item: (
            0 if item.support_status == "local-package-supported" else 1,
            0 if item.delivery_partner != "ultralibrarian" else 1,
            item.delivery_partner,
        ),
    )


def _artifact_kinds(description: str) -> Tuple[str, ...]:
    normalized = description.casefold()
    kinds: List[str] = []
    if any(marker in normalized for marker in ("pcb footprint", "footprint")):
        kinds.append("footprint")
    if any(
        marker in normalized
        for marker in ("3d model", "3-d model", "step", "stp", "wrl", "vrml")
    ):
        kinds.append("model_3d")
    if any(marker in normalized for marker in ("schematic symbol", "symbol")):
        kinds.append("symbol")
    return tuple(kinds)


def _delivery_identity(
    value: str,
    record: DistributorRecord,
    description: str = "",
) -> Tuple[str, Optional[str], str]:
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()
    if hostname == "mm.digikey.com" and "/opasdata/" in path:
        return "ultralibrarian", None, "manual-handoff"
    for rule in _DELIVERY_RULES:
        if any(_hostname_matches(hostname, item) for item in rule.hostnames):
            return rule.delivery_partner, None, rule.support_status
    manufacturer = record.manufacturer or "manufacturer"
    if _manufacturer_link_is_proven(hostname, manufacturer, description):
        return manufacturer, manufacturer, "local-package-supported"
    return hostname, None, "manual-handoff"


def _hostname_matches(hostname: str, expected: str) -> bool:
    return hostname == expected or hostname.endswith("." + expected)


def _manufacturer_link_is_proven(
    hostname: str,
    manufacturer: str,
    description: str,
) -> bool:
    normalized_description = " ".join(description.casefold().split())
    if "manufacturer provided" in normalized_description or (
        "manufacturer" in normalized_description
        and any(
            marker in normalized_description
            for marker in ("cad", "eda", "footprint", "model", "symbol")
        )
    ):
        return True

    manufacturer_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", manufacturer.casefold())
        if token not in _MANUFACTURER_NAME_NOISE
    ]
    strong_tokens = [
        token
        for token in manufacturer_tokens
        if len(token) >= 5 and token not in _GENERIC_MANUFACTURER_TOKENS
    ]
    joined_names = [
        manufacturer_tokens[index] + manufacturer_tokens[index + 1]
        for index in range(len(manufacturer_tokens) - 1)
    ]
    compact_hostname = re.sub(r"[^a-z0-9]", "", hostname)
    return any(
        candidate in compact_hostname for candidate in (*strong_tokens, *joined_names)
    )


def _source_priority(link: _DiscoveredLink) -> int:
    if link.support_status == "local-package-supported":
        return 0
    if link.delivery_partner == "ultralibrarian":
        return 1
    return 2


def _ultralibrarian_model_urls(response: Mapping[str, Any]) -> List[str]:
    """Compatibility helper retained for callers that only need UL links."""

    placeholder = DistributorRecord(
        provider="digikey",
        manufacturer="manufacturer",
        mpn="placeholder",
    )
    return sorted(
        {
            link.url
            for link in _product_cad_links(response, placeholder)
            if link.delivery_partner == "ultralibrarian"
        }
    )


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


def _digikey_model_page_url(value: Optional[str]) -> Optional[str]:
    product_page = _digikey_product_page_url(value)
    if product_page is None:
        return None
    product_path = urlsplit(product_page).path.rstrip("/")
    match = re.search(r"/([1-9][0-9]*)$", product_path)
    if match is None:
        return None
    return "https://www.digikey.com/en/models/{0}".format(match.group(1))


__all__ = [
    "DigiKeyCadSource",
    "DigiKeyProductApi",
]
