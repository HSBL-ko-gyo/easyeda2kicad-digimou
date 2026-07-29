"""JSON-safe common models for distributor metadata and EasyEDA CAD state."""

from __future__ import annotations

# Global imports
import math
import re
import unicodedata
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePath, PurePosixPath, PureWindowsPath
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

SUPPORTED_CAD_SOURCES = frozenset(("easyeda", "digikey", "mouser", "auto"))
GUEST_LOOKUP_UNSUPPORTED = "GUEST_LOOKUP_UNSUPPORTED"
CAD_PACKAGE_READY = "CAD_PACKAGE_READY"
CAD_NOT_ACQUIRED = "CAD_NOT_ACQUIRED"
CAD_AUTH_REQUIRED = "CAD_AUTH_REQUIRED"
CAD_DOWNLOAD_UNAVAILABLE = "CAD_DOWNLOAD_UNAVAILABLE"
CAD_MANUAL_DOWNLOAD_REQUIRED = "CAD_MANUAL_DOWNLOAD_REQUIRED"
CAD_IDENTITY_UNRESOLVED = "CAD_IDENTITY_UNRESOLVED"
CAD_SOURCE_CONFLICT = "CAD_SOURCE_CONFLICT"
CAD_SOURCE_LOCK_MISMATCH = "CAD_SOURCE_LOCK_MISMATCH"
CAD_DISCOVERY_STATUSES = frozenset(
    (
        CAD_PACKAGE_READY,
        CAD_NOT_ACQUIRED,
        CAD_AUTH_REQUIRED,
        CAD_DOWNLOAD_UNAVAILABLE,
        CAD_MANUAL_DOWNLOAD_REQUIRED,
        CAD_IDENTITY_UNRESOLVED,
        CAD_SOURCE_CONFLICT,
        CAD_SOURCE_LOCK_MISMATCH,
    )
)
JLCPCB_PART_FOUND = "JLCPCB_PART_FOUND"
MANUAL_GLOBAL_SOURCING_REQUIRED = "MANUAL_GLOBAL_SOURCING_REQUIRED"
JLCPCB_LOOKUP_FAILED = "JLCPCB_LOOKUP_FAILED"
JLCPCB_IDENTITY_AMBIGUOUS = "JLCPCB_IDENTITY_AMBIGUOUS"
JLCPCB_IDENTITY_CONFLICT = "JLCPCB_IDENTITY_CONFLICT"
JLCPCB_MATCH_STATUSES = frozenset(
    (
        JLCPCB_PART_FOUND,
        MANUAL_GLOBAL_SOURCING_REQUIRED,
        JLCPCB_LOOKUP_FAILED,
        JLCPCB_IDENTITY_AMBIGUOUS,
        JLCPCB_IDENTITY_CONFLICT,
    )
)
JLCPCB_CACHE_LIVE = "LIVE"
JLCPCB_CACHE_CACHED = "CACHED"
JLCPCB_CACHE_OFFLINE_MISS = "OFFLINE_MISS"
JLCPCB_CACHE_ERROR = "CACHE_ERROR"
JLCPCB_CACHE_STATES = frozenset(
    (
        JLCPCB_CACHE_LIVE,
        JLCPCB_CACHE_CACHED,
        JLCPCB_CACHE_OFFLINE_MISS,
        JLCPCB_CACHE_ERROR,
    )
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_CANONICAL_LCSC_ID_RE = re.compile(r"C[1-9][0-9]*")


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
class GlobalSourcingCandidate:
    """One exact distributor record usable as a manual sourcing hint."""

    provider: str
    manufacturer_part_number: str
    distributor_part_number: str
    product_url: Optional[str] = None

    def __post_init__(self) -> None:
        self.provider = identity_text(
            self.provider, "GlobalSourcingCandidate.provider"
        ).lower()
        if self.provider not in ("digikey", "mouser"):
            raise ValueError("unsupported global-sourcing provider")
        self.manufacturer_part_number = identity_text(
            self.manufacturer_part_number,
            "GlobalSourcingCandidate.manufacturer_part_number",
        )
        self.distributor_part_number = identity_text(
            self.distributor_part_number,
            "GlobalSourcingCandidate.distributor_part_number",
        )
        self.product_url = _optional_string(self.product_url)

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GlobalSourcingCandidate":
        mapping = _mapping(data, "GlobalSourcingCandidate")
        return cls(
            provider=identity_text(mapping.get("provider"), "provider"),
            manufacturer_part_number=identity_text(
                mapping.get("manufacturer_part_number"),
                "manufacturer_part_number",
            ),
            distributor_part_number=identity_text(
                mapping.get("distributor_part_number"),
                "distributor_part_number",
            ),
            product_url=_optional_string(mapping.get("product_url")),
        )


@dataclass
class JlcpcbResolution:
    """Fail-closed result of the invocation's exact JLCPCB/LCSC lookup."""

    match_status: str
    checked_at: str
    cache_state: str
    jlcpcb_part_number: Optional[str] = None
    lcsc_part_number: Optional[str] = None
    stock: Optional[int] = None
    manual_action_required: Optional[str] = None
    global_sourcing_candidates: List[GlobalSourcingCandidate] = dataclass_field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        self.match_status = identity_text(
            self.match_status, "JlcpcbResolution.match_status"
        )
        if self.match_status not in JLCPCB_MATCH_STATUSES:
            raise ValueError("unsupported JLCPCB match status")
        self.checked_at = identity_text(self.checked_at, "JlcpcbResolution.checked_at")
        self.cache_state = identity_text(
            self.cache_state, "JlcpcbResolution.cache_state"
        )
        if self.cache_state not in JLCPCB_CACHE_STATES:
            raise ValueError("unsupported JLCPCB cache state")
        for field_name in ("jlcpcb_part_number", "lcsc_part_number"):
            value = getattr(self, field_name)
            if value is not None:
                value = identity_text(value, "JlcpcbResolution.{0}".format(field_name))
                if _CANONICAL_LCSC_ID_RE.fullmatch(value) is None:
                    raise ValueError(
                        "{0} must be a canonical C-number".format(field_name)
                    )
                setattr(self, field_name, value)
        if self.stock is not None:
            self.stock = _non_negative_integer(self.stock, "JlcpcbResolution.stock")
        self.manual_action_required = _optional_identity_text(
            self.manual_action_required,
            "JlcpcbResolution.manual_action_required",
        )
        normalized_candidates = [
            candidate
            if isinstance(candidate, GlobalSourcingCandidate)
            else GlobalSourcingCandidate.from_dict(candidate)
            for candidate in self.global_sourcing_candidates
        ]
        unique_candidates = {
            (
                candidate.provider,
                candidate.manufacturer_part_number,
                candidate.distributor_part_number,
                candidate.product_url,
            ): candidate
            for candidate in normalized_candidates
        }
        self.global_sourcing_candidates = sorted(
            unique_candidates.values(),
            key=lambda candidate: (
                candidate.provider,
                candidate.distributor_part_number,
                candidate.product_url or "",
            ),
        )

        if self.match_status == JLCPCB_PART_FOUND:
            if self.jlcpcb_part_number is None and self.lcsc_part_number is None:
                raise ValueError("JLCPCB_PART_FOUND requires a canonical part number")
            if self.manual_action_required is not None:
                raise ValueError("found JLCPCB parts cannot require manual sourcing")
        else:
            if (
                self.jlcpcb_part_number is not None
                or self.lcsc_part_number is not None
                or self.stock is not None
            ):
                raise ValueError(
                    "unresolved JLCPCB results cannot expose a part number or stock"
                )
        if self.match_status == MANUAL_GLOBAL_SOURCING_REQUIRED:
            if self.manual_action_required is None:
                raise ValueError(
                    "manual global sourcing status requires an explicit action"
                )
        elif self.manual_action_required is not None:
            raise ValueError(
                "manual action is only valid for MANUAL_GLOBAL_SOURCING_REQUIRED"
            )

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JlcpcbResolution":
        mapping = _mapping(data, "JlcpcbResolution")
        raw_candidates = mapping.get("global_sourcing_candidates", [])
        return cls(
            match_status=identity_text(mapping.get("match_status"), "match_status"),
            checked_at=identity_text(mapping.get("checked_at"), "checked_at"),
            cache_state=identity_text(mapping.get("cache_state"), "cache_state"),
            jlcpcb_part_number=_optional_identity_text(
                mapping.get("jlcpcb_part_number"), "jlcpcb_part_number"
            ),
            lcsc_part_number=_optional_identity_text(
                mapping.get("lcsc_part_number"), "lcsc_part_number"
            ),
            stock=_optional_integer(mapping.get("stock"), "stock"),
            manual_action_required=_optional_identity_text(
                mapping.get("manual_action_required"), "manual_action_required"
            ),
            global_sourcing_candidates=[
                GlobalSourcingCandidate.from_dict(item)
                for item in _list(raw_candidates, "global_sourcing_candidates")
            ],
        )


@dataclass
class CadRequest:
    """One fail-closed CAD request for a complete manufacturer/MPN identity."""

    manufacturer: str
    mpn: str
    source: str

    def __post_init__(self) -> None:
        self.manufacturer = identity_text(self.manufacturer, "CadRequest.manufacturer")
        self.mpn = identity_text(self.mpn, "CadRequest.mpn")
        self.source = identity_text(self.source, "CadRequest.source").lower()
        if self.source not in SUPPORTED_CAD_SOURCES:
            raise ValueError("unsupported CAD source: {0}".format(self.source))

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CadRequest":
        mapping = _mapping(data, "CadRequest")
        return cls(
            manufacturer=identity_text(
                mapping.get("manufacturer"), "CadRequest.manufacturer"
            ),
            mpn=identity_text(mapping.get("mpn"), "CadRequest.mpn"),
            source=identity_text(mapping.get("source"), "CadRequest.source"),
        )


@dataclass
class CadArtifact:
    """A portable package artifact identified by content rather than machine path."""

    kind: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        self.kind = identity_text(self.kind, "CadArtifact.kind").lower()
        portable_path = identity_text(
            self.relative_path, "CadArtifact.relative_path"
        ).replace("\\", "/")
        parsed_path = PurePosixPath(portable_path)
        if (
            parsed_path.is_absolute()
            or PureWindowsPath(portable_path).drive
            or any(part in ("", ".", "..") for part in parsed_path.parts)
        ):
            raise ValueError("CadArtifact.relative_path must be a safe relative path")
        self.relative_path = parsed_path.as_posix()
        self.sha256 = identity_text(self.sha256, "CadArtifact.sha256").lower()
        if _SHA256_RE.fullmatch(self.sha256) is None:
            raise ValueError("CadArtifact.sha256 must be a lowercase SHA-256 digest")

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CadArtifact":
        mapping = _mapping(data, "CadArtifact")
        return cls(
            kind=identity_text(mapping.get("kind"), "CadArtifact.kind"),
            relative_path=identity_text(
                mapping.get("relative_path"), "CadArtifact.relative_path"
            ),
            sha256=identity_text(mapping.get("sha256"), "CadArtifact.sha256"),
        )


@dataclass
class CadProvenance:
    """Keep the distributor, delivery partner, and model creator distinct."""

    distributor: Optional[str] = None
    delivery_partner: Optional[str] = None
    model_creator: Optional[str] = None
    landing_url: Optional[str] = None
    retrieval_mode: Optional[str] = None
    package_hash: Optional[str] = None
    license: Optional[str] = None
    notice: Optional[str] = None

    def __post_init__(self) -> None:
        for field_name in ("distributor", "delivery_partner", "model_creator"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(
                    self,
                    field_name,
                    identity_text(
                        value, "CadProvenance.{0}".format(field_name)
                    ).lower(),
                )
        self.retrieval_mode = _optional_identity_text(
            self.retrieval_mode, "CadProvenance.retrieval_mode"
        )
        self.package_hash = _optional_identity_text(
            self.package_hash, "CadProvenance.package_hash"
        )
        if self.package_hash is not None:
            self.package_hash = self.package_hash.lower()
            if _SHA256_RE.fullmatch(self.package_hash) is None:
                raise ValueError(
                    "CadProvenance.package_hash must be a lowercase SHA-256 digest"
                )

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CadProvenance":
        mapping = _mapping(data, "CadProvenance")
        return cls(
            distributor=_optional_identity_text(
                mapping.get("distributor"), "CadProvenance.distributor"
            ),
            delivery_partner=_optional_identity_text(
                mapping.get("delivery_partner"), "CadProvenance.delivery_partner"
            ),
            model_creator=_optional_identity_text(
                mapping.get("model_creator"), "CadProvenance.model_creator"
            ),
            landing_url=_optional_string(mapping.get("landing_url")),
            retrieval_mode=_optional_identity_text(
                mapping.get("retrieval_mode"), "CadProvenance.retrieval_mode"
            ),
            package_hash=_optional_identity_text(
                mapping.get("package_hash"), "CadProvenance.package_hash"
            ),
            license=_optional_string(mapping.get("license")),
            notice=_optional_string(mapping.get("notice")),
        )


@dataclass
class NormalizedCadPackage:
    """A source-neutral, content-addressed CAD package."""

    request: CadRequest
    format_name: str
    format_version: str
    artifacts: List[CadArtifact]
    provenance: CadProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.request, CadRequest):
            self.request = CadRequest.from_dict(self.request)
        self.format_name = identity_text(
            self.format_name, "NormalizedCadPackage.format_name"
        )
        self.format_version = identity_text(
            self.format_version, "NormalizedCadPackage.format_version"
        )
        self.artifacts = [
            artifact
            if isinstance(artifact, CadArtifact)
            else CadArtifact.from_dict(artifact)
            for artifact in self.artifacts
        ]
        if not self.artifacts:
            raise ValueError("NormalizedCadPackage requires at least one artifact")
        if not isinstance(self.provenance, CadProvenance):
            self.provenance = CadProvenance.from_dict(self.provenance)
        if self.provenance.package_hash is None:
            raise ValueError("NormalizedCadPackage requires a package hash")

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NormalizedCadPackage":
        mapping = _mapping(data, "NormalizedCadPackage")
        raw_artifacts = mapping.get("artifacts")
        raw_request = mapping.get("request")
        raw_provenance = mapping.get("provenance")
        if not isinstance(raw_artifacts, (list, tuple)):
            raise ValueError("NormalizedCadPackage.artifacts must be a list")
        if not isinstance(raw_request, Mapping):
            raise ValueError("NormalizedCadPackage.request must be an object")
        if not isinstance(raw_provenance, Mapping):
            raise ValueError("NormalizedCadPackage.provenance must be an object")
        return cls(
            request=CadRequest.from_dict(raw_request),
            format_name=identity_text(
                mapping.get("format_name"), "NormalizedCadPackage.format_name"
            ),
            format_version=identity_text(
                mapping.get("format_version"), "NormalizedCadPackage.format_version"
            ),
            artifacts=[CadArtifact.from_dict(item) for item in raw_artifacts],
            provenance=CadProvenance.from_dict(raw_provenance),
        )


@dataclass
class CadActionRequired:
    """A credential-safe instruction describing why CAD is not yet available."""

    code: str
    detail: str
    setup_url: Optional[str] = None

    def __post_init__(self) -> None:
        self.code = identity_text(self.code, "CadActionRequired.code")
        self.detail = identity_text(self.detail, "CadActionRequired.detail")

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CadActionRequired":
        mapping = _mapping(data, "CadActionRequired")
        return cls(
            code=identity_text(mapping.get("code"), "CadActionRequired.code"),
            detail=identity_text(mapping.get("detail"), "CadActionRequired.detail"),
            setup_url=_optional_string(mapping.get("setup_url")),
        )


@dataclass
class CadDiscoveryResult:
    """A typed discovery result that never implies an unverified CAD package."""

    requested_source: str
    status: str
    request: Optional[CadRequest] = None
    provenance: CadProvenance = dataclass_field(default_factory=CadProvenance)
    action_required: Optional[CadActionRequired] = None
    package: Optional[NormalizedCadPackage] = None

    def __post_init__(self) -> None:
        self.requested_source = identity_text(
            self.requested_source, "CadDiscoveryResult.requested_source"
        ).lower()
        if self.requested_source not in SUPPORTED_CAD_SOURCES:
            raise ValueError(
                "unsupported CAD source: {0}".format(self.requested_source)
            )
        self.status = identity_text(self.status, "CadDiscoveryResult.status").upper()
        if self.status not in CAD_DISCOVERY_STATUSES:
            raise ValueError(
                "unsupported CAD discovery status: {0}".format(self.status)
            )
        if self.request is not None and not isinstance(self.request, CadRequest):
            self.request = CadRequest.from_dict(self.request)
        if not isinstance(self.provenance, CadProvenance):
            self.provenance = CadProvenance.from_dict(self.provenance)
        if self.action_required is not None and not isinstance(
            self.action_required, CadActionRequired
        ):
            self.action_required = CadActionRequired.from_dict(self.action_required)
        if self.package is not None and not isinstance(
            self.package, NormalizedCadPackage
        ):
            self.package = NormalizedCadPackage.from_dict(self.package)
        if self.status == CAD_PACKAGE_READY and self.package is None:
            raise ValueError("CAD_PACKAGE_READY requires a normalized package")
        if self.status != CAD_PACKAGE_READY and self.package is not None:
            raise ValueError("an unready CAD result cannot contain a package")

    def to_dict(self) -> Dict[str, Any]:
        return cast(Dict[str, Any], model_to_dict(self))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CadDiscoveryResult":
        mapping = _mapping(data, "CadDiscoveryResult")
        raw_request = mapping.get("request")
        raw_action = mapping.get("action_required")
        raw_package = mapping.get("package")
        return cls(
            requested_source=identity_text(
                mapping.get("requested_source"),
                "CadDiscoveryResult.requested_source",
            ),
            status=identity_text(mapping.get("status"), "CadDiscoveryResult.status"),
            request=(
                CadRequest.from_dict(raw_request) if raw_request is not None else None
            ),
            provenance=CadProvenance.from_dict(mapping.get("provenance", {})),
            action_required=(
                CadActionRequired.from_dict(raw_action)
                if raw_action is not None
                else None
            ),
            package=(
                NormalizedCadPackage.from_dict(raw_package)
                if raw_package is not None
                else None
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
    distributor: Optional[str] = None
    delivery_partner: Optional[str] = None
    model_creator: Optional[str] = None
    landing_url: Optional[str] = None
    retrieval_mode: Optional[str] = None
    package_hash: Optional[str] = None
    license: Optional[str] = None
    notice: Optional[str] = None
    artifacts: List[CadArtifact] = dataclass_field(default_factory=list)

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
        provenance = CadProvenance(
            distributor=self.distributor,
            delivery_partner=self.delivery_partner,
            model_creator=self.model_creator,
            landing_url=self.landing_url,
            retrieval_mode=self.retrieval_mode,
            package_hash=self.package_hash,
            license=self.license,
            notice=self.notice,
        )
        self.distributor = provenance.distributor
        self.delivery_partner = provenance.delivery_partner
        self.model_creator = provenance.model_creator
        self.retrieval_mode = provenance.retrieval_mode
        self.package_hash = provenance.package_hash
        self.artifacts = [
            artifact
            if isinstance(artifact, CadArtifact)
            else CadArtifact.from_dict(artifact)
            for artifact in self.artifacts
        ]

    def to_dict(self) -> Dict[str, Any]:
        document = cast(Dict[str, Any], model_to_dict(self))
        _omit_empty_cad_extensions(document)
        return document

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
            distributor=_optional_identity_text(
                mapping.get("distributor"), "CadRecord.distributor"
            ),
            delivery_partner=_optional_identity_text(
                mapping.get("delivery_partner"), "CadRecord.delivery_partner"
            ),
            model_creator=_optional_identity_text(
                mapping.get("model_creator"), "CadRecord.model_creator"
            ),
            landing_url=_optional_string(mapping.get("landing_url")),
            retrieval_mode=_optional_identity_text(
                mapping.get("retrieval_mode"), "CadRecord.retrieval_mode"
            ),
            package_hash=_optional_identity_text(
                mapping.get("package_hash"), "CadRecord.package_hash"
            ),
            license=_optional_string(mapping.get("license")),
            notice=_optional_string(mapping.get("notice")),
            artifacts=[
                CadArtifact.from_dict(item)
                for item in _list(mapping.get("artifacts", []), "CadRecord.artifacts")
            ],
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
    setup_url: Optional[str] = None

    def __post_init__(self) -> None:
        self.code = identity_text(self.code, "diagnostic code")
        self.operation = _optional_identity_text(self.operation, "diagnostic operation")
        self.status = _optional_integer(self.status, "diagnostic status")
        self.setup_url = _optional_identity_text(self.setup_url, "diagnostic setup URL")

    def to_dict(self) -> Dict[str, Any]:
        document: Dict[str, Any] = {
            "code": self.code,
            "operation": self.operation,
            "status": self.status,
        }
        if self.setup_url is not None:
            document["setup_url"] = self.setup_url
        return document

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProviderDiagnostic":
        mapping = _mapping(data, "ProviderDiagnostic")
        return cls(
            code=identity_text(mapping.get("code"), "diagnostic code"),
            operation=_optional_identity_text(
                mapping.get("operation"), "diagnostic operation"
            ),
            status=_optional_integer(mapping.get("status"), "diagnostic status"),
            setup_url=_optional_identity_text(
                mapping.get("setup_url"), "diagnostic setup URL"
            ),
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
    cad_discovery: Optional[CadDiscoveryResult] = None
    jlcpcb: Optional[JlcpcbResolution] = None

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
        if self.cad_discovery is not None and not isinstance(
            self.cad_discovery, CadDiscoveryResult
        ):
            self.cad_discovery = CadDiscoveryResult.from_dict(self.cad_discovery)
        if self.jlcpcb is not None and not isinstance(self.jlcpcb, JlcpcbResolution):
            self.jlcpcb = JlcpcbResolution.from_dict(self.jlcpcb)

    def to_dict(self) -> Dict[str, Any]:
        document = cast(Dict[str, Any], model_to_dict(self))
        cad = document.get("cad")
        if isinstance(cad, dict):
            _omit_empty_cad_extensions(cad)
        if document.get("cad_discovery") is None:
            document.pop("cad_discovery", None)
        if document.get("jlcpcb") is None:
            document.pop("jlcpcb", None)
        diagnostics = cast(Dict[str, Any], document["provider_diagnostics"])
        for provider, code in self.provider_errors.items():
            diagnostics.setdefault(provider, ProviderDiagnostic(code=code).to_dict())
        for diagnostic in diagnostics.values():
            if isinstance(diagnostic, dict) and diagnostic.get("setup_url") is None:
                diagnostic.pop("setup_url", None)
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
        raw_cad_discovery = mapping.get("cad_discovery")
        raw_jlcpcb = mapping.get("jlcpcb")
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
            cad_discovery=(
                CadDiscoveryResult.from_dict(raw_cad_discovery)
                if raw_cad_discovery is not None
                else None
            ),
            jlcpcb=(
                JlcpcbResolution.from_dict(raw_jlcpcb)
                if raw_jlcpcb is not None
                else None
            ),
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
    if isinstance(value, ProviderDiagnostic):
        return value.to_dict()
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


def _omit_empty_cad_extensions(document: Dict[str, Any]) -> None:
    """Keep pre-contract CAD JSON byte-compatible when extensions are unused."""

    for field_name in (
        "distributor",
        "delivery_partner",
        "model_creator",
        "landing_url",
        "retrieval_mode",
        "package_hash",
        "license",
        "notice",
    ):
        if document.get(field_name) is None:
            document.pop(field_name, None)
    if document.get("artifacts") == []:
        document.pop("artifacts", None)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("{0} must be an object".format(name))
    return value


def _list(value: Any, name: str) -> List[Any]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("{0} must be a list".format(name))
    return list(value)


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
