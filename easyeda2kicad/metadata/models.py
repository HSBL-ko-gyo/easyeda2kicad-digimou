"""JSON-safe common models for distributor metadata and EasyEDA CAD state."""

from __future__ import annotations

# Global imports
import math
import unicodedata
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePath
from typing import Any, Dict, List, Mapping, Optional, Type, TypeVar, Union, cast

_MPN_MINUS_EQUIVALENTS = str.maketrans(
    {
        # Common presentation forms copied from PDFs, catalogues, and drawings.
        "\N{MINUS SIGN}": "-",
        "\N{SUPERSCRIPT MINUS}": "-",
        "\N{SUBSCRIPT MINUS}": "-",
        "\N{SMALL HYPHEN-MINUS}": "-",
        "\N{FULLWIDTH HYPHEN-MINUS}": "-",
    }
)


def identity_text(value: Any, field_name: str = "identity") -> str:
    """Return a nonempty identity string without coercing other JSON types."""

    if not isinstance(value, str):
        raise ValueError("{0} must be a nonempty string".format(field_name))
    text = value.strip()
    if not text:
        raise ValueError("{0} must be a nonempty string".format(field_name))
    return text


def normalize_mpn(value: Optional[str]) -> str:
    """Return the conservative comparison form of a manufacturer part number.

    Ordering-code suffixes, separators, and their positions remain significant.
    Unicode dash punctuation is mapped to ASCII ``-`` and runs of whitespace
    are collapsed, but ``-``, ``_``, and ``/`` are never deleted or conflated.
    """

    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError("MPN must be a string or None")
    translated = value.translate(_MPN_MINUS_EQUIVALENTS)
    normalized = unicodedata.normalize("NFKC", translated).strip().upper()
    normalized = "".join(
        "-" if unicodedata.category(character) == "Pd" else character
        for character in normalized
    )
    return " ".join(normalized.split())


def normalize_manufacturer(value: Optional[str]) -> str:
    """Return a punctuation/whitespace-insensitive manufacturer comparison key."""

    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError("manufacturer must be a string or None")
    normalized = unicodedata.normalize("NFKC", value).strip().upper()
    return "".join(
        character
        for character in normalized
        if not character.isspace()
        and not unicodedata.category(character).startswith("P")
    )


@dataclass
class PartIdentity:
    manufacturer: Optional[str] = None
    manufacturer_normalized: str = ""
    mpn: str = ""
    mpn_normalized: str = ""
    package: Optional[str] = None
    lifecycle: Optional[str] = None
    manufacturer_datasheet_url: Optional[str] = None

    def __post_init__(self) -> None:
        expected_manufacturer = normalize_manufacturer(self.manufacturer)
        expected_mpn = normalize_mpn(self.mpn)
        if (
            self.manufacturer_normalized
            and self.manufacturer_normalized != expected_manufacturer
        ):
            raise ValueError("manufacturer_normalized does not match manufacturer")
        if self.mpn_normalized and self.mpn_normalized != expected_mpn:
            raise ValueError("mpn_normalized does not match mpn")
        self.manufacturer_normalized = expected_manufacturer
        self.mpn_normalized = expected_mpn

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PartIdentity":
        mapping = _mapping(data, "PartIdentity")
        return cls(
            manufacturer=_optional_string(mapping.get("manufacturer")),
            manufacturer_normalized=_string(
                mapping.get("manufacturer_normalized", ""),
                "manufacturer_normalized",
            ),
            mpn=_string(mapping.get("mpn", ""), "mpn"),
            mpn_normalized=_string(mapping.get("mpn_normalized", ""), "mpn_normalized"),
            package=_optional_string(mapping.get("package")),
            lifecycle=_optional_string(mapping.get("lifecycle")),
            manufacturer_datasheet_url=_optional_string(
                mapping.get("manufacturer_datasheet_url")
            ),
        )


@dataclass
class PriceBreak:
    quantity: int
    unit_price: float
    currency: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.quantity, bool) or int(self.quantity) < 0:
            raise ValueError("price-break quantity must be a non-negative integer")
        self.quantity = int(self.quantity)
        if isinstance(self.unit_price, bool):
            raise ValueError("price-break unit_price must be numeric")
        self.unit_price = float(self.unit_price)
        if not math.isfinite(self.unit_price) or self.unit_price < 0:
            raise ValueError("price-break unit_price must be finite and non-negative")

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PriceBreak":
        mapping = _mapping(data, "PriceBreak")
        if "quantity" not in mapping or "unit_price" not in mapping:
            raise ValueError("PriceBreak requires quantity and unit_price")
        return cls(
            quantity=_integer(mapping["quantity"], "quantity"),
            unit_price=_number(mapping["unit_price"], "unit_price"),
            currency=_optional_string(mapping.get("currency")),
        )


