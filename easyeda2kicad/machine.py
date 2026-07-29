"""Versioned, credential-safe machine result projection for CLI automation."""

from __future__ import annotations

# Global imports
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO, Dict, Iterable, List, Mapping, Optional, Tuple

# Local imports
from .metadata.cache import (
    redact_configured_secret_text,
    sanitize_public_url,
    strip_secrets,
)
from .metadata.merge import CAD_NOT_FOUND, CAD_PIN_PAD_MISMATCH, VERIFIED
from .metadata.models import (
    CAD_AUTH_REQUIRED,
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CAD_PACKAGE_READY,
    GUEST_LOOKUP_UNSUPPORTED,
    JLCPCB_IDENTITY_AMBIGUOUS,
    JLCPCB_IDENTITY_CONFLICT,
    JLCPCB_LOOKUP_FAILED,
    JLCPCB_PART_FOUND,
    MANUAL_GLOBAL_SOURCING_REQUIRED,
    DistributorRecord,
    MergedPart,
    ProviderDiagnostic,
)

MACHINE_SCHEMA_VERSION = "1"

EXIT_SUCCESS = 0
EXIT_INVALID_REQUEST = 2
EXIT_ACTION_REQUIRED = 3
EXIT_NOT_FOUND = 4
EXIT_IDENTITY = 5
EXIT_PROVIDER = 6
EXIT_CAD = 7
EXIT_PROJECT = 8
EXIT_INTERNAL = 70

MACHINE_EXIT_CODES = frozenset(
    (
        EXIT_SUCCESS,
        EXIT_INVALID_REQUEST,
        EXIT_ACTION_REQUIRED,
        EXIT_NOT_FOUND,
        EXIT_IDENTITY,
        EXIT_PROVIDER,
        EXIT_CAD,
        EXIT_PROJECT,
        EXIT_INTERNAL,
    )
)

_IDENTITY_CODES = frozenset(
    (
        "AMBIGUOUS",
        "MPN_MISMATCH",
        "MANUFACTURER_MISMATCH",
        "MANUFACTURER_UNVERIFIED",
        "CAD_IDENTITY_UNPROVEN",
        "CAD_IDENTITY_UNRESOLVED",
        JLCPCB_IDENTITY_AMBIGUOUS,
        JLCPCB_IDENTITY_CONFLICT,
    )
)
_PROVIDER_CODES = frozenset(
    (
        "AUTH_FAILED",
        "RATE_LIMITED",
        "NETWORK_ERROR",
        "INVALID_RESPONSE",
        "OFFLINE_CACHE_MISS",
        "CACHE_CORRUPT",
        "CACHE_WRITE_ERROR",
        JLCPCB_LOOKUP_FAILED,
    )
)
_ACTION_CODES = frozenset(
    (
        GUEST_LOOKUP_UNSUPPORTED,
        CAD_AUTH_REQUIRED,
        CAD_MANUAL_DOWNLOAD_REQUIRED,
        MANUAL_GLOBAL_SOURCING_REQUIRED,
    )
)
_CAD_ERROR_PREFIXES = (
    "CAD_",
    "EXPORT_",
)


def invalid_machine_result(
    request_id: str,
    *,
    code: str = "INVALID_REQUEST",
) -> Dict[str, Any]:
    """Return a schema-shaped invalid request without echoing untrusted input."""

    return _base_result(
        request_id=request_id,
        status="FAILED",
        exit_code=EXIT_INVALID_REQUEST,
        identity={"manufacturer": None, "mpn": None},
        errors=[_diagnostic(code)],
    )


def internal_machine_result(request_id: str) -> Dict[str, Any]:
    """Return a bounded unexpected-failure result without exception contents."""

    return _base_result(
        request_id=request_id,
        status="FAILED",
        exit_code=EXIT_INTERNAL,
        identity={"manufacturer": None, "mpn": None},
        errors=[_diagnostic("INTERNAL_ERROR")],
    )


