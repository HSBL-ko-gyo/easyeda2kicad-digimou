"""Conservative exact-identity merge with conflicts and provenance."""

from __future__ import annotations

# Global imports
import unicodedata
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

# Local imports
from .models import (
    CadRecord,
    Conflict,
    DistributorRecord,
    MergedPart,
    PartIdentity,
    ProviderDiagnostic,
    ProvenanceEntry,
    normalize_manufacturer,
    normalize_mpn,
)

VERIFIED = "VERIFIED"
PARTIAL = "PARTIAL"
CAD_NOT_FOUND = "CAD_NOT_FOUND"
CAD_PIN_PAD_MISMATCH = "CAD_PIN_PAD_MISMATCH"
VERIFICATION_STATUSES = frozenset(
    (VERIFIED, PARTIAL, CAD_NOT_FOUND, CAD_PIN_PAD_MISMATCH)
)

_PROVIDER_PRIORITY = {"lcsc": 0, "digikey": 1, "mouser": 2}


class MergeError(ValueError):
    category = "MERGE_ERROR"


class IdentityMismatchError(MergeError):
    category = "MPN_MISMATCH"


class AmbiguousIdentityError(MergeError):
    category = "AMBIGUOUS"


def merge_records(
    distributor_records: Sequence[DistributorRecord],
    mpn: Optional[str] = None,
    manufacturer: Optional[str] = None,
    cad: Optional[CadRecord] = None,
    provider_errors: Optional[Mapping[str, Any]] = None,
    provider_diagnostics: Optional[Mapping[str, Any]] = None,
    verification_status: Optional[str] = None,
    manufacturer_seed: Optional[str] = None,
    manufacturer_seed_source: Optional[str] = None,
    manufacturer_evidence_values: Optional[Mapping[str, str]] = None,
    manufacturer_diagnostic_values: Optional[Mapping[str, str]] = None,
) -> MergedPart:
    """Merge locally validated distributor records around one exact identity.

    The explicit MPN/manufacturer remain authoritative.  A mismatching LCSC
    record is fatal because it represents an explicit CAD identity; an invalid
    distributor result is excluded and reported as a provider diagnostic.
    """

    records = [_coerce_record(record) for record in distributor_records]
    records.sort(key=_record_sort_key)
    errors: Dict[str, str] = {
        str(provider).lower(): str(error)
        for provider, error in (provider_errors or {}).items()
    }
    diagnostics: Dict[str, ProviderDiagnostic] = {
        str(provider).lower(): (
            diagnostic
            if isinstance(diagnostic, ProviderDiagnostic)
            else ProviderDiagnostic.from_dict(diagnostic)
        )
        for provider, diagnostic in (provider_diagnostics or {}).items()
    }
    for provider, code in errors.items():
        diagnostics.setdefault(provider, ProviderDiagnostic(code=code))

    authoritative_mpn, mpn_provider = _select_authoritative_mpn(records, mpn)
    requested_mpn_normalized = normalize_mpn(authoritative_mpn)
    if not requested_mpn_normalized:
        raise MergeError("an exact MPN is required to merge metadata")

    authoritative_manufacturer, manufacturer_provider = _select_manufacturer(
        records,
        manufacturer,
        manufacturer_seed,
        manufacturer_seed_source,
    )
    requested_manufacturer_normalized = normalize_manufacturer(
        authoritative_manufacturer
    )
    # Manufacturer is a hard filter only when the user supplied it. Provider
    # display names are not canonical identifiers (for example TI vs the full
    # company name), so inferred disagreements remain explicit conflicts.
    enforce_manufacturer = bool(
        manufacturer is not None and normalize_manufacturer(manufacturer)
    )

    valid_records: List[DistributorRecord] = []
    for record in records:
        if normalize_mpn(record.mpn) != requested_mpn_normalized:
            if record.provider == "lcsc":
                raise IdentityMismatchError(
                    "LCSC identity does not exactly match MPN {0}".format(
                        authoritative_mpn
                    )
                )
            errors[record.provider] = "NOT_FOUND: returned MPN failed exact validation"
            continue
        if (
            enforce_manufacturer
            and requested_manufacturer_normalized
            and normalize_manufacturer(record.manufacturer)
            != requested_manufacturer_normalized
        ):
            if record.provider == "lcsc":
                raise IdentityMismatchError(
                    "LCSC manufacturer does not match the requested identity"
                )
            errors[record.provider] = (
                "NOT_FOUND: returned manufacturer failed exact validation"
            )
            continue
        valid_records.append(record)

    conflicts: List[Conflict] = []
    provenance: Dict[str, List[ProvenanceEntry]] = {}

    identity_manufacturer = authoritative_manufacturer
    if not identity_manufacturer:
        identity_manufacturer, manufacturer_provider = _first_value(
            valid_records, "manufacturer"
        )

    _add_identity_provenance(
        provenance,
        "identity.mpn",
        mpn_provider,
        "--mpn" if mpn_provider == "user" else "mpn",
    )
    _add_identity_provenance(
        provenance,
        "identity.mpn_normalized",
        mpn_provider,
        "normalized(mpn)",
    )
    if identity_manufacturer:
        _add_identity_provenance(
            provenance,
            "identity.manufacturer",
            manufacturer_provider,
            _manufacturer_source_field(manufacturer_provider),
        )
        _add_identity_provenance(
            provenance,
            "identity.manufacturer_normalized",
            manufacturer_provider,
            "normalized(manufacturer)",
        )

    _append_conflict_if_needed(
        conflicts,
        "manufacturer",
        valid_records,
        "manufacturer",
        identity_manufacturer,
        normalizer=normalize_manufacturer,
        seed_value=(manufacturer_seed if not enforce_manufacturer else None),
        seed_provider=manufacturer_seed_source,
        evidence_values=(
            manufacturer_evidence_values if not enforce_manufacturer else None
        ),
        diagnostic_values=manufacturer_diagnostic_values,
        reason=(
            "manufacturer value is not supported by exact part-scoped evidence"
            if manufacturer_diagnostic_values
            else "inferred manufacturer display names disagree"
            if manufacturer_seed and not enforce_manufacturer
            else "provider values disagree"
        ),
    )

    package, package_entries = _select_scalar(valid_records, "package")
    lifecycle, lifecycle_entries = _select_scalar(valid_records, "lifecycle")
    datasheet, datasheet_entries = _select_datasheet(valid_records)
    if package_entries:
        provenance["identity.package"] = package_entries
    if lifecycle_entries:
        provenance["identity.lifecycle"] = lifecycle_entries
    if datasheet_entries:
        provenance["identity.manufacturer_datasheet_url"] = datasheet_entries

    _append_conflict_if_needed(conflicts, "package", valid_records, "package", package)
    _append_conflict_if_needed(
        conflicts, "lifecycle", valid_records, "lifecycle", lifecycle
    )
    _append_conflict_if_needed(
        conflicts,
        "manufacturer_datasheet_url",
        valid_records,
        "datasheet_url",
        datasheet,
        normalizer=_normalize_url,
    )

    if cad is not None and not isinstance(cad, CadRecord):
        cad = CadRecord.from_dict(cad)
    if cad is not None:
        for field_name in (
            "lcsc_part_number",
            "easyeda_component_id",
            "symbol_name",
            "footprint_name",
            "model_3d",
            "symbol_path",
            "footprint_path",
            "model_3d_path",
            "verification_status",
            "distributor",
            "delivery_partner",
            "model_creator",
            "landing_url",
            "retrieval_mode",
            "package_hash",
            "license",
            "notice",
            "artifacts",
        ):
            if getattr(cad, field_name):
                provenance["cad.{0}".format(field_name)] = [
                    ProvenanceEntry(provider=cad.source, source_field=field_name)
                ]

    status = _verification_status(cad, errors, verification_status)
    identity = PartIdentity(
        manufacturer=identity_manufacturer,
        manufacturer_normalized=normalize_manufacturer(identity_manufacturer),
        mpn=authoritative_mpn,
        mpn_normalized=requested_mpn_normalized,
        package=package,
        lifecycle=lifecycle,
        manufacturer_datasheet_url=datasheet,
    )
    return MergedPart(
        identity=identity,
        distributor_records=valid_records,
        cad=cad,
        conflicts=sorted(conflicts, key=lambda conflict: conflict.field),
        verification_status=status,
        provenance={key: provenance[key] for key in sorted(provenance)},
        provider_errors={key: errors[key] for key in sorted(errors)},
        provider_diagnostics={key: diagnostics[key] for key in sorted(diagnostics)},
    )


