"""Metadata orchestration kept separate from the legacy conversion path."""

from __future__ import annotations

# Global imports
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, cast

# Local imports
from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad.providers import (
    AmbiguousMatchError,
    CadProvider,
    DigiKeyProvider,
    EasyedaProvider,
    LcscProvider,
    MetadataProvider,
    MouserProvider,
    MpnMismatchError,
    NotFoundError,
    ProviderError,
)
from easyeda2kicad.providers.lcsc_client import JlcpcbCatalogueClient

from .cache import CacheCorruptError as MetadataCacheCorruptError
from .cache import CacheError, MetadataCache, sanitize_public_url
from .cad_identity import CadIdentity, CadIdentityError, extract_cad_identity
from .merge import CAD_NOT_FOUND, PARTIAL, VERIFIED, merge_records
from .models import (
    CadRecord,
    DistributorRecord,
    MergedPart,
    PartIdentity,
    ProviderDiagnostic,
    ProvenanceEntry,
    normalize_manufacturer,
    normalize_mpn,
)


MetadataProviderFactory = Callable[[str, EasyedaApi], MetadataProvider]
CadProviderFactory = Callable[[EasyedaApi], CadProvider]


class MetadataServiceError(RuntimeError):
    """A fatal, credential-safe orchestration error."""

    def __init__(self, code: str, detail: str, provider: Optional[str] = None) -> None:
        self.code = code
        self.provider = provider
        self.detail = detail
        label = "metadata"
        if provider:
            label = provider
        super().__init__("{0}: {1}: {2}".format(label, code, detail))


@dataclass
class MetadataResolution:
    distributor_records: List[DistributorRecord] = field(default_factory=list)
    cad: Optional[CadRecord] = None
    cad_data: Optional[Dict[str, Any]] = None
    cad_identity: Optional[CadIdentity] = None
    trusted_mpn: Optional[str] = None
    trusted_manufacturer: Optional[str] = None
    requested_mpn: Optional[str] = None
    requested_manufacturer: Optional[str] = None
    mpn_source: Optional[str] = None
    manufacturer_source: Optional[str] = None
    manufacturer_evidence: Dict[str, str] = field(default_factory=dict)
    rejected_manufacturers: Dict[str, str] = field(default_factory=dict)
    provider_errors: Dict[str, str] = field(default_factory=dict)
    provider_diagnostics: Dict[str, ProviderDiagnostic] = field(default_factory=dict)
    blocking_error: Optional[str] = None

    def to_merged(
        self,
        cad_verification_status: Optional[str] = None,
        *,
        overall_status: Optional[str] = None,
    ) -> MergedPart:
        """Build the public result after the caller has checked CAD pins/pads."""

        verification_status = overall_status or cad_verification_status
        if verification_status is None:
            if self.blocking_error:
                verification_status = PARTIAL
            elif self.cad is not None:
                verification_status = self.cad.verification_status
            else:
                verification_status = PARTIAL
        # The positional status is the CAD verification result retained for
        # compatibility. Callers use ``overall_status`` for non-CAD failures so
        # those cannot rewrite an already verified CadRecord.
        merged_cad = (
            replace(self.cad, verification_status=cad_verification_status)
            if self.cad is not None and cad_verification_status is not None
            else self.cad
        )
        if self.trusted_mpn and normalize_mpn(self.trusted_mpn):
            explicit_status: Optional[str] = verification_status
            if verification_status == VERIFIED:
                # Let merge_records downgrade VERIFIED to PARTIAL if a requested
                # metadata provider failed.
                explicit_status = None
            merged = merge_records(
                self.distributor_records,
                mpn=self.trusted_mpn,
                manufacturer=self.requested_manufacturer,
                cad=merged_cad,
                provider_errors=self.provider_errors,
                provider_diagnostics=self.provider_diagnostics,
                verification_status=explicit_status,
                manufacturer_seed=(
                    self.trusted_manufacturer
                    if not self.requested_manufacturer
                    else None
                ),
                manufacturer_seed_source=self.manufacturer_source,
                manufacturer_evidence_values=self.manufacturer_evidence,
                manufacturer_diagnostic_values=self.rejected_manufacturers,
            )
            _set_identity_provenance(merged, "mpn", self.mpn_source)
            return merged

        # An ID-only confirmed CAD miss can legitimately lack any MPN evidence.
        status = verification_status or PARTIAL
        merged = MergedPart(
            identity=PartIdentity(
                manufacturer=self.trusted_manufacturer,
                mpn=self.trusted_mpn or "",
            ),
            distributor_records=list(self.distributor_records),
            cad=merged_cad,
            verification_status=status,
            provider_errors=dict(sorted(self.provider_errors.items())),
            provider_diagnostics=dict(sorted(self.provider_diagnostics.items())),
        )
        _set_identity_provenance(merged, "mpn", self.mpn_source)
        _set_identity_provenance(merged, "manufacturer", self.manufacturer_source)
        return merged


