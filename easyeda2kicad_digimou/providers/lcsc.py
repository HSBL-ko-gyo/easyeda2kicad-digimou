from __future__ import annotations

# Global imports
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from easyeda2kicad_digimou.metadata.models import (
    DistributorRecord,
    PriceBreak,
    normalize_manufacturer,
    normalize_mpn,
)

# Local imports
from .base import (
    AmbiguousMatchError,
    AuthRequirements,
    BaseMetadataProvider,
    CacheCorruptError,
    InvalidResponseError,
    MpnMismatchError,
    NetworkError,
    NotFoundError,
    OfflineCacheMissError,
    identity_text,
    optional_float,
    optional_int,
    optional_text,
    parse_result_count,
)
from .lcsc_client import JlcpcbCatalogueClient


class LcscProvider(BaseMetadataProvider):
    """LCSC metadata adapter over the anonymous JLCPCB catalogue client."""

    name = "lcsc"
    page_size = 50
    max_pages = 10

    def __init__(
        self, api: Optional[JlcpcbCatalogueClient] = None, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.api = api if api is not None else JlcpcbCatalogueClient()

    def describe_auth_requirements(self) -> AuthRequirements:
        return AuthRequirements()

    def _retrieved_at(self) -> str:
        return (
            datetime.fromtimestamp(self._clock(), timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _raise_last_api_error(self, operation: str) -> None:
        error = getattr(self.api, "last_error", None)
        if error == "offline_cache_miss" or (
            getattr(self.api, "offline", False) and not error
        ):
            raise OfflineCacheMissError(self.name, operation=operation)
        if error == "cache_corrupt":
            raise CacheCorruptError(self.name, operation=operation)
        if error == "network_error":
            raise NetworkError(self.name, operation=operation)
        if error == "invalid_response":
            raise InvalidResponseError(self.name, operation=operation)
        if error == "not_found":
            raise NotFoundError(self.name, operation=operation)

    @staticmethod
    def _raw_results(response: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        results = response.get("results")
        if results is None:
            page_info = (
                (response.get("data") or {}).get("componentPageInfo")
                if isinstance(response.get("data"), Mapping)
                else None
            )
            if isinstance(page_info, Mapping):
                results = page_info.get("list")
        if results is None:
            return []
        if not isinstance(results, list):
            raise InvalidResponseError("lcsc", operation="normalize")
        mappings = [item for item in results if isinstance(item, Mapping)]
        if len(mappings) != len(results):
            raise InvalidResponseError("lcsc", operation="normalize")
        return mappings

    @staticmethod
    def _raw_item_mpn(item: Mapping[str, Any]) -> Any:
        return _first_present(item, "model", "componentModelEn")

    def _record_from_search_item(
        self, item: Mapping[str, Any]
    ) -> Optional[DistributorRecord]:
        # Accept both EasyedaApi's stable adapter keys and the upstream JLCPCB
        # response keys so cached raw responses can be normalized as well.
        raw_mpn = _first_present(item, "model", "componentModelEn")
        # Prefer the part-scoped English catalogue name when both the upstream
        # field and the adapter's localized display value are available.
        raw_manufacturer = _first_present(item, "componentBrandEn", "brand")
        if raw_mpn is None or raw_manufacturer is None:
            return None
        mpn = identity_text(raw_mpn, "manufacturer_part_number")
        manufacturer = identity_text(raw_manufacturer, "manufacturer")
        raw_lcsc_number = _first_present(item, "lcsc", "componentCode")
        if raw_lcsc_number is None:
            return None
        lcsc_number = identity_text(raw_lcsc_number, "lcsc_part_number")
        product_url = optional_text(item.get("url") or item.get("lcscGoodsUrl"))
        if not product_url and lcsc_number:
            product_url = "https://www.lcsc.com/product-detail/%s.html" % lcsc_number

        prices = item.get("price_breaks")
        if prices is None:
            prices = item.get("componentPrices")
        if not isinstance(prices, list):
            prices = []
        price_breaks: List[PriceBreak] = []
        for price in prices:
            if not isinstance(price, Mapping):
                continue
            quantity = optional_int(
                price.get("qty")
                if price.get("qty") is not None
                else price.get("startNumber")
            )
            unit_price = optional_float(
                price.get("price")
                if price.get("price") is not None
                else price.get("productPrice")
            )
            if quantity is None or unit_price is None:
                continue
            price_breaks.append(PriceBreak(quantity=quantity, unit_price=unit_price))

        stock_value = (
            item.get("stock")
            if item.get("stock") is not None
            else item.get("stockCount")
        )
        minimum_value = (
            item.get("min_qty")
            if item.get("min_qty") is not None
            else item.get("minPurchaseNum")
        )
        reel_value = (
            item.get("reel_qty")
            if item.get("reel_qty") is not None
            else item.get("encapsulationNumber")
        )
        return DistributorRecord(
            provider=self.name,
            distributor_part_number=lcsc_number,
            product_url=product_url,
            manufacturer=manufacturer,
            mpn=mpn,
            description=optional_text(
                item.get("description")
                or item.get("describe")
                or item.get("name")
                or item.get("componentName")
            ),
            package=optional_text(
                item.get("package") or item.get("componentSpecificationEn")
            ),
            datasheet_url=optional_text(
                item.get("datasheet") or item.get("dataManualUrl")
            ),
            stock=optional_int(stock_value),
            minimum_order_quantity=optional_int(minimum_value),
            packaging="Reel" if optional_int(reel_value) else None,
            price_breaks=price_breaks,
            retrieved_at=self._retrieved_at(),
        )

    def normalize_response(
        self, response: Mapping[str, Any]
    ) -> List[DistributorRecord]:
        if not isinstance(response, Mapping):
            raise InvalidResponseError(self.name, operation="normalize")
        items = self._raw_results(response)
        records: List[DistributorRecord] = []
        for item in items:
            try:
                record = self._record_from_search_item(item)
            except (TypeError, ValueError):
                raise InvalidResponseError(self.name, operation="normalize") from None
            if record is None:
                raise InvalidResponseError(self.name, operation="normalize")
            records.append(record)
        return records

    def _normalize_exact_response(
        self, response: Mapping[str, Any], requested_mpn: str
    ) -> List[DistributorRecord]:
        items = self._raw_results(response)
        return self._normalize_exact_candidates(
            items,
            requested_mpn,
            get_raw_mpn=self._raw_item_mpn,
            parse_record=self._record_from_search_item,
        )

    @staticmethod
    def _response_total(response: Mapping[str, Any]) -> Optional[int]:
        raw_totals: List[Any] = []
        if response.get("total") is not None:
            raw_totals.append(response.get("total"))
        data = response.get("data")
        if isinstance(data, Mapping):
            page_info = data.get("componentPageInfo")
            if isinstance(page_info, Mapping) and page_info.get("total") is not None:
                raw_totals.append(page_info.get("total"))
        try:
            totals = [parse_result_count(value) for value in raw_totals]
        except ValueError:
            raise InvalidResponseError("lcsc", operation="search") from None
        parsed = [value for value in totals if value is not None]
        if len(set(parsed)) > 1:
            raise InvalidResponseError("lcsc", operation="search")
        return parsed[0] if parsed else None

    def _search_all(
        self, keyword: str, *, requested_mpn: Optional[str] = None
    ) -> List[DistributorRecord]:
        records: List[DistributorRecord] = []
        raw_pages: List[Dict[str, Any]] = []
        total: Optional[int] = None
        seen_items = 0
        for page in range(1, self.max_pages + 1):
            response = self.api.search_jlcpcb_components(
                keyword,
                page=page,
                page_size=self.page_size,
            )
            if not isinstance(response, Mapping):
                raise InvalidResponseError(self.name, operation="search")
            raw_pages.append(dict(response))
            self.last_raw_response = {"pages": raw_pages}
            page_total = self._response_total(response)
            if page == 1:
                total = page_total
            elif page_total != total:
                # All pages must represent one consistent result snapshot.
                raise InvalidResponseError(self.name, operation="search")
            page_records = (
                self._normalize_exact_response(response, requested_mpn)
                if requested_mpn is not None
                else self.normalize_response(response)
            )
            records.extend(page_records)
            raw_results = self._raw_results(response)
            seen_items += len(raw_results)
            if page == 1:
                if total is not None and total > self.page_size * self.max_pages:
                    # A locally exact record cannot be selected while additional
                    # exact LCSC IDs may exist beyond the bounded scan.
                    raise AmbiguousMatchError(self.name, operation="search-truncated")
                if total == 0 and raw_results:
                    raise InvalidResponseError(self.name, operation="search")
            if total is not None and seen_items > total:
                raise InvalidResponseError(self.name, operation="search")
            if not raw_results:
                self._raise_last_api_error("search")
                if total is not None and seen_items < total:
                    raise AmbiguousMatchError(self.name, operation="search-truncated")
                break
            if total is not None and seen_items >= total:
                break
            if total is None and len(raw_results) < self.page_size:
                break
            if total is None and page == self.max_pages:
                raise AmbiguousMatchError(self.name, operation="search-truncated")

        if total is not None and seen_items < total:
            raise AmbiguousMatchError(self.name, operation="search-truncated")

        if not records:
            self._raise_last_api_error("search")
        return records

    def validate_exact_match(
        self,
        candidates: Sequence[DistributorRecord],
        manufacturer: Optional[str],
        mpn: str,
    ) -> DistributorRecord:
        try:
            requested_mpn = normalize_mpn(identity_text(mpn, "mpn"))
            requested_manufacturer = normalize_manufacturer(
                identity_text(manufacturer, "manufacturer")
                if manufacturer is not None
                else None
            )
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="exact-match") from None
        exact_mpn = [
            candidate
            for candidate in candidates
            if candidate.mpn and normalize_mpn(candidate.mpn) == requested_mpn
        ]
        exact = [
            candidate
            for candidate in exact_mpn
            if (
                not requested_manufacturer
                or normalize_manufacturer(candidate.manufacturer)
                == requested_manufacturer
            )
        ]
        if not exact:
            if requested_manufacturer and exact_mpn:
                raise MpnMismatchError(self.name, operation="manufacturer-exact-match")
            raise NotFoundError(self.name, operation="exact-match")
        lcsc_ids = {
            (candidate.distributor_part_number or "").strip().casefold()
            for candidate in exact
        }
        identities = {
            (
                normalize_manufacturer(candidate.manufacturer),
                normalize_mpn(candidate.mpn),
            )
            for candidate in exact
        }
        if len(lcsc_ids) != 1 or len(identities) != 1:
            raise AmbiguousMatchError(self.name, operation="exact-match")
        return sorted(exact, key=self._candidate_preference)[0]

    def search_exact_mpn(
        self, manufacturer: Optional[str], mpn: str
    ) -> DistributorRecord:
        try:
            requested_mpn = identity_text(mpn, "mpn")
            requested_manufacturer = (
                identity_text(manufacturer, "manufacturer")
                if manufacturer is not None
                else None
            )
            query_mpn = normalize_mpn(requested_mpn)
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="exact-query") from None
        if not query_mpn:
            raise InvalidResponseError(self.name, operation="exact-query")
        return self.validate_exact_match(
            self._search_all(query_mpn, requested_mpn=requested_mpn),
            requested_manufacturer,
            requested_mpn,
        )

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord:
        # Distributor identity is resolved only through the anonymous catalogue.
        # EasyEDA CAD is a separate trust boundary owned by EasyedaProvider.
        try:
            requested = identity_text(part_id, "distributor_part_number")
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="distributor-id") from None
        if not re.fullmatch(r"C[1-9][0-9]*", requested):
            raise InvalidResponseError(self.name, operation="distributor-id")
        matches = [
            record
            for record in self._search_all(requested)
            if (record.distributor_part_number or "").strip() == requested
        ]
        if not matches:
            raise NotFoundError(self.name, operation="distributor-id")
        if len(matches) > 1:
            raise AmbiguousMatchError(self.name, operation="distributor-id")
        return matches[0]


LCSCProvider = LcscProvider


def _first_present(mapping: Mapping[str, Any], *field_names: str) -> Any:
    for field_name in field_names:
        if field_name in mapping and mapping[field_name] is not None:
            return mapping[field_name]
    return None


__all__ = ["LCSCProvider", "LcscProvider"]
