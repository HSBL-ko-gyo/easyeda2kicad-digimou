"""Stable metadata projection for KiCad symbol properties."""

from __future__ import annotations

# Global imports
from collections import OrderedDict
from typing import Dict, Mapping, Optional
from urllib.parse import parse_qsl, urlsplit

# Local imports
from .cache import sanitize_public_url
from .models import DistributorRecord, MergedPart

NATIVE_SYMBOL_FIELDS = ("Manufacturer", "MPN", "LCSC Part", "Datasheet")
CUSTOM_SYMBOL_FIELD_ORDER: tuple[str, ...] = ()
RESERVED_METADATA_FIELDS = frozenset(NATIVE_SYMBOL_FIELDS + CUSTOM_SYMBOL_FIELD_ORDER)


def build_symbol_fields(merged: MergedPart) -> Dict[str, str]:
    """Return metadata-only custom fields safe to persist in a KiCad symbol.

    All supported stable identity values use the exporter's existing native
    Manufacturer/MPN/LCSC/Datasheet properties. Provider, provenance, CAD
    status, package/lifecycle, URL, and sales data remain manifest-only so a
    metadata run cannot add hidden columns to KiCad's Symbol Fields Table.
    """

    if not isinstance(merged, MergedPart):
        merged = MergedPart.from_dict(merged)
    return OrderedDict()


def build_native_symbol_fields(
    merged: MergedPart,
    datasheet_choice: Optional[str] = None,
    default_datasheet: Optional[str] = None,
) -> Dict[str, str]:
    """Return verified values for the exporter's existing native properties."""

    if not isinstance(merged, MergedPart):
        merged = MergedPart.from_dict(merged)
    lcsc_part = (
        merged.cad.lcsc_part_number
        if merged.cad is not None and merged.cad.lcsc_part_number
        else _record_value(
            _provider_records(merged).get("lcsc"), "distributor_part_number"
        )
    )
    candidates = OrderedDict(
        (
            ("Manufacturer", merged.identity.manufacturer),
            ("MPN", merged.identity.mpn),
            ("LCSC Part", lcsc_part),
            (
                "Datasheet",
                select_datasheet(
                    merged, choice=datasheet_choice, default=default_datasheet
                ),
            ),
        )
    )
    return OrderedDict(
        (key, str(value))
        for key, value in candidates.items()
        if value is not None and str(value) != ""
    )


def build_all_symbol_fields(
    merged: MergedPart,
    datasheet_choice: Optional[str] = None,
    default_datasheet: Optional[str] = None,
) -> Dict[str, str]:
    """Return native and custom fields in stable documentation order."""

    fields = OrderedDict(
        build_native_symbol_fields(
            merged,
            datasheet_choice=datasheet_choice,
            default_datasheet=default_datasheet,
        )
    )
    fields.update(build_symbol_fields(merged))
    return fields


def select_datasheet(
    merged: MergedPart,
    choice: Optional[str] = None,
    default: Optional[str] = None,
) -> Optional[str]:
    """Select a requested link while preserving the source default if omitted."""

    if choice is None:
        return default
    normalized_choice = choice.strip().lower()
    if normalized_choice not in ("manufacturer", "lcsc", "digikey", "mouser"):
        raise ValueError("unknown datasheet link choice: {0}".format(choice))
    if not isinstance(merged, MergedPart):
        merged = MergedPart.from_dict(merged)
    if normalized_choice == "manufacturer":
        selected = sanitize_public_url(merged.identity.manufacturer_datasheet_url)
        if selected:
            return selected
        raise ValueError("manufacturer datasheet is unavailable")
    record = _provider_records(merged).get(normalized_choice)
    selected = sanitize_public_url(record.datasheet_url if record is not None else None)
    if record is None or not selected:
        raise ValueError("{0} datasheet is unavailable".format(normalized_choice))
    product_url = sanitize_public_url(record.product_url)
    if product_url is not None and _urls_equivalent(selected, product_url):
        raise ValueError(
            "{0} datasheet URL is the distributor product page".format(
                normalized_choice
            )
        )
    return selected


def _urls_equivalent(first: str, second: str) -> bool:
    """Compare sanitized public URLs without cosmetic authority/path variance."""

    def identity(value: str) -> tuple[str, str, str, tuple[tuple[str, str], ...]]:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").casefold()
        port = parsed.port
        if port is not None and not (
            (parsed.scheme.casefold() == "http" and port == 80)
            or (parsed.scheme.casefold() == "https" and port == 443)
        ):
            host = "{0}:{1}".format(host, port)
        path = parsed.path.rstrip("/") or "/"
        query = tuple(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
        return parsed.scheme.casefold(), host, path, query

    try:
        return identity(first) == identity(second)
    except ValueError:
        return False


def _provider_records(merged: MergedPart) -> Mapping[str, DistributorRecord]:
    records: Dict[str, DistributorRecord] = {}
    for record in sorted(
        merged.distributor_records,
        key=lambda item: (
            item.provider.lower(),
            item.distributor_part_number or "",
            item.product_url or "",
        ),
    ):
        records.setdefault(record.provider.lower(), record)
    return records


def _record_value(
    record: Optional[DistributorRecord], field_name: str
) -> Optional[str]:
    if record is None:
        return None
    value = getattr(record, field_name)
    if field_name in ("product_url", "datasheet_url"):
        return sanitize_public_url(str(value)) if value is not None else None
    return str(value) if value is not None else None


metadata_symbol_fields = build_symbol_fields