def create_metadata_provider(name: str, api: EasyedaApi) -> MetadataProvider:
    """Create one official/public-API-backed metadata adapter."""

    if name == "lcsc":
        if not isinstance(api, EasyedaApi):
            # Structural test/compatibility clients remain injectable; the
            # production EasyedaApi path below is always split.
            return LcscProvider(api=cast(Any, api))
        return LcscProvider(
            api=JlcpcbCatalogueClient(
                offline=api.offline,
                ssl_context=api.ssl_context,
                headers=api.headers,
            )
        )
    if name == "digikey":
        return DigiKeyProvider()
    if name == "mouser":
        return MouserProvider()
    raise ValueError("unsupported metadata provider: {0}".format(name))


def create_cad_provider(api: EasyedaApi) -> CadProvider:
    return EasyedaProvider(api=api)


def resolve_metadata(
    *,
    requested_mpn: Optional[str],
    requested_manufacturer: Optional[str],
    requested_lcsc_id: Optional[str],
    provider_names: Sequence[str],
    cad_api: EasyedaApi,
    metadata_api: Optional[EasyedaApi] = None,
    cache: Optional[MetadataCache] = None,
    offline: bool = False,
    refresh_metadata: bool = False,
    provider_factory: MetadataProviderFactory = create_metadata_provider,
    cad_provider_factory: CadProviderFactory = create_cad_provider,
) -> MetadataResolution:
    """Resolve exact distributor metadata and EasyEDA-only CAD identity."""

    if offline and refresh_metadata:
        raise ValueError("offline and refresh_metadata are mutually exclusive")
    if offline:
        # Enforce strict offline behavior for direct service callers too.
        cad_api.offline = True
        cad_api.use_cache = True
        if metadata_api is not None:
            metadata_api.offline = True
    cache = cache or MetadataCache()
    metadata_api = metadata_api or cad_api
    selected = tuple(dict.fromkeys(name.strip().lower() for name in provider_names))
    result = MetadataResolution(
        trusted_mpn=_clean(requested_mpn),
        trusted_manufacturer=_clean(requested_manufacturer),
        requested_mpn=_clean(requested_mpn),
        requested_manufacturer=_clean(requested_manufacturer),
        mpn_source="user" if _clean(requested_mpn) else None,
        manufacturer_source="user" if _clean(requested_manufacturer) else None,
    )

    lcsc_provider = provider_factory("lcsc", metadata_api)
    lcsc_record: Optional[DistributorRecord] = None
    lcsc_id_lookup_attempted = False
    lcsc_id = _clean(requested_lcsc_id)

    # MPN-only requests need a conservative LCSC exact match to identify the
    # sole permitted CAD source.  A provider/network failure is not CAD_NOT_FOUND.
    if lcsc_id is None and result.trusted_mpn:
        try:
            lcsc_record = _cached_exact_lookup(
                lcsc_provider,
                cache,
                result.trusted_manufacturer,
                result.trusted_mpn,
                offline=offline,
                refresh=refresh_metadata,
            )
            lcsc_id = _clean(lcsc_record.distributor_part_number)
            if not lcsc_id or not re.fullmatch(r"C[1-9][0-9]*", lcsc_id):
                raise MetadataServiceError(
                    "INVALID_RESPONSE",
                    "exact result omitted a canonical LCSC ID",
                    "lcsc",
                )
            result.trusted_manufacturer = result.trusted_manufacturer or _clean(
                lcsc_record.manufacturer
            )
            if result.manufacturer_source is None and result.trusted_manufacturer:
                result.manufacturer_source = "lcsc"
            _remember_manufacturer_evidence(result, "lcsc", lcsc_record.manufacturer)
        except NotFoundError:
            result.cad = CadRecord(source="easyeda", verification_status=CAD_NOT_FOUND)
        except (AmbiguousMatchError, MpnMismatchError) as error:
            raise _fatal_provider_error(error) from None
        except (ProviderError, CacheError) as error:
            code = _error_code(error)
            _record_provider_error(result, "lcsc", error)
            result.blocking_error = code

    # Fetch CAD before contacting DigiKey/Mouser so an explicit LCSC/MPN
    # mismatch stops without creating files or making unnecessary requests.
    if lcsc_id is not None and result.blocking_error is None:
        cad_provider = cad_provider_factory(cad_api)
        try:
            cad_record, cad_data = cad_provider.get_cad_data(lcsc_id)
            try:
                # The CAD payload itself must prove the requested LCSC ID and
                # reconcile any identity fields it does contain.  Missing MPN
                # or manufacturer evidence can be completed by the mandatory
                # LCSC ID lookup below; contradictory evidence cannot.
                identity = extract_cad_identity(
                    cad_data,
                    requested_lcsc_id=lcsc_id,
                )
                identity = extract_cad_identity(
                    cad_data,
                    requested_lcsc_id=lcsc_id,
                    requested_mpn=(result.trusted_mpn if identity.mpn else None),
                )
            except CadIdentityError as error:
                raise MetadataServiceError(
                    error.code, error.detail, "easyeda"
                ) from None
            cad_record.lcsc_part_number = identity.lcsc_id
            cad_record.easyeda_component_id = identity.easyeda_component_id
            cad_record.verification_status = PARTIAL
            result.cad = cad_record
            result.cad_data = cad_data
            result.cad_identity = identity
            result.trusted_mpn = result.trusted_mpn or identity.mpn
            if result.mpn_source is None and result.trusted_mpn:
                result.mpn_source = "easyeda"
            result.trusted_manufacturer = (
                result.trusted_manufacturer or identity.manufacturer
            )
            if result.manufacturer_source is None and result.trusted_manufacturer:
                result.manufacturer_source = "easyeda"
            _remember_manufacturer_evidence(result, "easyeda", identity.manufacturer)
        except NotFoundError:
            result.cad = CadRecord(
                source="easyeda",
                lcsc_part_number=lcsc_id,
                verification_status=CAD_NOT_FOUND,
            )
        except (ProviderError, CacheError) as error:
            code = _error_code(error)
            _record_provider_error(result, "easyeda", error)
            result.blocking_error = code

    # A complete CAD identity already verifies an explicit LCSC/MPN pair and
    # supplies the MPN needed by external providers. If CAD is unavailable or
    # omits required MPN/manufacturer evidence, complete that proof through the
    # LCSC identity endpoint regardless of manifest output selection. The
    # fetched LCSC record is still emitted only when selected.
    cad_identity_incomplete = bool(
        result.cad_identity is None
        or result.cad_identity.mpn is None
        or (_clean(requested_manufacturer) and result.cad_identity.manufacturer is None)
    )
    explicit_pair_lookup = bool(
        _clean(requested_lcsc_id) and _clean(requested_mpn) and cad_identity_incomplete
    )
    explicit_manufacturer_lookup = bool(
        lcsc_id
        and _clean(requested_manufacturer)
        and (
            result.cad_identity is None
            or normalize_manufacturer(result.cad_identity.manufacturer)
            != normalize_manufacturer(requested_manufacturer)
        )
    )
    external_provider_needs_identity = bool(
        lcsc_id
        and any(name != "lcsc" for name in selected)
        and not result.trusted_mpn
        and (
            (result.cad is not None and result.cad.verification_status == CAD_NOT_FOUND)
            or result.cad_identity is not None
        )
    )
    mandatory_identity_lookup = (
        explicit_pair_lookup
        or explicit_manufacturer_lookup
        or external_provider_needs_identity
    )
    mandatory_lookup_detail = (
        "explicit LCSC ID and MPN could not be verified"
        if explicit_pair_lookup
        else "explicit manufacturer could not be verified for the LCSC ID"
        if explicit_manufacturer_lookup
        else "LCSC ID could not be resolved to an exact MPN"
    )
    should_lookup_lcsc = bool(
        lcsc_record is None
        and lcsc_id is not None
        and ("lcsc" in selected or mandatory_identity_lookup)
    )
    if should_lookup_lcsc and lcsc_id is not None:
        lcsc_id_lookup_attempted = True
        try:
            lcsc_record = _cached_id_lookup(
                lcsc_provider,
                cache,
                lcsc_id,
                offline=offline,
                refresh=refresh_metadata,
            )
            _validate_record_identity(
                lcsc_record,
                result.trusted_mpn,
                _clean(requested_manufacturer),
            )
            result.trusted_mpn = result.trusted_mpn or _clean(lcsc_record.mpn)
            if result.mpn_source is None and result.trusted_mpn:
                result.mpn_source = "lcsc"
            result.trusted_manufacturer = result.trusted_manufacturer or _clean(
                lcsc_record.manufacturer
            )
            if result.manufacturer_source is None and result.trusted_manufacturer:
                result.manufacturer_source = "lcsc"
            _remember_manufacturer_evidence(result, "lcsc", lcsc_record.manufacturer)
        except NotFoundError as error:
            if mandatory_identity_lookup:
                raise MetadataServiceError(
                    error.code,
                    mandatory_lookup_detail,
                    "lcsc",
                ) from None
            _record_provider_error(result, "lcsc", error)
        except (AmbiguousMatchError, MpnMismatchError) as error:
            raise _fatal_provider_error(error) from None
        except (ProviderError, CacheError) as error:
            if mandatory_identity_lookup:
                raise MetadataServiceError(
                    _error_code(error),
                    mandatory_lookup_detail,
                    "lcsc",
                ) from None
            _record_provider_error(result, "lcsc", error)

    if "lcsc" in selected and lcsc_record is not None:
        _append_once(result.distributor_records, lcsc_record)

    # Other providers are metadata-only and are independent of CAD success.
    for name in selected:
        if name == "lcsc":
            continue
        if not result.trusted_mpn:
            result.provider_errors[name] = "IDENTITY_UNRESOLVED"
            continue
        provider = provider_factory(name, metadata_api)
        try:
            record = _cached_exact_lookup(
                provider,
                cache,
                _clean(requested_manufacturer),
                result.trusted_mpn,
                offline=offline,
                refresh=refresh_metadata,
            )
            _validate_record_identity(
                record, result.trusted_mpn, _clean(requested_manufacturer)
            )
            if (
                not _clean(requested_manufacturer)
                and not _manufacturer_is_evidenced(result, record.manufacturer)
                and lcsc_id is not None
                and lcsc_record is None
                and not lcsc_id_lookup_attempted
            ):
                # An external display name that differs from the sole CAD
                # evidence may still be exact, but only a catalogue record tied
                # to this canonical LCSC ID and MPN can prove that alias.
                lcsc_id_lookup_attempted = True
                try:
                    candidate = _cached_id_lookup(
                        lcsc_provider,
                        cache,
                        lcsc_id,
                        offline=offline,
                        refresh=refresh_metadata,
                    )
                    _validate_record_identity(
                        candidate,
                        result.trusted_mpn,
                        None,
                    )
                except MetadataServiceError as error:
                    if error.code == "MPN_MISMATCH":
                        raise
                except (ProviderError, CacheError):
                    pass
                else:
                    lcsc_record = candidate
                    result.trusted_manufacturer = result.trusted_manufacturer or _clean(
                        lcsc_record.manufacturer
                    )
                    if (
                        result.manufacturer_source is None
                        and result.trusted_manufacturer
                    ):
                        result.manufacturer_source = "lcsc"
                    _remember_manufacturer_evidence(
                        result, "lcsc", lcsc_record.manufacturer
                    )
                    if "lcsc" in selected:
                        _append_once(result.distributor_records, lcsc_record)
            if not _clean(requested_manufacturer) and not _manufacturer_is_evidenced(
                result, record.manufacturer
            ):
                result.provider_errors[name] = "MANUFACTURER_UNVERIFIED"
                rejected_manufacturer = _clean(record.manufacturer)
                if rejected_manufacturer:
                    result.rejected_manufacturers[name] = rejected_manufacturer
                continue
            result.distributor_records.append(record)
        except (AmbiguousMatchError, MpnMismatchError) as error:
            raise _fatal_provider_error(error) from None
        except (ProviderError, CacheError) as error:
            _record_provider_error(result, name, error)

    return result