def merge_metadata(
    records: Sequence[DistributorRecord],
    requested_mpn: Optional[str] = None,
    requested_manufacturer: Optional[str] = None,
    cad: Optional[CadRecord] = None,
    provider_errors: Optional[Mapping[str, Any]] = None,
    provider_diagnostics: Optional[Mapping[str, Any]] = None,
    verification_status: Optional[str] = None,
    manufacturer_seed: Optional[str] = None,
    manufacturer_seed_source: Optional[str] = None,
    manufacturer_evidence_values: Optional[Mapping[str, str]] = None,
    manufacturer_diagnostic_values: Optional[Mapping[str, str]] = None,
) -> MergedPart:
    """Named compatibility wrapper for orchestration code."""

    return merge_records(
        distributor_records=records,
        mpn=requested_mpn,
        manufacturer=requested_manufacturer,
        cad=cad,
        provider_errors=provider_errors,
        provider_diagnostics=provider_diagnostics,
        verification_status=verification_status,
        manufacturer_seed=manufacturer_seed,
        manufacturer_seed_source=manufacturer_seed_source,
        manufacturer_evidence_values=manufacturer_evidence_values,
        manufacturer_diagnostic_values=manufacturer_diagnostic_values,
    )


merge_part = merge_records


def _coerce_record(record: DistributorRecord) -> DistributorRecord:
    if isinstance(record, DistributorRecord):
        return record
    return DistributorRecord.from_dict(record)


