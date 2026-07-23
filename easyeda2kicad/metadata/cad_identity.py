"""Extract and reconcile identity evidence from an EasyEDA CAD payload."""

from __future__ import annotations

# Global imports
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Local imports
from .models import normalize_manufacturer, normalize_mpn


class CadIdentityError(ValueError):
    """Base error for CAD identity that cannot be verified safely."""

    code = "INVALID_RESPONSE"

    def __init__(self, field_name: str, detail: str) -> None:
        self.field_name = field_name
        self.detail = detail
        super().__init__("CAD identity {0}: {1}".format(field_name, detail))


class CadIdentityConflictError(CadIdentityError):
    """The CAD payload contains contradictory values for one identity field."""


class CadIdentityMissingError(CadIdentityError):
    """The CAD payload omits evidence required to verify a request."""


class CadIdentityMismatchError(CadIdentityError):
    """The CAD payload disagrees with an explicit user identity."""

    def __init__(self, field_name: str, detail: str) -> None:
        self.code = {
            "mpn": "MPN_MISMATCH",
            "lcsc_id": "LCSC_ID_MISMATCH",
            "manufacturer": "MANUFACTURER_MISMATCH",
        }.get(field_name, "IDENTITY_MISMATCH")
        super().__init__(field_name, detail)


@dataclass(frozen=True)
class CadIdentity:
    """Identity proven by values contained in the fetched CAD payload."""

    lcsc_id: Optional[str]
    mpn: Optional[str]
    manufacturer: Optional[str]
    easyeda_component_id: Optional[str]
    evidence: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)


def normalize_lcsc_id(value: Optional[str]) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().upper()


def extract_cad_identity(
    raw: Mapping[str, Any],
    *,
    requested_lcsc_id: Optional[str] = None,
    requested_mpn: Optional[str] = None,
    requested_manufacturer: Optional[str] = None,
) -> CadIdentity:
    """Validate identity using only fields present in an EasyEDA CAD payload.

    Search terms, response titles, and caller-provided identifiers are never
    used as fallback values.  Every non-empty piece of evidence for a field
    must agree after the field's documented conservative normalization.
    """

    if not isinstance(raw, Mapping):
        raise CadIdentityError("payload", "expected an object")

    parameter_maps = list(_parameter_maps(raw))
    lcsc_values = _top_level_lcsc_values(raw)
    lcsc_values.extend(
        _values_for_keys(
            parameter_maps,
            (
                "supplier part",
                "supplier part number",
                "lcsc part",
                "lcsc part number",
                "lcsc",
            ),
        )
    )
    mpn_values = _values_for_keys(
        parameter_maps,
        (
            "manufacturer part",
            "manufacturer part number",
            "bom_manufacturer part",
            "bom_manufacturer part number",
            "mpn",
        ),
    )
    manufacturer_values = _values_for_keys(
        parameter_maps,
        (
            "manufacturer",
            "manufacturer name",
            "bom_manufacturer",
            "brand",
        ),
    )

    lcsc_id = _reconcile("lcsc_id", lcsc_values, normalize_lcsc_id)
    mpn = _reconcile("mpn", mpn_values, normalize_mpn)
    manufacturer = _reconcile(
        "manufacturer", manufacturer_values, normalize_manufacturer
    )

    _verify_requested(
        "lcsc_id",
        requested_lcsc_id,
        lcsc_id,
        normalize_lcsc_id,
    )
    _verify_requested("mpn", requested_mpn, mpn, normalize_mpn)
    _verify_requested(
        "manufacturer",
        requested_manufacturer,
        manufacturer,
        normalize_manufacturer,
    )

    component_id = _optional_text(raw.get("uuid"))
    return CadIdentity(
        lcsc_id=lcsc_id,
        mpn=mpn,
        manufacturer=manufacturer,
        easyeda_component_id=component_id,
        evidence={
            "lcsc_id": tuple(_unique_values(lcsc_values)),
            "mpn": tuple(_unique_values(mpn_values)),
            "manufacturer": tuple(_unique_values(manufacturer_values)),
        },
    )


def _parameter_maps(raw: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    symbol_parameters = _nested_mapping(raw, "dataStr", "head", "c_para")
    if symbol_parameters is not None:
        yield symbol_parameters

    package_parameters = _nested_mapping(
        raw, "packageDetail", "dataStr", "head", "c_para"
    )
    if package_parameters is not None:
        yield package_parameters

    subparts = raw.get("subparts")
    if isinstance(subparts, Sequence) and not isinstance(subparts, (str, bytes)):
        for subpart in subparts:
            if not isinstance(subpart, Mapping):
                continue
            parameters = _nested_mapping(subpart, "dataStr", "head", "c_para")
            if parameters is not None:
                yield parameters


def _nested_mapping(
    source: Mapping[str, Any], *path: str
) -> Optional[Mapping[str, Any]]:
    current: Any = source
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current if isinstance(current, Mapping) else None


def _top_level_lcsc_values(raw: Mapping[str, Any]) -> List[str]:
    values: List[str] = []
    for key in ("lcsc", "szlcsc"):
        container = raw.get(key)
        if isinstance(container, Mapping):
            for candidate_key in ("number", "componentCode", "code"):
                value = _optional_text(container.get(candidate_key))
                if value:
                    values.append(value)
        else:
            value = _optional_text(container)
            if value:
                values.append(value)
    return values


def _key_form(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


def _values_for_keys(
    mappings: Iterable[Mapping[str, Any]], names: Sequence[str]
) -> List[str]:
    wanted = {_key_form(name) for name in names}
    values: List[str] = []
    for mapping in mappings:
        for key, item in mapping.items():
            if _key_form(key) not in wanted:
                continue
            value = _optional_text(item)
            if value:
                values.append(value)
    return values


def _reconcile(
    field_name: str,
    values: Sequence[str],
    normalizer: Any,
) -> Optional[str]:
    distinct: Dict[str, str] = {}
    for value in values:
        normalized = normalizer(value)
        if normalized:
            distinct.setdefault(normalized, value.strip())
    if len(distinct) > 1:
        raise CadIdentityConflictError(
            field_name,
            "payload values disagree ({0})".format(
                ", ".join(sorted(distinct.values()))
            ),
        )
    return next(iter(distinct.values())) if distinct else None


def _verify_requested(
    field_name: str,
    requested: Optional[str],
    actual: Optional[str],
    normalizer: Any,
) -> None:
    requested_normalized = normalizer(requested)
    if not requested_normalized:
        return
    actual_normalized = normalizer(actual)
    if not actual_normalized:
        raise CadIdentityMissingError(
            field_name, "payload contains no value to verify the request"
        )
    if requested_normalized != actual_normalized:
        raise CadIdentityMismatchError(
            field_name,
            "requested value does not match the CAD payload",
        )


def _unique_values(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CadIdentityError("payload", "identity evidence must be text")
    text = value.strip()
    return text or None


__all__ = [
    "CadIdentity",
    "CadIdentityConflictError",
    "CadIdentityError",
    "CadIdentityMismatchError",
    "CadIdentityMissingError",
    "extract_cad_identity",
    "normalize_lcsc_id",
]