def _cached_exact_lookup(
    provider: MetadataProvider,
    cache: MetadataCache,
    manufacturer: Optional[str],
    mpn: str,
    *,
    offline: bool,
    refresh: bool,
) -> DistributorRecord:
    request = cache.canonical_request(
        provider.name,
        "search_exact_mpn",
        mpn=mpn,
        manufacturer=manufacturer,
        options={"provider_context": _provider_cache_context(provider)},
    )
    return _cached_lookup(
        provider,
        cache,
        request,
        lambda: provider.search_exact_mpn(manufacturer, mpn),
        validator=lambda record: _validate_cached_record(
            record,
            provider.name,
            expected_mpn=mpn,
            expected_manufacturer=manufacturer,
        ),
        offline=offline,
        refresh=refresh,
    )


def _cached_id_lookup(
    provider: MetadataProvider,
    cache: MetadataCache,
    part_id: str,
    *,
    offline: bool,
    refresh: bool,
) -> DistributorRecord:
    request = cache.canonical_request(
        provider.name,
        "get_part_by_distributor_id",
        options={
            "part_id": part_id,
            "provider_context": _provider_cache_context(provider),
        },
    )
    return _cached_lookup(
        provider,
        cache,
        request,
        lambda: provider.get_part_by_distributor_id(part_id),
        validator=lambda record: _validate_cached_record(
            record,
            provider.name,
            expected_distributor_id=part_id,
        ),
        offline=offline,
        refresh=refresh,
    )


