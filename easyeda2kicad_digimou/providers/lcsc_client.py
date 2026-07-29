"""Anonymous JLCPCB catalogue transport, independent of EasyEDA CAD."""

from __future__ import annotations

# Global imports
import gzip
import json
import logging
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Tuple

JLCPCB_SEARCH_API = (
    "https://jlcpcb.com/api/overseas-pcb-order/v1/"
    "shoppingCart/smtGood/selectSmtComponentList"
)


def _validated_page(
    response: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], List[Mapping[str, Any]]]:
    data = response.get("data")
    page_info = data.get("componentPageInfo") if isinstance(data, Mapping) else None
    if not isinstance(page_info, Mapping):
        raise ValueError("missing componentPageInfo")
    raw_items = page_info.get("list")
    if raw_items is None:
        raw_items = []
    if not isinstance(raw_items, list):
        raise ValueError("catalogue list must be an array")
    items = [item for item in raw_items if isinstance(item, Mapping)]
    if len(items) != len(raw_items):
        raise ValueError("catalogue items must be objects")
    for item in items:
        for field_name in ("componentPrices", "attributes"):
            nested = item.get(field_name)
            if nested is None:
                continue
            if not isinstance(nested, list) or any(
                not isinstance(entry, Mapping) for entry in nested
            ):
                raise ValueError("catalogue nested values must be object arrays")
    return page_info, items


def adapt_catalogue_response(response: Mapping[str, Any]) -> Dict[str, Any]:
    """Map one validated official response for the legacy EasyedaApi facade."""

    page_info, items = _validated_page(response)
    results: List[Dict[str, Any]] = []
    for item in items:
        raw_prices = item.get("componentPrices")
        prices = [] if raw_prices is None else raw_prices
        raw_attributes = item.get("attributes")
        attributes = [] if raw_attributes is None else raw_attributes
        results.append(
            {
                "lcsc": item.get("componentCode", ""),
                "name": item.get("componentName", ""),
                "model": item.get("componentModelEn", ""),
                "brand": item.get("componentBrand", "")
                or item.get("componentBrandEn", ""),
                "componentBrandEn": item.get("componentBrandEn", ""),
                "package": item.get("componentSpecificationEn", ""),
                "category": item.get("componentTypeEn", ""),
                "stock": item.get("stockCount", 0),
                "type": (
                    "Basic"
                    if item.get("componentLibraryType") == "base"
                    else "Extended"
                ),
                "price": prices[0].get("productPrice") if prices else None,
                "price_breaks": [
                    {
                        "qty": price.get("startNumber"),
                        "price": price.get("productPrice"),
                    }
                    for price in prices
                ],
                "min_qty": item.get("minPurchaseNum", 1),
                "reel_qty": item.get("encapsulationNumber"),
                "description": item.get("describe", ""),
                "url": item.get("lcscGoodsUrl", ""),
                "datasheet": item.get("dataManualUrl", ""),
                "attributes": [
                    {
                        "name": attribute.get("attribute_name_en", ""),
                        "value": attribute["attribute_value_name"],
                    }
                    for attribute in attributes
                    if attribute.get("attribute_value_name")
                    and attribute["attribute_value_name"] != "-"
                ],
            }
        )
    return {"total": page_info.get("total", 0), "results": results}


class JlcpcbCatalogueClient:
    """Small official catalogue client with no CAD or credential responsibility."""

    def __init__(
        self,
        *,
        offline: bool = False,
        ssl_context: Optional[ssl.SSLContext] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.offline = offline
        self.ssl_context = ssl_context or ssl.create_default_context()
        self.headers = {
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "User-Agent": "easyeda2kicad-digimou catalogue client",
            **dict(headers or {}),
        }
        self.last_error: Optional[str] = None

    @staticmethod
    def _decode(raw: bytes) -> str:
        if raw[:2] == b"\x1f\x8b":
            return gzip.decompress(raw).decode("utf-8")
        return raw.decode("utf-8")

    def search_jlcpcb_components(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 10,
        part_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return one validated official response page without normalization."""

        self.last_error = None
        if self.offline:
            self.last_error = "offline_cache_miss"
            return {}
        payload: Dict[str, Any] = {
            "keyword": keyword,
            "currentPage": page,
            "pageSize": page_size,
        }
        if part_type:
            payload["componentLibraryType"] = part_type
        request = urllib.request.Request(  # noqa: S310
            url=JLCPCB_SEARCH_API,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                **self.headers,
                "Content-Type": "application/json",
                "Origin": "https://jlcpcb.com",
                "Referer": "https://jlcpcb.com/parts",
            },
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=15, context=self.ssl_context
            ) as response:
                decoded = self._decode(response.read())
            raw = json.loads(decoded)
        except (urllib.error.URLError, OSError) as error:
            self.last_error = "network_error"
            logging.error("JLCPCB catalogue request failed: %s", type(error).__name__)
            return {}
        except (json.JSONDecodeError, UnicodeError, TypeError) as error:
            self.last_error = "invalid_response"
            logging.error("JLCPCB catalogue response invalid: %s", type(error).__name__)
            return {}
        if not isinstance(raw, Mapping):
            self.last_error = "invalid_response"
            return {}
        try:
            page_info, items = _validated_page(raw)
        except ValueError:
            self.last_error = "invalid_response"
            return {}
        if not items and page_info.get("total", 0) == 0:
            self.last_error = "not_found"
        return dict(raw)


__all__ = ["JLCPCB_SEARCH_API", "JlcpcbCatalogueClient", "adapt_catalogue_response"]