@dataclass
class DistributorRecord:
    provider: str
    distributor_part_number: Optional[str] = None
    product_url: Optional[str] = None
    manufacturer: Optional[str] = None
    mpn: Optional[str] = None
    description: Optional[str] = None
    package: Optional[str] = None
    lifecycle: Optional[str] = None
    datasheet_url: Optional[str] = None
    stock: Optional[int] = None
    minimum_order_quantity: Optional[int] = None
    packaging: Optional[str] = None
    currency: Optional[str] = None
    price_breaks: List[PriceBreak] = dataclass_field(default_factory=list)
    retrieved_at: Optional[str] = None
    raw_response_cache_key: Optional[str] = None

    def __post_init__(self) -> None:
        self.provider = identity_text(
            self.provider, "DistributorRecord.provider"
        ).lower()
        for field_name in (
            "distributor_part_number",
            "manufacturer",
            "mpn",
        ):
            value = getattr(self, field_name)
            if value is not None:
                setattr(
                    self,
                    field_name,
                    identity_text(value, "DistributorRecord.{0}".format(field_name)),
                )
        if self.stock is not None:
            self.stock = _non_negative_integer(self.stock, "stock")
        if self.minimum_order_quantity is not None:
            self.minimum_order_quantity = _non_negative_integer(
                self.minimum_order_quantity, "minimum_order_quantity"
            )
        converted: List[PriceBreak] = []
        for item in self.price_breaks:
            converted.append(
                item if isinstance(item, PriceBreak) else PriceBreak.from_dict(item)
            )
        self.price_breaks = converted

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DistributorRecord":
        mapping = _mapping(data, "DistributorRecord")
        if "provider" not in mapping:
            raise ValueError("DistributorRecord requires provider")
        raw_breaks = mapping.get("price_breaks", [])
        if raw_breaks is None:
            raw_breaks = []
        if not isinstance(raw_breaks, (list, tuple)):
            raise ValueError("price_breaks must be a list")
        return cls(
            provider=identity_text(mapping["provider"], "provider"),
            distributor_part_number=_optional_identity_text(
                mapping.get("distributor_part_number"), "distributor_part_number"
            ),
            product_url=_optional_string(mapping.get("product_url")),
            manufacturer=_optional_identity_text(
                mapping.get("manufacturer"), "manufacturer"
            ),
            mpn=_optional_identity_text(mapping.get("mpn"), "mpn"),
            description=_optional_string(mapping.get("description")),
            package=_optional_string(mapping.get("package")),
            lifecycle=_optional_string(mapping.get("lifecycle")),
            datasheet_url=_optional_string(mapping.get("datasheet_url")),
            stock=_optional_integer(mapping.get("stock"), "stock"),
            minimum_order_quantity=_optional_integer(
                mapping.get("minimum_order_quantity"), "minimum_order_quantity"
            ),
            packaging=_optional_string(mapping.get("packaging")),
            currency=_optional_string(mapping.get("currency")),
            price_breaks=[PriceBreak.from_dict(item) for item in raw_breaks],
            retrieved_at=_optional_string(mapping.get("retrieved_at")),
            raw_response_cache_key=_optional_string(
                mapping.get("raw_response_cache_key")
            ),
        )