def build_machine_result(
    arguments: Mapping[str, Any],
    merged: Optional[MergedPart],
    *,
    core_exit_code: int,
    request_id: str,
) -> Tuple[Dict[str, Any], int]:
    """Project one completed acquisition into schema v1 and its exit code."""

    identity = {
        "manufacturer": _optional_text(
            merged.identity.manufacturer
            if merged is not None
            else arguments.get("manufacturer")
        ),
        "mpn": _optional_text(
            merged.identity.mpn if merged is not None else arguments.get("mpn")
        ),
    }
    providers = _providers_projection(arguments, merged)
    cad = _cad_projection(arguments, merged)
    jlcpcb = _jlcpcb_projection(merged)
    artifacts, artifact_warnings = _artifact_projection(arguments, merged)
    project_changes = _project_changes_projection(arguments)

    warnings: List[Dict[str, Any]] = list(artifact_warnings)
    errors: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    ranked_failures: List[Tuple[int, str, Optional[str]]] = []

    required_providers = frozenset(
        str(value).strip().lower()
        for value in arguments.get("machine_required_provider_names", ())
        if str(value).strip()
    )
    for provider, provider_result in providers.items():
        if provider_result["status"] == "FOUND":
            continue
        diagnostic = provider_result.get("diagnostic")
        code = (
            str(diagnostic.get("code"))
            if isinstance(diagnostic, Mapping)
            else "PROVIDER_RECORD_MISSING"
        )
        if provider in required_providers:
            ranked_failures.append((_exit_for_code(code, provider), code, provider))
            if code in _ACTION_CODES:
                actions.append(
                    _action(
                        code,
                        provider=provider,
                        handoff_url=(
                            diagnostic.get("setup_url")
                            if isinstance(diagnostic, Mapping)
                            else None
                        ),
                    )
                )
            else:
                errors.append(_diagnostic(code, provider=provider))
        else:
            warnings.append(_diagnostic(code, provider=provider))
            if code in _ACTION_CODES:
                actions.append(
                    _action(
                        code,
                        provider=provider,
                        handoff_url=(
                            diagnostic.get("setup_url")
                            if isinstance(diagnostic, Mapping)
                            else None
                        ),
                    )
                )

    cad_action = _cad_action(merged)
    if cad_action is not None:
        actions.append(cad_action)
    explicit_cad = str(arguments.get("cad_source", "easyeda")).lower() in (
        "digikey",
        "mouser",
    )
    cad_required = bool(arguments.get("require_cad")) or explicit_cad
    if cad_required and not _cad_requirement_satisfied(merged):
        cad_code = _cad_failure_code(merged)
        exit_code = (
            EXIT_ACTION_REQUIRED
            if cad_code in _ACTION_CODES
            else _exit_for_code(cad_code)
        )
        ranked_failures.append((exit_code, cad_code, None))
        if exit_code != EXIT_ACTION_REQUIRED:
            errors.append(_diagnostic(cad_code))

    if arguments.get("require_jlcpcb_resolution"):
        jlcpcb_status = (
            str(jlcpcb.get("match_status")) if isinstance(jlcpcb, Mapping) else ""
        )
        if jlcpcb_status != JLCPCB_PART_FOUND:
            if jlcpcb_status == MANUAL_GLOBAL_SOURCING_REQUIRED:
                ranked_failures.append(
                    (
                        EXIT_ACTION_REQUIRED,
                        MANUAL_GLOBAL_SOURCING_REQUIRED,
                        "lcsc",
                    )
                )
                actions.append(
                    _action(
                        MANUAL_GLOBAL_SOURCING_REQUIRED,
                        provider="lcsc",
                    )
                )
            else:
                code = jlcpcb_status or JLCPCB_LOOKUP_FAILED
                ranked_failures.append((_exit_for_code(code, "lcsc"), code, "lcsc"))
                errors.append(_diagnostic(code, provider="lcsc"))
    elif (
        isinstance(jlcpcb, Mapping)
        and jlcpcb.get("match_status") == MANUAL_GLOBAL_SOURCING_REQUIRED
    ):
        warnings.append(_diagnostic(MANUAL_GLOBAL_SOURCING_REQUIRED, provider="lcsc"))
        actions.append(_action(MANUAL_GLOBAL_SOURCING_REQUIRED, provider="lcsc"))

    if arguments.get("require_project_registration") and not arguments.get(
        "_machine_project_succeeded"
    ):
        code = str(
            arguments.get("_machine_project_error") or "PROJECT_REGISTRATION_FAILED"
        )
        ranked_failures.append((EXIT_PROJECT, code, None))
        errors.append(_diagnostic(code))

    execution_code = _optional_text(arguments.get("_machine_error_code"))
    if core_exit_code != 0 and execution_code is None and not ranked_failures:
        execution_code = _infer_execution_code(merged)
    ranked_codes = {item[1] for item in ranked_failures}
    if core_exit_code != 0 and execution_code and execution_code not in ranked_codes:
        ranked_failures.append((_exit_for_code(execution_code), execution_code, None))
        if execution_code in _ACTION_CODES:
            actions.append(_action(execution_code))
        else:
            errors.append(_diagnostic(execution_code))
    elif core_exit_code != 0 and not ranked_failures:
        ranked_failures.append((EXIT_INTERNAL, "INTERNAL_ERROR", None))
        errors.append(_diagnostic("INTERNAL_ERROR"))

    warnings = _deduplicate_objects(warnings)
    errors = _deduplicate_objects(errors)
    actions = _deduplicate_objects(actions)
    exit_code = _select_exit_code(ranked_failures)
    if exit_code == EXIT_SUCCESS:
        status = "SUCCEEDED_WITH_WARNINGS" if warnings or actions else "SUCCEEDED"
    elif exit_code == EXIT_ACTION_REQUIRED:
        status = "ACTION_REQUIRED"
    else:
        status = "FAILED"

    document = _base_result(
        request_id=request_id,
        status=status,
        exit_code=exit_code,
        identity=identity,
        providers=providers,
        cad=cad,
        jlcpcb=jlcpcb,
        artifacts=artifacts,
        project_changes=project_changes,
        warnings=warnings,
        errors=errors,
        actions_required=actions,
    )
    return document, exit_code


