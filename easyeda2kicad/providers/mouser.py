from __future__ import annotations

# Global imports
import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Tuple

from easyeda2kicad.metadata.models import DistributorRecord, PriceBreak, normalize_mpn

# Local imports
from .base import (
    AmbiguousMatchError,
    AuthFailedError,
    AuthMissingError,
    AuthRequirements,
    BaseMetadataProvider,
    InvalidResponseError,
    NotFoundError,
    identity_text,
    optional_float,
    optional_int,
    optional_text,
    parse_result_count,
)

MOUSER_SEARCH_URL = "https://api.mouser.com/api/v2/search/partnumberandmanufacturer"
MOUSER_AUTH_HELP_URL = "https://www.mouser.com/api-search/"


class MouserProvider(BaseMetadataProvider):
    name = "mouser"

    @staticmethod
    def _candidate_preference(record: DistributorRecord) -> Tuple[int, str]:
        """Select a stable public identifier, never a volatile sales term."""

        part_number = (record.distributor_part_number or "").strip()
        if part_number:
            return (0, part_number.casefold())
        return (1, (record.product_url or "").strip().casefold())

    def describe_auth_requirements(self) -> AuthRequirements:
        return AuthRequirements(
            required_environment_variables=("MOUSER_API_KEY",),
            help_url=MOUSER_AUTH_HELP_URL,
        )

    def _api_key(self) -> str:
        api_key = self._env.get("MOUSER_API_KEY", "").strip()
        if not api_key:
            raise AuthMissingError(self.name, operation="part-search")
        return api_key

    def _search_part_number(
        self, part_number: str, manufacturer: Optional[str] = None
    ) -> Dict[str, Any]:
        # The official endpoint requires the key in the query string.  The URL is
        # consequently never placed in an exception, cache request, or log entry.
        query = urllib.parse.urlencode({"apiKey": self._api_key()})
        url = "%s?%s" % (MOUSER_SEARCH_URL, query)
        body = json.dumps(
            {
                "SearchByPartMfrNameRequest": {
                    "manufacturerName": manufacturer or "",
                    "mouserPartNumber": part_number,
                    "partSearchOptions": "Exact",
                }
            },
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - fixed HTTPS endpoint
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        response = self._request_json(request, operation="part-search")
        if response.get("Errors"):
            error_text = str(response.get("Errors")).casefold()
            if any(
                marker in error_text
                for marker in (
                    "api key",
                    "apikey",
                    "unauthor",
                    "authenticat",
                    "credential",
                )
            ):
                raise AuthFailedError(self.name, operation="part-search")
            raise InvalidResponseError(self.name, operation="part-search")
        self.last_raw_response = response
        return response

    @staticmethod
    def _attributes(part: Mapping[str, Any]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        raw = part.get("ProductAttributes") or []
        if not isinstance(raw, list):
            return result
        for attribute in raw:
            if not isinstance(attribute, Mapping):
                continue
            name = optional_text(
                attribute.get("AttributeName") or attribute.get("Name")
            )
            value = optional_text(
                attribute.get("AttributeValue") or attribute.get("Value")
            )
            if name and value:
                normalized = "".join(
                    character for character in name.casefold() if character.isalnum()
                )
                result[normalized] = value
        return result

    @classmethod
    def _package(cls, part: Mapping[str, Any]) -> Optional[str]:
        attributes = cls._attributes(part)
        for name in (
            "packagecase",
            "casepackage",
            "supplierdevicepackage",
            "devicepackage",
        ):
            value = attributes.get(name)
            if value:
                return value
        return None

    @classmethod
    def _packaging(cls, part: Mapping[str, Any]) -> Optional[str]:
        attributes = cls._attributes(part)
        for name in ("packaging", "packagetype"):
            value = attributes.get(name)
            if value:
                return value
        reeling = part.get("Reeling")
        if reeling is True or (
            isinstance(reeling, str) and reeling.strip().casefold() == "true"
        ):
            return "Reel"
        return None

    @staticmethod
    def _lifecycle(part: Mapping[str, Any]) -> Optional[str]:
        discontinued = part.get("IsDiscontinued")
        if discontinued is True or (
            isinstance(discontinued, str) and discontinued.strip().casefold() == "true"
        ):
            return "Discontinued"
        return optional_text(part.get("LifecycleStatus"))

    @staticmethod
    def _stock(part: Mapping[str, Any]) -> Optional[int]:
        if part.get("AvailabilityInStock") is not None:
            return optional_int(part.get("AvailabilityInStock"))
        return optional_int(part.get("Availability"))

    def _retrieved_at(self) -> str:
        # Global imports
        from datetime import datetime, timezone

        return (
            datetime.fromtimestamp(self._clock(), timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _raw_part_mpn(part: Mapping[str, Any]) -> Any:
        return part.get("ManufacturerPartNumber")

    def _record_from_part(self, part: Mapping[str, Any]) -> Optional[DistributorRecord]:
        raw_mpn = part.get("ManufacturerPartNumber")
        raw_manufacturer = part.get("Manufacturer")
        if raw_mpn is None or raw_manufacturer is None:
            return None
        mpn = identity_text(raw_mpn, "ManufacturerPartNumber")
        manufacturer = identity_text(raw_manufacturer, "Manufacturer")

        price_breaks: List[PriceBreak] = []
        raw_prices = part.get("PriceBreaks") or []
        if not isinstance(raw_prices, list):
            raw_prices = []
        currency: Optional[str] = None
        for price in raw_prices:
            if not isinstance(price, Mapping):
                continue
            quantity = optional_int(price.get("Quantity"))
            unit_price = optional_float(
                price.get("Price")
                if price.get("Price") is not None
                else price.get("UnitPrice")
            )
            item_currency = optional_text(price.get("Currency"))
            if quantity is None or unit_price is None:
                continue
            if currency is None:
                currency = item_currency
            price_breaks.append(
                PriceBreak(
                    quantity=quantity,
                    unit_price=unit_price,
                    currency=item_currency,
                )
            )

        return DistributorRecord(
            provider=self.name,
            distributor_part_number=(
                identity_text(part["MouserPartNumber"], "MouserPartNumber")
                if part.get("MouserPartNumber") is not None
                else None
            ),
            product_url=optional_text(part.get("ProductDetailUrl")),
            manufacturer=manufacturer,
            mpn=mpn,
            description=optional_text(part.get("Description")),
            package=self._package(part),
            lifecycle=self._lifecycle(part),
            datasheet_url=optional_text(part.get("DataSheetUrl")),
            stock=self._stock(part),
            minimum_order_quantity=optional_int(part.get("Min")),
            packaging=self._packaging(part),
            currency=currency,
            price_breaks=price_breaks,
            retrieved_at=self._retrieved_at(),
        )

    def _parts(self, response: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        search_results = response.get("SearchResults")
        if search_results is None:
            raise InvalidResponseError(self.name, operation="normalize")
        if not isinstance(search_results, Mapping):
            raise InvalidResponseError(self.name, operation="normalize")
        try:
            parts = search_results["Parts"]
        except KeyError:
            raise InvalidResponseError(self.name, operation="normalize") from None
        if not isinstance(parts, list):
            raise InvalidResponseError(self.name, operation="normalize")
        result = [item for item in parts if isinstance(item, Mapping)]
        if len(result) != len(parts):
            raise InvalidResponseError(self.name, operation="normalize")
        try:
            count = parse_result_count(search_results["NumberOfResult"])
            if count is None:
                raise ValueError("missing NumberOfResult")
        except (KeyError, ValueError):
            raise InvalidResponseError(self.name, operation="normalize") from None
        if count < len(result):
            raise InvalidResponseError(self.name, operation="normalize")
        if count > len(result):
            raise AmbiguousMatchError(self.name, operation="part-search-truncated")
        return result

    def normalize_response(
        self, response: Mapping[str, Any]
    ) -> List[DistributorRecord]:
        if not isinstance(response, Mapping):
            raise InvalidResponseError(self.name, operation="normalize")
        parts = self._parts(response)
        records: List[DistributorRecord] = []
        for part in parts:
            try:
                record = self._record_from_part(part)
            except (TypeError, ValueError):
                raise InvalidResponseError(self.name, operation="normalize") from None
            if record is None:
                raise InvalidResponseError(self.name, operation="normalize")
            records.append(record)
        return records

    def _normalize_exact_response(
        self, response: Mapping[str, Any], requested_mpn: str
    ) -> List[DistributorRecord]:
        parts = self._parts(response)
        return self._normalize_exact_candidates(
            parts,
            requested_mpn,
            get_raw_mpn=self._raw_part_mpn,
            parse_record=self._record_from_part,
        )

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
        response = self._search_part_number(query_mpn, requested_manufacturer)
        return self.validate_exact_match(
            self._normalize_exact_response(response, requested_mpn),
            requested_manufacturer,
            requested_mpn,
        )

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord:
        try:
            requested_part_id = identity_text(part_id, "distributor_part_number")
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="distributor-id") from None
        response = self._search_part_number(requested_part_id)
        requested = requested_part_id.casefold()
        matches = [
            record
            for record in self.normalize_response(response)
            if (record.distributor_part_number or "").casefold() == requested
        ]
        if not matches:
            raise NotFoundError(self.name, operation="distributor-id")
        if len(matches) > 1:
            raise AmbiguousMatchError(self.name, operation="distributor-id")
        return matches[0]


__all__ = ["MOUSER_SEARCH_URL", "MouserProvider"]