@dataclass
class CadRecord:
    source: str
    lcsc_part_number: Optional[str] = None
    easyeda_component_id: Optional[str] = None
    symbol_name: Optional[str] = None
    footprint_name: Optional[str] = None
    model_3d: Optional[str] = None
    symbol_path: Optional[Union[str, PurePath]] = None
    footprint_path: Optional[Union[str, PurePath]] = None
    model_3d_path: Optional[Union[str, PurePath]] = None
    verification_status: str = "CAD_NOT_FOUND"

    def __post_init__(self) -> None:
        self.source = identity_text(self.source, "CadRecord.source").lower()
        for field_name in ("lcsc_part_number", "easyeda_component_id"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(
                    self,
                    field_name,
                    identity_text(value, "CadRecord.{0}".format(field_name)),
                )

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CadRecord":
        mapping = _mapping(data, "CadRecord")
        if "source" not in mapping:
            raise ValueError("CadRecord requires source")
        return cls(
            source=identity_text(mapping["source"], "source"),
            lcsc_part_number=_optional_identity_text(
                mapping.get("lcsc_part_number"), "lcsc_part_number"
            ),
            easyeda_component_id=_optional_identity_text(
                mapping.get("easyeda_component_id"), "easyeda_component_id"
            ),
            symbol_name=_optional_string(mapping.get("symbol_name")),
            footprint_name=_optional_string(mapping.get("footprint_name")),
            model_3d=_optional_string(mapping.get("model_3d")),
            symbol_path=_optional_string(mapping.get("symbol_path")),
            footprint_path=_optional_string(mapping.get("footprint_path")),
            model_3d_path=_optional_string(mapping.get("model_3d_path")),
            verification_status=_string(
                mapping.get("verification_status", "CAD_NOT_FOUND"),
                "verification_status",
            ),
        )


@dataclass
class Conflict:
    field: str
    values: Dict[str, Any] = dataclass_field(default_factory=dict)
    selected_value: Any = None
    reason: str = "provider values disagree"

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Conflict":
        mapping = _mapping(data, "Conflict")
        values = mapping.get("values", {})
        if not isinstance(values, Mapping):
            raise ValueError("Conflict.values must be an object")
        return cls(
            field=_string(mapping.get("field", ""), "field"),
            values={str(key): model_to_dict(value) for key, value in values.items()},
            selected_value=model_to_dict(mapping.get("selected_value")),
            reason=_string(mapping.get("reason", "provider values disagree"), "reason"),
        )


@dataclass
class ProvenanceEntry:
    provider: str
    source_field: str

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProvenanceEntry":
        mapping = _mapping(data, "ProvenanceEntry")
        return cls(
            provider=_string(mapping.get("provider", ""), "provider"),
            source_field=_string(mapping.get("source_field", ""), "source_field"),
        )


@dataclass
class ProviderDiagnostic:
    """Credential-safe provider failure context exposed in manifests."""

    code: str
    operation: Optional[str] = None
    status: Optional[int] = None

    def __post_init__(self) -> None:
        self.code = identity_text(self.code, "diagnostic code")
        self.operation = _optional_identity_text(self.operation, "diagnostic operation")
        self.status = _optional_integer(self.status, "diagnostic status")

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProviderDiagnostic":
        mapping = _mapping(data, "ProviderDiagnostic")
        return cls(
            code=identity_text(mapping.get("code"), "diagnostic code"),
            operation=_optional_identity_text(
                mapping.get("operation"), "diagnostic operation"
            ),
            status=_optional_integer(mapping.get("status"), "diagnostic status"),
        )


@dataclass
class MergedPart:
    identity: PartIdentity
    distributor_records: List[DistributorRecord] = dataclass_field(default_factory=list)
    cad: Optional[CadRecord] = None
    conflicts: List[Conflict] = dataclass_field(default_factory=list)
    verification_status: str = "PARTIAL"
    provenance: Dict[str, List[ProvenanceEntry]] = dataclass_field(default_factory=dict)
    provider_errors: Dict[str, str] = dataclass_field(default_factory=dict)
    provider_diagnostics: Dict[str, ProviderDiagnostic] = dataclass_field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not isinstance(self.identity, PartIdentity):
            self.identity = PartIdentity.from_dict(self.identity)
        self.distributor_records = [
            (
                record
                if isinstance(record, DistributorRecord)
                else DistributorRecord.from_dict(record)
            )
            for record in self.distributor_records
        ]
        if self.cad is not None and not isinstance(self.cad, CadRecord):
            self.cad = CadRecord.from_dict(self.cad)
        self.conflicts = [
            conflict if isinstance(conflict, Conflict) else Conflict.from_dict(conflict)
            for conflict in self.conflicts
        ]
        converted_provenance: Dict[str, List[ProvenanceEntry]] = {}
        for key, entries in self.provenance.items():
            converted_provenance[str(key)] = [
                (
                    entry
                    if isinstance(entry, ProvenanceEntry)
                    else ProvenanceEntry.from_dict(entry)
                )
                for entry in entries
            ]
        self.provenance = converted_provenance
        self.provider_errors = {
            str(provider): str(error)
            for provider, error in self.provider_errors.items()
        }
        self.provider_diagnostics = {
            str(provider): (
                diagnostic
                if isinstance(diagnostic, ProviderDiagnostic)
                else ProviderDiagnostic.from_dict(diagnostic)
            )
            for provider, diagnostic in self.provider_diagnostics.items()
        }
        for provider, code in self.provider_errors.items():
            self.provider_diagnostics.setdefault(
                provider, ProviderDiagnostic(code=code)
            )

    def to_dict(self) -> Dict[str, Any]:
        document = cast(Dict[str, Any], model_to_dict(self))
        diagnostics = cast(Dict[str, Any], document["provider_diagnostics"])
        for provider, code in self.provider_errors.items():
            diagnostics.setdefault(provider, ProviderDiagnostic(code=code).to_dict())
        return document

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MergedPart":
        mapping = _mapping(data, "MergedPart")
        if "identity" not in mapping:
            raise ValueError("MergedPart requires identity")
        raw_records = mapping.get("distributor_records", [])
        raw_conflicts = mapping.get("conflicts", [])
        raw_provenance = mapping.get("provenance", {})
        raw_errors = mapping.get("provider_errors", {})
        raw_diagnostics = mapping.get("provider_diagnostics", {})
        if not isinstance(raw_records, (list, tuple)):
            raise ValueError("distributor_records must be a list")
        if not isinstance(raw_conflicts, (list, tuple)):
            raise ValueError("conflicts must be a list")
        if not isinstance(raw_provenance, Mapping):
            raise ValueError("provenance must be an object")
        if not isinstance(raw_errors, Mapping):
            raise ValueError("provider_errors must be an object")
        if not isinstance(raw_diagnostics, Mapping):
            raise ValueError("provider_diagnostics must be an object")
        provenance: Dict[str, List[ProvenanceEntry]] = {}
        for key, entries in raw_provenance.items():
            if not isinstance(entries, (list, tuple)):
                raise ValueError("provenance values must be lists")
            provenance[str(key)] = [
                ProvenanceEntry.from_dict(entry) for entry in entries
            ]
        raw_cad = mapping.get("cad")
        return cls(
            identity=PartIdentity.from_dict(mapping["identity"]),
            distributor_records=[
                DistributorRecord.from_dict(item) for item in raw_records
            ],
            cad=CadRecord.from_dict(raw_cad) if raw_cad is not None else None,
            conflicts=[Conflict.from_dict(item) for item in raw_conflicts],
            verification_status=_string(
                mapping.get("verification_status", "PARTIAL"),
                "verification_status",
            ),
            provenance=provenance,
            provider_errors={str(key): str(value) for key, value in raw_errors.items()},
            provider_diagnostics={
                str(key): ProviderDiagnostic.from_dict(value)
                for key, value in raw_diagnostics.items()
            },
        )


ModelType = TypeVar("ModelType")


def model_to_dict(value: Any) -> Any:
    """Recursively convert supported model values to JSON-safe primitives."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not JSON-safe")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite decimals are not JSON-safe")
        return str(value)
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: model_to_dict(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            result[key] = model_to_dict(item)
        return result
    if isinstance(value, (list, tuple)):
        return [model_to_dict(item) for item in value]
    if isinstance(value, (set, frozenset)):
        converted = [model_to_dict(item) for item in value]
        return sorted(converted, key=lambda item: repr(item))
    raise TypeError("unsupported JSON value: {0}".format(type(value).__name__))


def model_from_dict(model_type: Type[ModelType], data: Mapping[str, Any]) -> ModelType:
    """Deserialize a common model using its explicit validating constructor."""

    from_dict = getattr(model_type, "from_dict", None)
    if not callable(from_dict):
        raise TypeError("model_type must provide from_dict")
    return cast(ModelType, from_dict(data))


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("{0} must be an object".format(name))
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError("{0} must be a string".format(name))
    return value


def _optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, (str, PurePath)):
        raise ValueError("optional string value has invalid type")
    return str(value)


def _optional_identity_text(value: Any, name: str) -> Optional[str]:
    if value is None:
        return None
    return identity_text(value, name)


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("{0} must be an integer".format(name))
    return int(value)


def _non_negative_integer(value: Any, name: str) -> int:
    number = _integer(value, name)
    if number < 0:
        raise ValueError("{0} must be non-negative".format(name))
    return number


def _optional_integer(value: Any, name: str) -> Optional[int]:
    if value is None:
        return None
    return _non_negative_integer(value, name)


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{0} must be numeric".format(name))
    try:
        number = float(value)
    except OverflowError:
        raise ValueError("{0} is out of range".format(name)) from None
    if not math.isfinite(number):
        raise ValueError("{0} must be finite".format(name))
    return number
