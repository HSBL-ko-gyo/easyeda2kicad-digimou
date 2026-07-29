"""Deterministic JSON and BOM-compatible CSV manifest writers."""

from __future__ import annotations

# Global imports
import csv
import json
import os
import tempfile
from pathlib import Path, PurePath
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union, cast

# Local imports
from .cache import redact_configured_secret_text, sanitize_public_url, strip_secrets
from .models import DistributorRecord, JlcpcbResolution, MergedPart, model_to_dict

CSV_COLUMNS = (
    "Manufacturer",
    "MPN",
    "Package",
    "Lifecycle",
    "Manufacturer Datasheet",
    "LCSC Part",
    "JLCPCB Part #",
    "LCSC Part #",
    "JLCPCB Match Status",
    "JLCPCB Checked At",
    "JLCPCB Stock",
    "JLCPCB Cache State",
    "Manual Action Required",
    "Global Sourcing Candidates",
    "LCSC Product URL",
    "DigiKey Part",
    "DigiKey Product URL",
    "Mouser Part",
    "Mouser Product URL",
    "CAD Source",
    "Symbol",
    "Footprint",
    "3D Model",
    "Verification Status",
    "Provider",
    "Distributor Part Number",
    "Product URL",
    "Description",
    "Datasheet",
    "Stock",
    "MOQ",
    "Packaging",
    "Currency",
    "Price Breaks",
    "Retrieved At",
    "Conflicts",
    "Provenance",
    "Provider Errors",
    "Provider Diagnostics",
)


def manifest_to_dict(
    merged: MergedPart,
    include_price: bool = True,
    include_stock: bool = True,
) -> Dict[str, Any]:
    """Project a merged part to a JSON-safe manifest without mutating it."""

    if not isinstance(merged, MergedPart):
        merged = MergedPart.from_dict(merged)
    result = merged.to_dict()
    identity = result.get("identity")
    if isinstance(identity, dict):
        identity["manufacturer_datasheet_url"] = sanitize_public_url(
            identity.get("manufacturer_datasheet_url")
        )
    cad = result.get("cad")
    if isinstance(cad, dict) and "landing_url" in cad:
        cad["landing_url"] = sanitize_public_url(cad.get("landing_url"))
    cad_discovery = result.get("cad_discovery")
    if isinstance(cad_discovery, dict):
        provenance = cad_discovery.get("provenance")
        if isinstance(provenance, dict):
            provenance["landing_url"] = sanitize_public_url(
                provenance.get("landing_url")
            )
        action_required = cad_discovery.get("action_required")
        if isinstance(action_required, dict):
            action_required["setup_url"] = sanitize_public_url(
                action_required.get("setup_url")
            )
        package = cad_discovery.get("package")
        if isinstance(package, dict):
            package_provenance = package.get("provenance")
            if isinstance(package_provenance, dict):
                package_provenance["landing_url"] = sanitize_public_url(
                    package_provenance.get("landing_url")
                )
    jlcpcb = result.get("jlcpcb")
    if isinstance(jlcpcb, dict):
        if not include_stock:
            jlcpcb["stock"] = None
        candidates = jlcpcb.get("global_sourcing_candidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if isinstance(candidate, dict):
                    candidate["product_url"] = sanitize_public_url(
                        candidate.get("product_url")
                    )
    for record in result["distributor_records"]:
        record["product_url"] = sanitize_public_url(record.get("product_url"))
        record["datasheet_url"] = sanitize_public_url(record.get("datasheet_url"))
        if not include_price:
            record["price_breaks"] = []
            record["currency"] = None
        if not include_stock:
            record["stock"] = None
    diagnostics = result.get("provider_diagnostics")
    if isinstance(diagnostics, dict):
        for diagnostic in diagnostics.values():
            if isinstance(diagnostic, dict) and "setup_url" in diagnostic:
                diagnostic["setup_url"] = sanitize_public_url(
                    diagnostic.get("setup_url")
                )
    return cast(Dict[str, Any], strip_secrets(result))


def write_json_manifest(
    merged: MergedPart,
    path: Union[str, os.PathLike[str]],
    include_price: bool = True,
    include_stock: bool = True,
) -> Path:
    """Atomically write the complete merged manifest as UTF-8 JSON."""

    target = Path(path)
    value = manifest_to_dict(merged, include_price, include_stock)
    _atomic_json_write(target, value)
    return target


def csv_manifest_rows(
    merged: MergedPart,
    include_price: bool = True,
    include_stock: bool = True,
) -> List[Dict[str, str]]:
    """Return one deterministic BOM row per distributor record."""

    if not isinstance(merged, MergedPart):
        merged = MergedPart.from_dict(merged)
    records = sorted(merged.distributor_records, key=_record_sort_key)
    by_provider: Dict[str, DistributorRecord] = {}
    for record in records:
        by_provider.setdefault(record.provider.lower(), record)

    cad = merged.cad
    lcsc_record = by_provider.get("lcsc")
    digikey_record = by_provider.get("digikey")
    mouser_record = by_provider.get("mouser")
    jlcpcb = merged.jlcpcb
    legacy_lcsc_part = _text(
        cad.lcsc_part_number
        if cad is not None and cad.lcsc_part_number
        else (lcsc_record.distributor_part_number if lcsc_record is not None else None)
    )
    resolved_lcsc_part = (
        _text(jlcpcb.lcsc_part_number) if jlcpcb is not None else legacy_lcsc_part
    )
    stable = {
        "Manufacturer": _text(merged.identity.manufacturer),
        "MPN": _text(merged.identity.mpn),
        "Package": _text(merged.identity.package),
        "Lifecycle": _text(merged.identity.lifecycle),
        "Manufacturer Datasheet": _text(
            sanitize_public_url(merged.identity.manufacturer_datasheet_url)
        ),
        "LCSC Part": resolved_lcsc_part,
        "JLCPCB Part #": _text(
            jlcpcb.jlcpcb_part_number if jlcpcb is not None else None
        ),
        "LCSC Part #": resolved_lcsc_part,
        "JLCPCB Match Status": _text(
            jlcpcb.match_status if jlcpcb is not None else None
        ),
        "JLCPCB Checked At": _text(jlcpcb.checked_at if jlcpcb is not None else None),
        "JLCPCB Stock": _text(
            jlcpcb.stock if jlcpcb is not None and include_stock else None
        ),
        "JLCPCB Cache State": _text(jlcpcb.cache_state if jlcpcb is not None else None),
        "Manual Action Required": _text(
            jlcpcb.manual_action_required if jlcpcb is not None else None
        ),
        "Global Sourcing Candidates": _compact_json(
            _safe_global_sourcing_candidates(jlcpcb)
        ),
        "LCSC Product URL": _record_value(lcsc_record, "product_url"),
        "DigiKey Part": _record_value(digikey_record, "distributor_part_number"),
        "DigiKey Product URL": _record_value(digikey_record, "product_url"),
        "Mouser Part": _record_value(mouser_record, "distributor_part_number"),
        "Mouser Product URL": _record_value(mouser_record, "product_url"),
        "CAD Source": _text(cad.source if cad is not None else None),
        "Symbol": _text(
            (cad.symbol_path or cad.symbol_name) if cad is not None else None
        ),
        "Footprint": _text(
            (cad.footprint_path or cad.footprint_name) if cad is not None else None
        ),
        "3D Model": _text(
            (cad.model_3d_path or cad.model_3d) if cad is not None else None
        ),
        "Verification Status": merged.verification_status,
        "Conflicts": _compact_json(merged.conflicts),
        "Provenance": _compact_json(merged.provenance),
        "Provider Errors": _compact_json(merged.provider_errors),
        "Provider Diagnostics": _compact_json(merged.to_dict()["provider_diagnostics"]),
    }

    rows: List[Dict[str, str]] = []
    source_records: Sequence[Optional[DistributorRecord]] = records or [None]
    for source_record in source_records:
        row = dict(stable)
        row.update(
            {
                "Provider": _text(source_record.provider if source_record else None),
                "Distributor Part Number": _record_value(
                    source_record, "distributor_part_number"
                ),
                "Product URL": _record_value(source_record, "product_url"),
                "Description": _record_value(source_record, "description"),
                "Datasheet": _record_value(source_record, "datasheet_url"),
                "Stock": _text(
                    source_record.stock
                    if source_record is not None and include_stock
                    else None
                ),
                "MOQ": _text(
                    source_record.minimum_order_quantity
                    if source_record is not None
                    else None
                ),
                "Packaging": _record_value(source_record, "packaging"),
                "Currency": _text(
                    source_record.currency
                    if source_record is not None and include_price
                    else None
                ),
                "Price Breaks": _compact_json(
                    source_record.price_breaks
                    if source_record is not None and include_price
                    else []
                ),
                "Retrieved At": _record_value(source_record, "retrieved_at"),
            }
        )
        rows.append(
            {
                column: _spreadsheet_safe_cell(row.get(column, ""))
                for column in CSV_COLUMNS
            }
        )
    return rows


def write_csv_manifest(
    merged: MergedPart,
    path: Union[str, os.PathLike[str]],
    include_price: bool = True,
    include_stock: bool = True,
) -> Path:
    """Atomically write a BOM-compatible UTF-8 CSV manifest."""

    target = Path(path)
    rows = csv_manifest_rows(merged, include_price, include_stock)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=".{0}.".format(target.name),
            suffix=".tmp",
            dir=str(target.parent),
            delete=False,
        ) as stream:
            temporary_name = stream.name
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary_name).replace(target)
    finally:
        if temporary_name is not None:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()
    return target


