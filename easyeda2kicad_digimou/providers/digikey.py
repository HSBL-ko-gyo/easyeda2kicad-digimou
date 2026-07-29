from __future__ import annotations

# Global imports
import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from easyeda2kicad_digimou.metadata.models import (
    DistributorRecord,
    PriceBreak,
    normalize_mpn,
)

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

DIGIKEY_TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"  # noqa: S105
DIGIKEY_KEYWORD_SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"
DIGIKEY_MEDIA_URL_TEMPLATE = (
    "https://api.digikey.com/products/v4/search/{product_number}/media"
)
DIGIKEY_AUTH_HELP_URL = (
    "https://developer.digikey.com/tutorials-and-resources/oauth-20-2-legged-flow"
)


class DigiKeyProvider(BaseMetadataProvider):
    name = "digikey"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._access_token: Optional[str] = None
        self._access_token_expires_at = 0.0

    def describe_auth_requirements(self) -> AuthRequirements:
        return AuthRequirements(
            required_environment_variables=(
                "DIGIKEY_CLIENT_ID",
                "DIGIKEY_CLIENT_SECRET",
            ),
            optional_environment_variables=(
                "DIGIKEY_LOCALE_SITE",
                "DIGIKEY_LOCALE_LANGUAGE",
                "DIGIKEY_LOCALE_CURRENCY",
            ),
            help_url=DIGIKEY_AUTH_HELP_URL,
        )

    @staticmethod
    def _candidate_preference(record: DistributorRecord) -> Tuple[int, str]:
        """Select a stable public identifier, never a volatile sales term."""

        part_number = (record.distributor_part_number or "").strip()
        if part_number:
            return (0, part_number.casefold())
        return (1, (record.product_url or "").strip().casefold())

    def _credentials(self) -> Tuple[str, str]:
        client_id = self._env.get("DIGIKEY_CLIENT_ID", "").strip()
        client_secret = self._env.get("DIGIKEY_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise AuthMissingError(self.name, operation="oauth")
        if "\r" in client_id or "\n" in client_id:
            raise AuthFailedError(self.name, operation="oauth")
        return client_id, client_secret

    def _locale(self) -> Tuple[str, str, str]:
        site = self._env.get("DIGIKEY_LOCALE_SITE", "US").strip() or "US"
        language = self._env.get("DIGIKEY_LOCALE_LANGUAGE", "en").strip() or "en"
        currency = self._env.get("DIGIKEY_LOCALE_CURRENCY", "USD").strip() or "USD"
        if any("\r" in value or "\n" in value for value in (site, language, currency)):
            raise InvalidResponseError(self.name, operation="locale")
        return site, language, currency

    def get_cache_context(self) -> Mapping[str, str]:
        site, language, currency = self._locale()
        return {
            "site": site,
            "language": language,
            "currency": currency,
        }

    def _get_access_token(self, client_id: str, client_secret: str) -> str:
        if self._access_token and self._clock() < self._access_token_expires_at:
            return self._access_token

        body = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - fixed HTTPS endpoint
            DIGIKEY_TOKEN_URL,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        response = self._request_json(
            request,
            operation="oauth",
            auth_statuses=(400, 401, 403),
        )
        token = response.get("access_token")
        expires_in = optional_int(response.get("expires_in"))
        if response.get("error"):
            raise AuthFailedError(self.name, operation="oauth")
        if not isinstance(token, str) or not token.strip() or expires_in is None:
            raise InvalidResponseError(self.name, operation="oauth")
        if any(character.isspace() for character in token.strip()):
            raise InvalidResponseError(self.name, operation="oauth")

        # Refresh a little early; neither token nor secret is copied elsewhere.
        lifetime = max(0, expires_in - 30)
        self._access_token = token.strip()
        self._access_token_expires_at = self._clock() + lifetime
        return self._access_token

    def _search_keyword(self, keyword: str) -> Dict[str, Any]:
        client_id, client_secret = self._credentials()
        token = self._get_access_token(client_id, client_secret)
        site, language, currency = self._locale()
        body = json.dumps(
            {
                "Keywords": keyword,
                "RecordCount": 50,
                "RecordStartPosition": 0,
                "ExcludeMarketPlaceProducts": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(  # noqa: S310 - fixed HTTPS endpoint
            DIGIKEY_KEYWORD_SEARCH_URL,
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer %s" % token,
                "Content-Type": "application/json",
                "X-DIGIKEY-Client-Id": client_id,
                "X-DIGIKEY-Locale-Site": site,
                "X-DIGIKEY-Locale-Language": language,
                "X-DIGIKEY-Locale-Currency": currency,
            },
            method="POST",
        )
        response = self._request_json(request, operation="keyword-search")
        if response.get("Errors"):
            error_text = str(response.get("Errors")).casefold()
            if any(
                marker in error_text
                for marker in ("unauthor", "authenticat", "credential", "token")
            ):
                raise AuthFailedError(self.name, operation="keyword-search")
            raise InvalidResponseError(self.name, operation="keyword-search")
        self.last_raw_response = response
        return response

    def get_product_media(self, product_number: str) -> Dict[str, Any]:
        """Return official Product Information V4 media without retaining it."""

        try:
            exact_product_number = identity_text(
                product_number, "distributor_part_number"
            )
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="media-query") from None
        client_id, client_secret = self._credentials()
        token = self._get_access_token(client_id, client_secret)
        site, language, currency = self._locale()
        encoded_product_number = urllib.parse.quote(exact_product_number, safe="")
        request = urllib.request.Request(  # noqa: S310 - fixed HTTPS endpoint
            DIGIKEY_MEDIA_URL_TEMPLATE.format(product_number=encoded_product_number),
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer %s" % token,
                "X-DIGIKEY-Client-Id": client_id,
                "X-DIGIKEY-Locale-Site": site,
                "X-DIGIKEY-Locale-Language": language,
                "X-DIGIKEY-Locale-Currency": currency,
            },
            method="GET",
        )
        response = self._request_json(request, operation="media")
        if response.get("Errors"):
            error_text = str(response.get("Errors")).casefold()
            if any(
                marker in error_text
                for marker in ("unauthor", "authenticat", "credential", "token")
            ):
                raise AuthFailedError(self.name, operation="media")
            raise InvalidResponseError(self.name, operation="media")
        # Unlike exact metadata lookup, CAD discovery responses are never
        # retained on the provider where callers might persist them as raw
        # cache evidence.
        return response

    @staticmethod
    def _identity_from(value: Mapping[str, Any], *field_names: str) -> Optional[str]:
        for field_name in field_names:
            if field_name in value and value[field_name] is not None:
                return identity_text(value[field_name], field_name)
        return None

    @staticmethod
    def _manufacturer(product: Mapping[str, Any]) -> Optional[str]:
        value = product.get("Manufacturer")
        if isinstance(value, Mapping):
            return DigiKeyProvider._identity_from(value, "Name")
        if value is None:
            return None
        return identity_text(value, "Manufacturer")

    @staticmethod
    def _description(product: Mapping[str, Any]) -> Optional[str]:
        value = product.get("Description")
        if isinstance(value, Mapping):
            return optional_text(
                value.get("ProductDescription") or value.get("DetailedDescription")
            )
        return optional_text(value or product.get("DetailedDescription"))

    @staticmethod
    def _package(product: Mapping[str, Any]) -> Optional[str]:
        parameters = product.get("Parameters") or []
        if not isinstance(parameters, list):
            return None
        fallback: Optional[str] = None
        for parameter in parameters:
            if not isinstance(parameter, Mapping):
                continue
            name = optional_text(
                parameter.get("ParameterText") or parameter.get("ParameterName")
            )
            value = optional_text(parameter.get("ValueText") or parameter.get("Value"))
            if not name or not value:
                continue
            normalized = "".join(
                character for character in name.casefold() if character.isalnum()
            )
            if normalized in ("packagecase", "casepackage"):
                return value
            if normalized in ("supplierdevicepackage", "devicepackage"):
                fallback = value
        return fallback

    @staticmethod
    def _variations(product: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        raw = product.get("ProductVariations") or []
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, Mapping)]

    @staticmethod
    def _variation_part_number(variation: Mapping[str, Any]) -> Optional[str]:
        return DigiKeyProvider._identity_from(
            variation,
            "DigiKeyProductNumber",
            "DKPartNumber",
            "ProductNumber",
        )

    @classmethod
    def _variation_preference(cls, variation: Mapping[str, Any]) -> Tuple[str, str]:
        part_number = cls._variation_part_number(variation) or ""
        return (part_number.casefold(), part_number)

    @classmethod
    def _selected_variation(
        cls,
        product: Mapping[str, Any],
        variations: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> Mapping[str, Any]:
        choices = (
            list(variations) if variations is not None else cls._variations(product)
        )
        identified_choices = [
            variation
            for variation in choices
            if cls._variation_part_number(variation) is not None
        ]
        if not identified_choices:
            # The product-level record is the deterministic fallback when the
            # API supplies no stable distributor identifier for its variations.
            return product
        return sorted(identified_choices, key=cls._variation_preference)[0]

    @staticmethod
    def _raw_product_mpn(product: Mapping[str, Any]) -> Any:
        for field_name in (
            "ManufacturerProductNumber",
            "ManufacturerPartNumber",
        ):
            if field_name in product and product[field_name] is not None:
                return product[field_name]
        return None

    @staticmethod
    def _packaging(variation: Mapping[str, Any]) -> Optional[str]:
        value = variation.get("PackageType")
        if isinstance(value, Mapping):
            return optional_text(value.get("Name"))
        return optional_text(value or variation.get("Packaging"))

    @staticmethod
    def _lifecycle(product: Mapping[str, Any]) -> Optional[str]:
        if product.get("EndOfLife") is True:
            return "End of Life"
        if product.get("Discontinued") is True:
            return "Discontinued"
        value = product.get("ProductStatus")
        if isinstance(value, Mapping):
            return optional_text(value.get("Status") or value.get("Name"))
        return optional_text(value)

    def _record_from_product(
        self,
        product: Mapping[str, Any],
        variations: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> Optional[DistributorRecord]:
        mpn = self._identity_from(
            product,
            "ManufacturerProductNumber",
            "ManufacturerPartNumber",
        )
        manufacturer = self._manufacturer(product)
        if not mpn or not manufacturer:
            return None

        variation = self._selected_variation(product, variations)
        site, language, requested_currency = self._locale()
        del site, language
        price_breaks: List[PriceBreak] = []
        pricing = variation.get("StandardPricing") or []
        if not isinstance(pricing, list):
            pricing = []
        record_currency: Optional[str] = requested_currency
        for price in pricing:
            if not isinstance(price, Mapping):
                continue
            quantity_value = price.get("BreakQuantity")
            if quantity_value is None:
                quantity_value = price.get("Quantity")
            unit_price_value = price.get("UnitPrice")
            if unit_price_value is None:
                unit_price_value = price.get("Price")
            quantity = optional_int(quantity_value)
            unit_price = optional_float(unit_price_value)
            currency = optional_text(price.get("Currency")) or requested_currency
            if quantity is None or unit_price is None:
                continue
            record_currency = currency
            price_breaks.append(
                PriceBreak(
                    quantity=quantity,
                    unit_price=unit_price,
                    currency=currency,
                )
            )

        stock_value = variation.get("QuantityAvailableforPackageType")
        if stock_value is None:
            stock_value = variation.get("QuantityAvailableForPackageType")
        if stock_value is None:
            stock_value = product.get("QuantityAvailable")
        stock = optional_int(stock_value)
        part_number = self._variation_part_number(variation) or self._identity_from(
            product, "DigiKeyProductNumber"
        )
        return DistributorRecord(
            provider=self.name,
            distributor_part_number=part_number,
            product_url=optional_text(product.get("ProductUrl")),
            manufacturer=manufacturer,
            mpn=mpn,
            description=self._description(product),
            package=self._package(product),
            lifecycle=self._lifecycle(product),
            datasheet_url=optional_text(product.get("DatasheetUrl")),
            stock=stock,
            minimum_order_quantity=optional_int(variation.get("MinimumOrderQuantity")),
            packaging=self._packaging(variation),
            currency=record_currency,
            price_breaks=price_breaks,
            retrieved_at=self._retrieved_at(),
        )

    def _retrieved_at(self) -> str:
        # Avoid a dependency on third-party date libraries and retain UTC ordering.
        # Global imports
        from datetime import datetime, timezone

        return (
            datetime.fromtimestamp(self._clock(), timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _products(
        self, response: Mapping[str, Any], *, deduplicate: bool = True
    ) -> List[Mapping[str, Any]]:
        products: List[Mapping[str, Any]] = []
        malformed_container = False
        has_result_container = False
        for key in ("Products", "ExactMatches"):
            if key not in response:
                continue
            has_result_container = True
            raw = response[key]
            if not isinstance(raw, list):
                malformed_container = True
                continue
            mappings = [item for item in raw if isinstance(item, Mapping)]
            if len(mappings) != len(raw):
                malformed_container = True
            products.extend(mappings)
        if malformed_container or not has_result_container:
            raise InvalidResponseError(self.name, operation="normalize")

        # The same product can occur in ExactMatches and Products.
        unique: List[Mapping[str, Any]] = []
        seen = set()
        for index, product in enumerate(products):
            marker: Tuple[Any, ...]
            try:
                marker = (
                    "identity",
                    self._identity_from(
                        product,
                        "ManufacturerProductNumber",
                        "ManufacturerPartNumber",
                    ),
                    self._manufacturer(product),
                    optional_text(product.get("ProductUrl")),
                )
            except (TypeError, ValueError):
                # Count this raw item without parsing fields unrelated to the
                # exact-MPN relation. The exact-aware boundary below decides
                # whether the malformed item is relevant to the query.
                marker = ("raw-candidate", index)
            if marker in seen:
                continue
            seen.add(marker)
            unique.append(product)
        try:
            total = parse_result_count(response["ProductsCount"])
            if total is None:
                raise ValueError("missing ProductsCount")
        except (KeyError, ValueError):
            raise InvalidResponseError(self.name, operation="normalize") from None
        if total < len(unique):
            raise InvalidResponseError(self.name, operation="normalize")
        if total > len(unique):
            raise AmbiguousMatchError(self.name, operation="keyword-search-truncated")
        return unique if deduplicate else products

    def normalize_response(
        self, response: Mapping[str, Any]
    ) -> List[DistributorRecord]:
        if not isinstance(response, Mapping):
            raise InvalidResponseError(self.name, operation="normalize")
        try:
            products = self._products(response)
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="normalize") from None
        records: List[DistributorRecord] = []
        for product in products:
            try:
                record = self._record_from_product(product)
            except (TypeError, ValueError):
                raise InvalidResponseError(self.name, operation="normalize") from None
            if record is None:
                raise InvalidResponseError(self.name, operation="normalize")
            records.append(record)
        return records

    def _normalize_exact_response(
        self, response: Mapping[str, Any], requested_mpn: str
    ) -> List[DistributorRecord]:
        try:
            products = self._products(response, deduplicate=False)
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="normalize") from None
        return self._normalize_exact_candidates(
            products,
            requested_mpn,
            get_raw_mpn=self._raw_product_mpn,
            parse_record=self._record_from_product,
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
        response = self._search_keyword(query_mpn)
        return self.validate_exact_match(
            self._normalize_exact_response(response, requested_mpn),
            requested_manufacturer,
            requested_mpn,
        )

    def get_part_by_distributor_id(self, part_id: str) -> DistributorRecord:
        try:
            requested_part_id = identity_text(part_id, "distributor_part_number")
            response = self._search_keyword(requested_part_id)
            products = self._products(response)
            requested = requested_part_id.casefold()
            records: List[DistributorRecord] = []
            for product in products:
                matching_variations = [
                    variation
                    for variation in self._variations(product)
                    if (self._variation_part_number(variation) or "").casefold()
                    == requested
                ]
                top_level_match = (
                    self._identity_from(product, "DigiKeyProductNumber") or ""
                ).casefold() == requested
                if matching_variations:
                    record = self._record_from_product(product, matching_variations)
                elif top_level_match:
                    record = self._record_from_product(product)
                else:
                    record = None
                if record is not None:
                    records.append(record)
        except (TypeError, ValueError):
            raise InvalidResponseError(self.name, operation="distributor-id") from None
        if not records:
            raise NotFoundError(self.name, operation="distributor-id")
        if len(records) > 1:
            raise AmbiguousMatchError(self.name, operation="distributor-id")
        return records[0]


__all__ = [
    "DIGIKEY_KEYWORD_SEARCH_URL",
    "DIGIKEY_MEDIA_URL_TEMPLATE",
    "DIGIKEY_TOKEN_URL",
    "DigiKeyProvider",
]