def _record_sort_key(record: DistributorRecord) -> Tuple[Any, ...]:
    return (
        _PROVIDER_PRIORITY.get(record.provider, 100),
        record.provider,
        record.minimum_order_quantity is None,
        record.minimum_order_quantity or 0,
        record.distributor_part_number or "",
        record.product_url or "",
    )


def _select_authoritative_mpn(
    records: Sequence[DistributorRecord], requested_mpn: Optional[str]
) -> Tuple[str, str]:
    if requested_mpn is not None and normalize_mpn(requested_mpn):
        return str(requested_mpn).strip(), "user"
    lcsc_records = [record for record in records if record.provider == "lcsc"]
    candidates = {
        normalize_mpn(record.mpn): record.mpn
        for record in lcsc_records
        if normalize_mpn(record.mpn)
    }
    if len(candidates) > 1:
        raise AmbiguousIdentityError("LCSC records contain multiple exact identities")
    if len(candidates) == 1:
        return str(next(iter(candidates.values()))), "lcsc"
    raise MergeError("MPN is required when no exact LCSC identity is available")


def _select_manufacturer(
    records: Sequence[DistributorRecord],
    requested_manufacturer: Optional[str],
    manufacturer_seed: Optional[str],
    manufacturer_seed_source: Optional[str],
) -> Tuple[Optional[str], str]:
    if requested_manufacturer is not None and normalize_manufacturer(
        requested_manufacturer
    ):
        return str(requested_manufacturer).strip(), "user"
    if manufacturer_seed is not None and normalize_manufacturer(manufacturer_seed):
        return (
            str(manufacturer_seed).strip(),
            (manufacturer_seed_source or "verified_identity").strip().lower(),
        )
    lcsc_records = [record for record in records if record.provider == "lcsc"]
    value, provider = _first_value(lcsc_records, "manufacturer")
    if value:
        return value, provider
    return _first_value(records, "manufacturer")


def _first_value(
    records: Iterable[DistributorRecord], field_name: str
) -> Tuple[Optional[str], str]:
    for record in records:
        value = getattr(record, field_name)
        if value is not None and str(value).strip():
            return str(value).strip(), record.provider
    return None, ""


def _select_scalar(
    records: Sequence[DistributorRecord], field_name: str
) -> Tuple[Optional[str], List[ProvenanceEntry]]:
    selected, _ = _first_value(records, field_name)
    if not selected:
        return None, []
    normalized_selected = _normalize_scalar(selected)
    entries = [
        ProvenanceEntry(provider=record.provider, source_field=field_name)
        for record in records
        if getattr(record, field_name)
        and _normalize_scalar(str(getattr(record, field_name))) == normalized_selected
    ]
    return selected, _deduplicate_provenance(entries)


def _select_datasheet(
    records: Sequence[DistributorRecord],
) -> Tuple[Optional[str], List[ProvenanceEntry]]:
    product_urls = {
        _normalize_url(record.product_url)
        for record in records
        if record.product_url and _normalize_url(record.product_url)
    }
    candidates: List[str] = []
    for record in records:
        candidate = record.datasheet_url
        if candidate and _is_http_url(candidate):
            normalized = _normalize_url(candidate)
            if normalized and normalized not in product_urls:
                candidates.append(candidate.strip())
    if not candidates:
        return None, []
    manufacturer_candidates = [
        candidate
        for candidate in candidates
        if not _is_distributor_owned_url(candidate)
    ]
    # This is only a link-quality heuristic. Record identity, conflicts, and
    # provenance remain governed by the same exact-match merge rules.
    selected = (manufacturer_candidates or candidates)[0]
    normalized_selected = _normalize_url(selected)
    entries = [
        ProvenanceEntry(provider=record.provider, source_field="datasheet_url")
        for record in records
        if record.datasheet_url
        and _normalize_url(record.datasheet_url) == normalized_selected
    ]
    return selected, _deduplicate_provenance(entries)