# Verb-first aliases read naturally at CLI call sites.
write_manifest_json = write_json_manifest
write_manifest_csv = write_csv_manifest


def _record_sort_key(record: DistributorRecord) -> Any:
    priority = {"lcsc": 0, "digikey": 1, "mouser": 2}
    return (
        priority.get(record.provider.lower(), 100),
        record.provider.lower(),
        record.distributor_part_number or "",
        record.product_url or "",
    )


def _record_value(record: Optional[DistributorRecord], field_name: str) -> str:
    if record is None:
        return ""
    value = getattr(record, field_name)
    if field_name in ("product_url", "datasheet_url"):
        value = sanitize_public_url(value)
    return _text(value)


def _safe_global_sourcing_candidates(
    resolution: Optional[JlcpcbResolution],
) -> List[Dict[str, Any]]:
    if resolution is None:
        return []
    candidates: List[Dict[str, Any]] = []
    for candidate in resolution.global_sourcing_candidates:
        value = candidate.to_dict()
        value["product_url"] = sanitize_public_url(value.get("product_url"))
        candidates.append(value)
    return candidates


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return redact_configured_secret_text(str(value))


def _compact_json(value: Any) -> str:
    return json.dumps(
        strip_secrets(model_to_dict(value)),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _spreadsheet_safe_cell(value: str) -> str:
    """Prevent spreadsheet applications from evaluating manifest cells."""

    stripped = value.lstrip(" \t\r\n")
    if value.startswith(("\t", "\r", "\n")) or stripped.startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + value
    return value


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=".{0}.".format(path.name),
            suffix=".tmp",
            dir=str(path.parent),
            delete=False,
        ) as stream:
            temporary_name = stream.name
            json.dump(
                value,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary_name).replace(path)
    finally:
        if temporary_name is not None:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()
