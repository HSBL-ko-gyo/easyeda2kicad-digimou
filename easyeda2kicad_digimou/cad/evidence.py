"""Strict, hash-bound evidence for manually downloaded CAD packages."""

from __future__ import annotations

# Global imports
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Set, cast
from urllib.parse import urlsplit

# Local imports
from easyeda2kicad_digimou.metadata.cache import sanitize_public_url
from easyeda2kicad_digimou.metadata.models import (
    CadRequest,
    normalize_manufacturer,
    normalize_mpn,
)

from .errors import CadPackageError

EVIDENCE_SCHEMA_VERSION = 1
_MAX_EVIDENCE_SIZE = 64 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_KEYS = frozenset(
    (
        "agreement_url",
        "delivery_partner",
        "landing_url",
        "manufacturer",
        "model_creator",
        "mpn",
        "package_format",
        "package_sha256",
        "product_url",
        "retrieval_mode",
        "retrieved_at_utc",
        "schema_version",
        "source",
    )
)
_DELIVERY_PARTNER = {
    "digikey": "ultralibrarian",
    "mouser": "samacsys",
}
_PACKAGE_FORMAT = {
    "digikey": "ultralibrarian-kicad",
    "mouser": "samacsys-kicad",
}


@dataclass(frozen=True)
class CadPackageEvidence:
    """Sanitized manual-handoff receipt bound to one exact archive hash."""

    source: str
    delivery_partner: str
    package_format: str
    manufacturer: str
    mpn: str
    package_sha256: str
    product_url: str
    landing_url: str
    agreement_url: Optional[str]
    retrieval_mode: str
    retrieved_at_utc: str
    model_creator: Optional[str]


def load_package_evidence(
    path: Path,
    *,
    request: CadRequest,
    archive_sha256: str,
    requested_format: str,
) -> CadPackageEvidence:
    """Load a small sanitized receipt and verify its exact request/hash binding."""

    if path.is_symlink() or not path.is_file():
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_NOT_FOUND",
            "package evidence path must be a regular file",
        )
    try:
        size = path.stat().st_size
    except OSError as error:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_UNREADABLE",
            "package evidence cannot be inspected",
        ) from error
    if size > _MAX_EVIDENCE_SIZE:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_TOO_LARGE",
            "package evidence exceeds the 64 KiB limit",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_INVALID",
            "package evidence must be UTF-8 JSON",
        ) from error
    if not isinstance(payload, Mapping):
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_INVALID",
            "package evidence root must be an object",
        )
    mapping = cast(Mapping[str, Any], payload)
    keys = set(mapping)
    if keys != _REQUIRED_KEYS:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_INVALID",
            "package evidence fields do not match schema version 1",
        )
    if mapping["schema_version"] != EVIDENCE_SCHEMA_VERSION:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_VERSION_UNSUPPORTED",
            "unsupported package evidence schema version",
        )

    source = _required_text(mapping, "source").casefold()
    delivery_partner = _required_text(mapping, "delivery_partner").casefold()
    package_format = _required_text(mapping, "package_format").casefold()
    manufacturer = _required_text(mapping, "manufacturer")
    mpn = _required_text(mapping, "mpn")
    package_sha256 = _required_text(mapping, "package_sha256").casefold()
    product_url = _safe_public_url(mapping, "product_url", source)
    landing_url = _safe_public_url(mapping, "landing_url", source)
    agreement_url = _optional_public_url(mapping, "agreement_url", source)
    retrieval_mode = _required_text(mapping, "retrieval_mode")
    retrieved_at_utc = _utc_timestamp(mapping, "retrieved_at_utc")
    model_creator = _optional_text(mapping, "model_creator")

    if source != request.source or source not in _DELIVERY_PARTNER:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_SOURCE_MISMATCH",
            "package evidence does not match the explicit CAD source",
        )
    if delivery_partner != _DELIVERY_PARTNER[source]:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_SOURCE_MISMATCH",
            "package evidence names an unexpected delivery partner",
        )
    if package_format != _PACKAGE_FORMAT[source]:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_FORMAT_MISMATCH",
            "package evidence names an unexpected package format",
        )
    if requested_format not in ("auto", package_format):
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_FORMAT_MISMATCH",
            "package evidence does not match --cad-package-format",
        )
    if normalize_manufacturer(manufacturer) != normalize_manufacturer(
        request.manufacturer
    ) or normalize_mpn(mpn) != normalize_mpn(request.mpn):
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_IDENTITY_MISMATCH",
            "package evidence does not match the requested manufacturer and exact MPN",
        )
    if _SHA256_RE.fullmatch(package_sha256) is None or package_sha256 != archive_sha256:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_HASH_MISMATCH",
            "package evidence is not bound to this exact archive",
        )
    if retrieval_mode != "manual-official-download":
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_INVALID",
            "package evidence retrieval mode must be manual-official-download",
        )
    _validate_source_urls(source, product_url, landing_url, agreement_url)
    return CadPackageEvidence(
        source=source,
        delivery_partner=delivery_partner,
        package_format=package_format,
        manufacturer=manufacturer,
        mpn=mpn,
        package_sha256=package_sha256,
        product_url=product_url,
        landing_url=landing_url,
        agreement_url=agreement_url,
        retrieval_mode=retrieval_mode,
        retrieved_at_utc=retrieved_at_utc,
        model_creator=model_creator,
    )