def _cached_lookup(
    provider: MetadataProvider,
    cache: MetadataCache,
    request: Mapping[str, Any],
    fetch: Callable[[], DistributorRecord],
    validator: Callable[[DistributorRecord], None],
    *,
    offline: bool,
    refresh: bool,
) -> DistributorRecord:
    key = cache.get_cache_key(provider.name, request)
    cached = cache.read_normalized(provider.name, key, offline=offline, refresh=refresh)
    if cached is not None:
        try:
            cached_record = DistributorRecord.from_dict(cached)
            if cached_record.raw_response_cache_key != key:
                raise ValueError("cached raw-response key mismatch")
            validator(cached_record)
            cached_record.product_url = sanitize_public_url(cached_record.product_url)
            cached_record.datasheet_url = sanitize_public_url(
                cached_record.datasheet_url
            )
            return cached_record
        except (OverflowError, TypeError, ValueError):
            if offline:
                raise MetadataCacheCorruptError(
                    provider.name, key, "normalized record is invalid"
                ) from None

    record = fetch()
    try:
        validator(record)
    except (OverflowError, TypeError, ValueError) as error:
        raise MetadataServiceError(
            "INVALID_RESPONSE",
            "provider returned a record that failed exact validation",
            provider.name,
        ) from error
    # Only public HTTP(S) links cross the provider boundary. This happens
    # before normalized cache persistence and also makes the first online run
    # identical to a later cache hit.
    record.product_url = sanitize_public_url(record.product_url)
    record.datasheet_url = sanitize_public_url(record.datasheet_url)
    record.raw_response_cache_key = key
    raw = getattr(provider, "last_raw_response", None)
    try:
        cache.write(
            provider.name,
            key,
            raw if raw is not None else {},
            record.to_dict(),
            request=request,
            retrieved_at=record.retrieved_at,
        )
    except OSError:
        raise MetadataServiceError(
            "CACHE_WRITE_ERROR", "metadata cache could not be written", provider.name
        ) from None
    return record