def write_machine_json(
    value: Mapping[str, Any],
    *,
    stream: Optional[BinaryIO] = None,
) -> None:
    """Write exactly one UTF-8 JSON document to a binary output boundary."""

    safe_value = strip_secrets(value)
    payload = (
        json.dumps(
            safe_value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    target = sys.stdout.buffer if stream is None else stream
    target.write(payload)
    target.flush()


def _base_result(
    *,
    request_id: str,
    status: str,
    exit_code: int,
    identity: Mapping[str, Any],
    providers: Optional[Mapping[str, Any]] = None,
    cad: Optional[Mapping[str, Any]] = None,
    jlcpcb: Optional[Mapping[str, Any]] = None,
    artifacts: Optional[Iterable[Mapping[str, Any]]] = None,
    project_changes: Optional[Iterable[Mapping[str, Any]]] = None,
    warnings: Optional[Iterable[Mapping[str, Any]]] = None,
    errors: Optional[Iterable[Mapping[str, Any]]] = None,
    actions_required: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": MACHINE_SCHEMA_VERSION,
        "request_id": request_id,
        "command": "acquire",
        "status": status,
        "exit_code": exit_code,
        "identity": dict(identity),
        "providers": dict(providers or {}),
        "cad": dict(cad) if cad is not None else None,
        "jlcpcb": dict(jlcpcb) if jlcpcb is not None else None,
        "artifacts": list(artifacts or ()),
        "project_changes": list(project_changes or ()),
        "warnings": list(warnings or ()),
        "errors": list(errors or ()),
        "actions_required": list(actions_required or ()),
    }


def _providers_projection(
    arguments: Mapping[str, Any],
    merged: Optional[MergedPart],
) -> Dict[str, Any]:
    names = {
        str(value).strip().lower()
        for value in arguments.get("provider_names", ())
        if str(value).strip()
    }
    if merged is not None:
        names.update(record.provider.lower() for record in merged.distributor_records)
        names.update(merged.provider_errors)
    records: Dict[str, DistributorRecord] = {}
    if merged is not None:
        for record in merged.distributor_records:
            records.setdefault(record.provider.lower(), record)
    output: Dict[str, Any] = {}
    for name in sorted(names):
        selected_record = records.get(name)
        diagnostic = (
            merged.provider_diagnostics.get(name) if merged is not None else None
        )
        if selected_record is not None:
            output[name] = {
                "status": "FOUND",
                "record": _provider_record(selected_record),
                "diagnostic": None,
            }
        else:
            code = (
                merged.provider_errors.get(name, "PROVIDER_RECORD_MISSING")
                if merged is not None
                else "PROVIDER_RECORD_MISSING"
            )
            output[name] = {
                "status": "UNAVAILABLE",
                "record": None,
                "diagnostic": _provider_diagnostic(code, diagnostic),
            }
    return output


def _provider_record(record: DistributorRecord) -> Dict[str, Any]:
    return {
        "provider": record.provider.lower(),
        "distributor_part_number": _optional_text(record.distributor_part_number),
        "manufacturer": _optional_text(record.manufacturer),
        "mpn": _optional_text(record.mpn),
        "product_url": sanitize_public_url(record.product_url),
        "datasheet_url": sanitize_public_url(record.datasheet_url),
        "retrieved_at": _optional_text(record.retrieved_at),
    }


def _provider_diagnostic(
    code: str,
    diagnostic: Optional[ProviderDiagnostic],
) -> Dict[str, Any]:
    return {
        "code": code,
        "operation": diagnostic.operation if diagnostic is not None else None,
        "status": diagnostic.status if diagnostic is not None else None,
        "setup_url": (
            sanitize_public_url(diagnostic.setup_url)
            if diagnostic is not None
            else None
        ),
    }


def _cad_projection(
    arguments: Mapping[str, Any],
    merged: Optional[MergedPart],
) -> Optional[Dict[str, Any]]:
    if merged is None or (merged.cad is None and merged.cad_discovery is None):
        return None
    cad = merged.cad
    discovery = merged.cad_discovery
    provenance = discovery.provenance if discovery is not None else None
    return {
        "source": cad.source if cad is not None else None,
        "selected_source": (
            cad.source
            if cad is not None
            else discovery.requested_source
            if discovery is not None
            else _optional_text(arguments.get("cad_source"))
        ),
        "verification_status": (
            cad.verification_status
            if cad is not None
            else discovery.status
            if discovery is not None
            else None
        ),
        "distributor": (
            cad.distributor
            if cad is not None and cad.distributor
            else provenance.distributor
            if provenance is not None
            else None
        ),
        "delivery_partner": (
            cad.delivery_partner
            if cad is not None and cad.delivery_partner
            else provenance.delivery_partner
            if provenance is not None
            else None
        ),
        "model_creator": (
            cad.model_creator
            if cad is not None and cad.model_creator
            else provenance.model_creator
            if provenance is not None
            else None
        ),
        "retrieval_mode": (
            cad.retrieval_mode
            if cad is not None and cad.retrieval_mode
            else provenance.retrieval_mode
            if provenance is not None
            else None
        ),
        "package_hash": (
            cad.package_hash
            if cad is not None and cad.package_hash
            else provenance.package_hash
            if provenance is not None
            else None
        ),
        "discovery_status": discovery.status if discovery is not None else None,
    }


def _jlcpcb_projection(merged: Optional[MergedPart]) -> Optional[Dict[str, Any]]:
    if merged is None or merged.jlcpcb is None:
        return None
    resolution = merged.jlcpcb
    return {
        "jlcpcb_part_number": resolution.jlcpcb_part_number,
        "lcsc_part_number": resolution.lcsc_part_number,
        "match_status": resolution.match_status,
        "checked_at": resolution.checked_at,
        "stock": resolution.stock,
        "cache_state": resolution.cache_state,
        "manual_action_required": resolution.manual_action_required,
        "global_sourcing_candidates": [
            {
                "provider": candidate.provider,
                "manufacturer_part_number": candidate.manufacturer_part_number,
                "distributor_part_number": candidate.distributor_part_number,
                "product_url": sanitize_public_url(candidate.product_url),
            }
            for candidate in resolution.global_sourcing_candidates
        ],
    }


def _artifact_projection(
    arguments: Mapping[str, Any],
    merged: Optional[MergedPart],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if merged is None or merged.cad is None:
        return [], []
    cad = merged.cad
    artifacts: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    if cad.artifacts:
        for artifact in sorted(
            cad.artifacts,
            key=lambda item: (item.kind, item.relative_path, item.sha256),
        ):
            artifacts.append(
                {
                    "kind": artifact.kind,
                    "path": artifact.relative_path,
                    "path_base": "output",
                    "sha256": artifact.sha256,
                }
            )
        return artifacts, warnings

    candidates = (
        ("symbol", cad.symbol_path),
        ("footprint", cad.footprint_path),
        ("model_3d", cad.model_3d_path),
    )
    seen: set[Tuple[str, str]] = set()
    for kind, value in candidates:
        if value is None:
            continue
        path = Path(str(value))
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        else:
            path = path.resolve()
        if not path.is_file():
            continue
        portable = _portable_artifact_path(path, arguments)
        if portable is None:
            warnings.append(_diagnostic("ARTIFACT_PATH_UNREPRESENTABLE"))
            continue
        path_base, relative_path = portable
        marker = (path_base, relative_path)
        if marker in seen:
            continue
        seen.add(marker)
        artifacts.append(
            {
                "kind": kind,
                "path": relative_path,
                "path_base": path_base,
                "sha256": _sha256_file(path),
            }
        )
    artifacts.sort(key=lambda item: (item["kind"], item["path_base"], item["path"]))
    return artifacts, warnings


def _portable_artifact_path(
    path: Path,
    arguments: Mapping[str, Any],
) -> Optional[Tuple[str, str]]:
    bases: List[Tuple[str, Path]] = []
    project_root = arguments.get("project_root")
    if isinstance(project_root, str) and project_root:
        bases.append(("project", Path(project_root).resolve()))
    output = arguments.get("output")
    if isinstance(output, str) and output:
        bases.append(("output", Path(output).resolve().parent))
    bases.append(("cwd", Path.cwd().resolve()))
    for label, base in bases:
        try:
            relative = path.relative_to(base)
        except ValueError:
            continue
        portable = PurePosixPath(relative.as_posix())
        if (
            portable.is_absolute()
            or PureWindowsPath(portable.as_posix()).drive
            or any(part in ("", ".", "..") for part in portable.parts)
        ):
            continue
        return label, portable.as_posix()
    return None


def _project_changes_projection(arguments: Mapping[str, Any]) -> List[Dict[str, Any]]:
    plan = arguments.get("_machine_project_plan")
    if plan is None:
        return []
    context = getattr(plan, "context", None)
    project_root = getattr(context, "project_root", None)
    updates = getattr(plan, "updates", ())
    if not isinstance(project_root, Path):
        return []
    changes: List[Dict[str, Any]] = []
    for update in updates:
        path = getattr(update, "path", None)
        entry = getattr(update, "entry", None)
        if not isinstance(path, Path) or entry is None:
            continue
        try:
            relative = path.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            continue
        changes.append(
            {
                "path": relative,
                "path_base": "project",
                "action": str(getattr(update, "action", "unknown")),
                "nickname": str(getattr(entry, "nickname", "")),
                "uri": str(getattr(entry, "uri", "")),
            }
        )
    return sorted(changes, key=lambda item: (item["path"], item["nickname"]))


def _cad_action(merged: Optional[MergedPart]) -> Optional[Dict[str, Any]]:
    if merged is None or merged.cad_discovery is None:
        return None
    discovery = merged.cad_discovery
    action = discovery.action_required
    if action is None:
        return None
    provider = discovery.provenance.distributor or (
        discovery.request.source
        if discovery.request is not None
        else discovery.requested_source
    )
    return _action(
        action.code,
        provider=provider,
        handoff_url=action.setup_url or discovery.provenance.landing_url,
    )


def _cad_requirement_satisfied(merged: Optional[MergedPart]) -> bool:
    if merged is None or merged.cad is None:
        return False
    if merged.cad.verification_status == VERIFIED:
        return True
    return bool(
        merged.cad_discovery is not None
        and merged.cad_discovery.status == CAD_PACKAGE_READY
        and merged.cad.artifacts
    )


def _cad_failure_code(merged: Optional[MergedPart]) -> str:
    if merged is None:
        return "CAD_ACQUISITION_FAILED"
    if (
        merged.cad_discovery is not None
        and merged.cad_discovery.action_required is not None
    ):
        return merged.cad_discovery.action_required.code
    if merged.cad is not None:
        return merged.cad.verification_status
    return "CAD_ACQUISITION_FAILED"


def _infer_execution_code(merged: Optional[MergedPart]) -> Optional[str]:
    if merged is None:
        return None
    if merged.verification_status in (CAD_NOT_FOUND, CAD_PIN_PAD_MISMATCH):
        return merged.verification_status
    for _, code in sorted(merged.provider_errors.items()):
        if _exit_for_code(code) != EXIT_INTERNAL:
            return code
    if (
        merged.cad_discovery is not None
        and merged.cad_discovery.action_required is not None
    ):
        return merged.cad_discovery.action_required.code
    return None


def _exit_for_code(code: str, provider: Optional[str] = None) -> int:
    normalized = code.strip().upper()
    if normalized in _ACTION_CODES:
        return EXIT_ACTION_REQUIRED
    if normalized in ("NOT_FOUND", "PROVIDER_RECORD_MISSING") and provider == "lcsc":
        return EXIT_NOT_FOUND
    if normalized == "NOT_FOUND":
        return EXIT_NOT_FOUND
    if normalized in _IDENTITY_CODES:
        return EXIT_IDENTITY
    if normalized.startswith("PROJECT_"):
        return EXIT_PROJECT
    if normalized in _PROVIDER_CODES:
        return EXIT_PROVIDER
    if normalized == CAD_NOT_FOUND or normalized == CAD_PIN_PAD_MISMATCH:
        return EXIT_CAD
    if normalized.startswith(_CAD_ERROR_PREFIXES):
        return EXIT_CAD
    return EXIT_INTERNAL


def _select_exit_code(failures: Iterable[Tuple[int, str, Optional[str]]]) -> int:
    ordered = list(failures)
    if not ordered:
        return EXIT_SUCCESS
    priority = {
        EXIT_INVALID_REQUEST: 0,
        EXIT_INTERNAL: 1,
        EXIT_IDENTITY: 2,
        EXIT_CAD: 3,
        EXIT_PROJECT: 4,
        EXIT_PROVIDER: 5,
        EXIT_NOT_FOUND: 6,
        EXIT_ACTION_REQUIRED: 7,
    }
    return min(
        (item[0] for item in ordered),
        key=lambda code: priority.get(code, 99),
    )


def _diagnostic(
    code: str,
    *,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "code": code,
        "provider": provider,
    }


def _action(
    code: str,
    *,
    provider: Optional[str] = None,
    handoff_url: Any = None,
) -> Dict[str, Any]:
    actions = {
        GUEST_LOOKUP_UNSUPPORTED: "Configure credentials for the official provider API",
        CAD_AUTH_REQUIRED: "Configure credentials for the official CAD handoff",
        CAD_MANUAL_DOWNLOAD_REQUIRED: (
            "Download the official KiCad package and rerun with --cad-package"
        ),
        MANUAL_GLOBAL_SOURCING_REQUIRED: (
            "Search/order the exact MPN in JLCPCB Parts Manager Global Sourcing"
        ),
    }
    return {
        "code": code,
        "provider": provider,
        "action": actions.get(code, "Complete the required manual action"),
        "handoff_url": sanitize_public_url(_optional_text(handoff_url)),
    }


def _deduplicate_objects(values: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    unique: Dict[str, Dict[str, Any]] = {}
    for value in values:
        item = dict(value)
        marker = json.dumps(item, sort_keys=True, separators=(",", ":"))
        unique.setdefault(marker, item)
    return [unique[key] for key in sorted(unique)]


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "EXIT_ACTION_REQUIRED",
    "EXIT_CAD",
    "EXIT_IDENTITY",
    "EXIT_INTERNAL",
    "EXIT_INVALID_REQUEST",
    "EXIT_NOT_FOUND",
    "EXIT_PROJECT",
    "EXIT_PROVIDER",
    "EXIT_SUCCESS",
    "MACHINE_EXIT_CODES",
    "MACHINE_SCHEMA_VERSION",
    "build_machine_result",
    "internal_machine_result",
    "invalid_machine_result",
    "write_machine_json",
]