def _required_text(mapping: Mapping[str, Any], name: str) -> str:
    value = mapping.get(name)
    if not isinstance(value, str) or not value.strip():
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_INVALID",
            "package evidence contains an invalid {0}".format(name),
        )
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_INVALID",
            "package evidence contains an invalid {0}".format(name),
        )
    return value.strip()


def _optional_text(mapping: Mapping[str, Any], name: str) -> Optional[str]:
    value = mapping.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_INVALID",
            "package evidence contains an invalid {0}".format(name),
        )
    return _required_text(mapping, name)


def _safe_public_url(mapping: Mapping[str, Any], name: str, source: str) -> str:
    value = _required_text(mapping, name)
    sanitized = sanitize_public_url(value)
    if sanitized is None or sanitized != value:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_URL_UNSAFE",
            "package evidence contains an unsafe {0}".format(name),
        )
    parsed = urlsplit(sanitized)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_URL_UNSAFE",
            "package evidence contains an unsafe {0}".format(name),
        )
    if source not in _DELIVERY_PARTNER:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_SOURCE_MISMATCH",
            "package evidence names an unsupported source",
        )
    return sanitized


def _optional_public_url(
    mapping: Mapping[str, Any],
    name: str,
    source: str,
) -> Optional[str]:
    if mapping.get(name) is None:
        return None
    return _safe_public_url(mapping, name, source)


def _validate_source_urls(
    source: str,
    product_url: str,
    landing_url: str,
    agreement_url: Optional[str],
) -> None:
    product = urlsplit(product_url)
    landing = urlsplit(landing_url)
    agreement = urlsplit(agreement_url) if agreement_url is not None else None
    if source == "digikey":
        if (
            product.hostname or ""
        ).casefold() != "www.digikey.com" or not product.path.casefold().startswith(
            "/en/products/detail/"
        ):
            raise CadPackageError(
                "CAD_PACKAGE_EVIDENCE_URL_UNSAFE",
                "DigiKey product evidence must use an official exact product URL",
            )
        landing_host = (landing.hostname or "").casefold()
        landing_is_digikey = (
            landing_host == "www.digikey.com"
            and re.fullmatch(r"/en/models/[0-9]+", landing.path.casefold()) is not None
        )
        landing_is_ultralibrarian = landing_host == "ultralibrarian.com" or (
            landing_host.endswith(".ultralibrarian.com")
        )
        if not (landing_is_digikey or landing_is_ultralibrarian):
            raise CadPackageError(
                "CAD_PACKAGE_EVIDENCE_URL_UNSAFE",
                "DigiKey CAD evidence must use an official model handoff URL",
            )
        if agreement is not None and (
            (agreement.hostname or "").casefold() != "www.digikey.com"
            or "/models/" not in agreement.path.casefold()
        ):
            raise CadPackageError(
                "CAD_PACKAGE_EVIDENCE_URL_UNSAFE",
                "DigiKey agreement evidence must use an official model URL",
            )
        return

    allowed_product_hosts: Set[str] = {"mouser.com", "www.mouser.com"}
    allowed_landing_hosts: Set[str] = {
        "componentsearchengine.com",
        "www.componentsearchengine.com",
    }
    if (product.hostname or "").casefold() not in allowed_product_hosts:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_URL_UNSAFE",
            "Mouser product evidence must use an official product URL",
        )
    landing_host = (landing.hostname or "").casefold()
    if landing_host not in allowed_landing_hosts and not landing_host.endswith(
        ".componentsearchengine.com"
    ):
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_URL_UNSAFE",
            "Mouser CAD evidence must use an official SamacSys handoff URL",
        )
    if agreement is not None:
        agreement_host = (agreement.hostname or "").casefold()
        if agreement_host not in allowed_landing_hosts and not agreement_host.endswith(
            ".componentsearchengine.com"
        ):
            raise CadPackageError(
                "CAD_PACKAGE_EVIDENCE_URL_UNSAFE",
                "SamacSys agreement evidence must use an official URL",
            )


def _utc_timestamp(mapping: Mapping[str, Any], name: str) -> str:
    value = _required_text(mapping, name)
    if not value.endswith("Z"):
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_INVALID",
            "package evidence retrieved_at_utc must use UTC Z notation",
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_INVALID",
            "package evidence retrieved_at_utc is not ISO-8601",
        ) from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise CadPackageError(
            "CAD_PACKAGE_EVIDENCE_INVALID",
            "package evidence retrieved_at_utc must be UTC",
        )
    return value


__all__ = [
    "CadPackageEvidence",
    "EVIDENCE_SCHEMA_VERSION",
    "load_package_evidence",
]