def _validate_record_identity(
    record: DistributorRecord,
    expected_mpn: Optional[str],
    expected_manufacturer: Optional[str],
) -> None:
    if expected_mpn and normalize_mpn(record.mpn) != normalize_mpn(expected_mpn):
        raise MetadataServiceError(
            "MPN_MISMATCH",
            "provider result does not match the verified MPN",
            record.provider,
        )
    if expected_manufacturer and normalize_manufacturer(
        record.manufacturer
    ) != normalize_manufacturer(expected_manufacturer):
        raise MetadataServiceError(
            "MANUFACTURER_MISMATCH",
            "provider result does not match the requested manufacturer",
            record.provider,
        )


def _validate_cached_record(
    record: DistributorRecord,
    provider_name: str,
    *,
    expected_mpn: Optional[str] = None,
    expected_manufacturer: Optional[str] = None,
    expected_distributor_id: Optional[str] = None,
) -> None:
    if record.provider != provider_name:
        raise ValueError("cached provider does not match its envelope")
    if expected_mpn and normalize_mpn(record.mpn) != normalize_mpn(expected_mpn):
        raise ValueError("cached MPN failed exact validation")
    if expected_manufacturer and normalize_manufacturer(
        record.manufacturer
    ) != normalize_manufacturer(expected_manufacturer):
        raise ValueError("cached manufacturer failed exact validation")
    if (
        expected_distributor_id
        and (record.distributor_part_number or "").strip().casefold()
        != expected_distributor_id.strip().casefold()
    ):
        raise ValueError("cached distributor ID failed exact validation")