def _append_conflict_if_needed(
    conflicts: List[Conflict],
    conflict_field: str,
    records: Sequence[DistributorRecord],
    record_field: str,
    selected_value: Optional[str],
    normalizer: Any = None,
    seed_value: Optional[str] = None,
    seed_provider: Optional[str] = None,
    evidence_values: Optional[Mapping[str, str]] = None,
    diagnostic_values: Optional[Mapping[str, str]] = None,
    reason: str = "provider values disagree",
) -> None:
    if normalizer is None:
        normalizer = _normalize_scalar
    values: List[Tuple[str, str, str]] = []
    provider_counts: Counter[str] = Counter()
    seed_normalized = ""
    seed_label = ""
    evidence_pairs = set()
    if seed_value is not None and str(seed_value).strip():
        seed_label = (seed_provider or "verified_identity").strip().lower()
        seed_normalized = normalizer(str(seed_value))
        if seed_normalized:
            provider_counts[seed_label] += 1
            values.append((seed_label, str(seed_value).strip(), seed_normalized))
            evidence_pairs.add((seed_label, seed_normalized))
    for provider, evidence_value in sorted((evidence_values or {}).items()):
        label_base = str(provider).strip().lower()
        normalized = normalizer(str(evidence_value))
        if not label_base or not normalized:
            continue
        if (label_base, normalized) in evidence_pairs:
            continue
        provider_counts[label_base] += 1
        suffix = provider_counts[label_base]
        label = label_base if suffix == 1 else "{0}#{1}".format(label_base, suffix)
        values.append((label, str(evidence_value).strip(), normalized))
        evidence_pairs.add((label_base, normalized))
    for record in records:
        value = getattr(record, record_field)
        if value is None or not str(value).strip():
            continue
        normalized = normalizer(str(value))
        if (record.provider, normalized) in evidence_pairs:
            continue
        provider_counts[record.provider] += 1
        suffix = provider_counts[record.provider]
        label = (
            record.provider
            if suffix == 1
            else "{0}#{1}".format(record.provider, suffix)
        )
        values.append((label, str(value), normalized))
    for provider, diagnostic_value in sorted((diagnostic_values or {}).items()):
        label_base = str(provider).strip().lower()
        normalized = normalizer(str(diagnostic_value))
        if not label_base or not normalized:
            continue
        provider_counts[label_base] += 1
        suffix = provider_counts[label_base]
        label = label_base if suffix == 1 else "{0}#{1}".format(label_base, suffix)
        values.append((label, str(diagnostic_value).strip(), normalized))
    distinct = {normalized for _, _, normalized in values if normalized}
    if len(distinct) <= 1:
        return
    conflicts.append(
        Conflict(
            field=conflict_field,
            values={label: value for label, value, _ in values},
            selected_value=selected_value,
            reason=reason,
        )
    )


def _manufacturer_source_field(provider: str) -> str:
    if provider == "user":
        return "--manufacturer"
    if provider == "easyeda":
        return "dataStr.head.c_para.Manufacturer"
    return "manufacturer"


def _add_identity_provenance(
    provenance: Dict[str, List[ProvenanceEntry]],
    key: str,
    provider: str,
    source_field: str,
) -> None:
    if provider:
        provenance[key] = [
            ProvenanceEntry(provider=provider, source_field=source_field)
        ]


def _deduplicate_provenance(
    entries: Iterable[ProvenanceEntry],
) -> List[ProvenanceEntry]:
    unique = {(entry.provider, entry.source_field): entry for entry in entries}
    return [unique[key] for key in sorted(unique)]


def _verification_status(
    cad: Optional[CadRecord],
    provider_errors: Mapping[str, str],
    explicit: Optional[str],
) -> str:
    if explicit is not None:
        if explicit not in VERIFICATION_STATUSES:
            raise ValueError("invalid verification status")
        return explicit
    if cad is None:
        return CAD_NOT_FOUND
    cad_status = cad.verification_status or VERIFIED
    if cad_status not in VERIFICATION_STATUSES:
        raise ValueError("invalid CAD verification status")
    if cad_status in (CAD_NOT_FOUND, CAD_PIN_PAD_MISMATCH):
        return cad_status
    if provider_errors or cad_status == PARTIAL:
        return PARTIAL
    return VERIFIED


def _normalize_scalar(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return " ".join(normalized.split())


def _normalize_url(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return _normalize_scalar(value)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return _normalize_scalar(value)
    hostname = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return _normalize_scalar(value)
    if port is not None:
        hostname = "{0}:{1}".format(hostname, port)
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), hostname, path, parsed.query, ""))


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
        return parsed.scheme.lower() in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


def _is_distributor_owned_url(value: str) -> bool:
    """Recognize common LCSC/DigiKey/Mouser mirror host families."""

    try:
        hostname = (urlsplit(value.strip()).hostname or "").strip(".").casefold()
    except ValueError:
        return False
    labels = hostname.split(".")
    if len(labels) < 2:
        return False
    distributor_labels = {"lcsc", "szlcsc", "digikey", "mouser"}
    plausible_official_suffix = labels[-1] == "com" or len(labels[-1]) == 2
    return plausible_official_suffix and any(
        label in distributor_labels for label in labels[:-1]
    )