def _provider_cache_context(provider: MetadataProvider) -> Dict[str, str]:
    getter = getattr(provider, "get_cache_context", None)
    if not callable(getter):
        return {}
    context = getter()
    if not isinstance(context, Mapping):
        raise MetadataServiceError(
            "INVALID_RESPONSE", "provider cache context is invalid", provider.name
        )
    return {str(key): str(value) for key, value in context.items()}


def _set_identity_provenance(
    merged: MergedPart, field_name: str, source: Optional[str]
) -> None:
    if not source:
        return
    source_fields = {
        ("mpn", "user"): "--mpn",
        ("manufacturer", "user"): "--manufacturer",
        ("mpn", "easyeda"): "dataStr.head.c_para.Manufacturer Part",
        (
            "manufacturer",
            "easyeda",
        ): "dataStr.head.c_para.Manufacturer",
    }
    source_field = source_fields.get((field_name, source), field_name)
    merged.provenance["identity.{0}".format(field_name)] = [
        ProvenanceEntry(provider=source, source_field=source_field)
    ]
    merged.provenance["identity.{0}_normalized".format(field_name)] = [
        ProvenanceEntry(
            provider=source,
            source_field="normalized({0})".format(field_name),
        )
    ]
    merged.provenance = {
        key: merged.provenance[key] for key in sorted(merged.provenance)
    }


def _remember_manufacturer_evidence(
    result: MetadataResolution,
    source: str,
    manufacturer: Optional[str],
) -> None:
    display = _clean(manufacturer)
    if not display:
        return
    result.manufacturer_evidence.setdefault(source, display)


def _manufacturer_is_evidenced(
    result: MetadataResolution, manufacturer: Optional[str]
) -> bool:
    normalized = normalize_manufacturer(manufacturer)
    return bool(normalized) and any(
        normalize_manufacturer(evidence) == normalized
        for evidence in result.manufacturer_evidence.values()
    )


def _append_once(records: List[DistributorRecord], record: DistributorRecord) -> None:
    marker = (
        record.provider,
        record.distributor_part_number,
        normalize_mpn(record.mpn),
    )
    for existing in records:
        if (
            existing.provider,
            existing.distributor_part_number,
            normalize_mpn(existing.mpn),
        ) == marker:
            return
    records.append(record)


def _fatal_provider_error(error: ProviderError) -> MetadataServiceError:
    detail = (
        "exact identity is not unique"
        if error.code == "AMBIGUOUS"
        else "provider result does not match the requested exact identity"
    )
    return MetadataServiceError(error.code, detail, error.provider)


def _error_code(error: Any) -> str:
    return str(getattr(error, "code", getattr(error, "category", "PROVIDER_ERROR")))


def _record_provider_error(
    result: MetadataResolution, provider: str, error: Any
) -> None:
    """Retain the compatibility code plus credential-safe structured context."""

    code = _error_code(error)
    operation = getattr(error, "operation", None)
    status = getattr(error, "status", None)
    result.provider_errors[provider] = code
    result.provider_diagnostics[provider] = ProviderDiagnostic(
        code=code,
        operation=operation if isinstance(operation, str) and operation else None,
        status=(
            int(status)
            if isinstance(status, int) and not isinstance(status, bool) and status >= 0
            else None
        ),
    )


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "MetadataResolution",
    "MetadataServiceError",
    "create_cad_provider",
    "create_metadata_provider",
    "resolve_metadata",
]
