"""Read-only, credential-safe discovery commands for automation."""

from __future__ import annotations

# Global imports
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Local imports
from .machine import (
    EXIT_CAD,
    EXIT_INTERNAL,
    EXIT_INVALID_REQUEST,
    EXIT_PROJECT,
    EXIT_SUCCESS,
    MACHINE_SCHEMA_VERSION,
)
from .metadata.cache import sanitize_public_url
from .project_registration import (
    ProjectInspection,
    ProjectRegistrationError,
    ProjectRegistrationPlan,
    inspect_project,
    plan_project_registration,
)

HEADLESS_COMMANDS = (
    "capabilities",
    "inspect-project",
    "plan-acquire",
    "verify-artifacts",
)
_PROVIDERS = ("lcsc", "digikey", "mouser")
_CAD_SOURCES = ("easyeda", "digikey", "mouser", "auto")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class HeadlessCommandError(RuntimeError):
    """Typed command failure that never includes private input in its result."""

    def __init__(self, code: str, exit_code: int) -> None:
        self.code = code
        self.exit_code = exit_code
        super().__init__(code)


def capabilities_result(request_id: str) -> Dict[str, Any]:
    """Describe supported providers and commands without network access."""

    credentials = _credential_state()
    result = {
        "providers": {
            "lcsc": {
                "authentication_required": False,
                "authentication_configured": True,
                "guest_lookup_supported": True,
                "metadata_transport": "public-api",
            },
            "digikey": {
                "authentication_required": True,
                "authentication_configured": credentials["digikey"],
                "guest_lookup_supported": False,
                "metadata_transport": "official-authenticated-api",
            },
            "mouser": {
                "authentication_required": True,
                "authentication_configured": credentials["mouser"],
                "guest_lookup_supported": False,
                "metadata_transport": "official-authenticated-api",
            },
        },
        "cad_sources": {
            "easyeda": {
                "automated_download": True,
                "manual_handoff": False,
                "delivery_partner": None,
            },
            "digikey": {
                "automated_download": False,
                "manual_handoff": True,
                "delivery_partner": "ultralibrarian",
            },
            "mouser": {
                "automated_download": False,
                "manual_handoff": True,
                "delivery_partner": "samacsys",
            },
            "auto": {
                "automated_download": False,
                "manual_handoff": True,
                "delivery_partner": None,
            },
        },
        "commands": list(HEADLESS_COMMANDS),
    }
    return _headless_result(
        request_id=request_id,
        command="capabilities",
        status="SUCCEEDED",
        exit_code=EXIT_SUCCESS,
        result=result,
    )


def project_inspection_result(
    project: str | Path,
    *,
    request_id: str,
) -> Dict[str, Any]:
    """Inspect a KiCad project and return only project-relative paths."""

    try:
        inspection = inspect_project(project)
    except ProjectRegistrationError as error:
        raise HeadlessCommandError(error.code, EXIT_PROJECT) from None
    result = _project_inspection_projection(inspection)
    return _headless_result(
        request_id=request_id,
        command="inspect-project",
        status="SUCCEEDED",
        exit_code=EXIT_SUCCESS,
        result=result,
    )


def acquire_plan_result(
    arguments: Mapping[str, Any],
    *,
    request_id: str,
) -> Dict[str, Any]:
    """Build an output-free acquisition plan without provider requests."""

    manufacturer = _optional_text(arguments.get("manufacturer"))
    mpn = _optional_text(arguments.get("mpn"))
    lcsc_id = _optional_text(arguments.get("lcsc_id"))
    if mpn is None and lcsc_id is None:
        raise HeadlessCommandError("IDENTITY_REQUIRED", EXIT_INVALID_REQUEST)
    if lcsc_id is not None and not re.fullmatch(r"C[1-9][0-9]*", lcsc_id):
        raise HeadlessCommandError("LCSC_ID_INVALID", EXIT_INVALID_REQUEST)

    providers = _normalize_providers(arguments.get("providers"))
    required_providers = _normalize_providers(
        arguments.get("required_providers"), allow_empty=True
    )
    providers = list(dict.fromkeys([*providers, *required_providers]))
    cad_source = str(arguments.get("cad_source") or "easyeda").strip().lower()
    if cad_source not in _CAD_SOURCES:
        raise HeadlessCommandError("CAD_SOURCE_INVALID", EXIT_INVALID_REQUEST)
    cad_package = _optional_text(arguments.get("cad_package"))
    if cad_package is not None:
        package_path = Path(cad_package)
        if (
            cad_source not in ("digikey", "mouser")
            or package_path.is_symlink()
            or not package_path.is_file()
        ):
            raise HeadlessCommandError("CAD_PACKAGE_INVALID", EXIT_INVALID_REQUEST)

    offline = bool(arguments.get("offline"))
    register_project = bool(arguments.get("register_project_libraries"))
    require_project = bool(arguments.get("require_project_registration"))
    if require_project and not register_project:
        raise HeadlessCommandError(
            "PROJECT_REGISTRATION_NOT_REQUESTED",
            EXIT_INVALID_REQUEST,
        )
    project_changes: List[Dict[str, Any]] = []
    if register_project:
        project = _optional_text(arguments.get("project"))
        output = _optional_text(arguments.get("output"))
        if project is None or output is None:
            raise HeadlessCommandError(
                "PROJECT_REGISTRATION_INPUT_REQUIRED",
                EXIT_INVALID_REQUEST,
            )
        try:
            plan = plan_project_registration(
                project,
                output,
                require_artifacts=False,
            )
        except ProjectRegistrationError as error:
            raise HeadlessCommandError(error.code, EXIT_PROJECT) from None
        project_changes = _project_plan_projection(plan)
    elif arguments.get("project") is not None:
        raise HeadlessCommandError(
            "PROJECT_REGISTRATION_NOT_REQUESTED",
            EXIT_INVALID_REQUEST,
        )

    credential_state = _credential_state()
    warnings: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    if not offline:
        for provider in providers:
            if provider in ("digikey", "mouser") and not credential_state[provider]:
                warnings.append(_diagnostic("CREDENTIALS_MISSING", provider))
                actions.append(_credential_action(provider))

    steps = ["identity-validation"]
    steps.extend("metadata:{0}".format(provider) for provider in providers)
    if mpn is not None:
        steps.append("jlcpcb-resolution")
    steps.append("cad:{0}".format(cad_source))
    steps.append("artifact-validation")
    if register_project:
        steps.append("project-registration")

    write_operations = ["cad-artifacts"]
    if register_project:
        write_operations.append("project-library-tables")
    result = {
        "identity": {
            "manufacturer": manufacturer,
            "mpn": mpn,
            "lcsc_id": lcsc_id,
        },
        "providers": providers,
        "required_providers": required_providers,
        "authentication_configured": {
            provider: credential_state[provider] for provider in providers
        },
        "cad_source": cad_source,
        "cad_package_configured": cad_package is not None,
        "offline": offline,
        "network_access_planned": not offline,
        "requirements": {
            "providers": required_providers,
            "cad": bool(arguments.get("require_cad")),
            "jlcpcb_resolution": bool(arguments.get("require_jlcpcb_resolution")),
            "project_registration": require_project,
        },
        "steps": steps,
        "write_operations": write_operations,
        "project_changes": project_changes,
    }
    return _headless_result(
        request_id=request_id,
        command="plan-acquire",
        status="SUCCEEDED",
        exit_code=EXIT_SUCCESS,
        result=result,
        warnings=warnings,
        actions_required=actions,
    )


def verify_artifacts_result(
    result_path: str | Path,
    *,
    request_id: str,
    project_root: Optional[str | Path] = None,
    output_root: Optional[str | Path] = None,
    cwd_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Verify machine-result artifact hashes without modifying any path."""

    source = Path(result_path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise HeadlessCommandError(
            "MACHINE_RESULT_INVALID", EXIT_INVALID_REQUEST
        ) from None
    if (
        not isinstance(raw, Mapping)
        or raw.get("schema_version") != MACHINE_SCHEMA_VERSION
        or raw.get("command") != "acquire"
        or not isinstance(raw.get("artifacts"), list)
    ):
        raise HeadlessCommandError("MACHINE_RESULT_INVALID", EXIT_INVALID_REQUEST)

    bases: Dict[str, Optional[Path]] = {
        "project": Path(project_root).expanduser()
        if project_root is not None
        else None,
        "output": Path(output_root).expanduser() if output_root is not None else None,
        "cwd": (Path(cwd_root).expanduser() if cwd_root is not None else Path.cwd()),
    }
    verifications = [
        _verify_artifact(item, bases)
        for item in raw["artifacts"]
        if isinstance(item, Mapping)
    ]
    if len(verifications) != len(raw["artifacts"]):
        raise HeadlessCommandError("MACHINE_RESULT_INVALID", EXIT_INVALID_REQUEST)
    failed = sum(item["status"] != "VERIFIED" for item in verifications)
    result = {
        "artifacts": verifications,
        "summary": {
            "total": len(verifications),
            "verified": len(verifications) - failed,
            "failed": failed,
        },
    }
    errors = [_diagnostic("ARTIFACT_VERIFICATION_FAILED")] if failed else []
    return _headless_result(
        request_id=request_id,
        command="verify-artifacts",
        status="FAILED" if failed else "SUCCEEDED",
        exit_code=EXIT_CAD if failed else EXIT_SUCCESS,
        result=result,
        errors=errors,
    )


def error_result(
    command: str,
    *,
    request_id: str,
    code: str,
    exit_code: int,
) -> Dict[str, Any]:
    """Return a bounded command failure without echoing paths or exception text."""

    if command not in HEADLESS_COMMANDS:
        command = "capabilities"
        code = "INTERNAL_ERROR"
        exit_code = EXIT_INTERNAL
    return _headless_result(
        request_id=request_id,
        command=command,
        status="FAILED",
        exit_code=exit_code,
        result=None,
        errors=[_diagnostic(code)],
    )


def _headless_result(
    *,
    request_id: str,
    command: str,
    status: str,
    exit_code: int,
    result: Any,
    warnings: Iterable[Mapping[str, Any]] = (),
    errors: Iterable[Mapping[str, Any]] = (),
    actions_required: Iterable[Mapping[str, Any]] = (),
) -> Dict[str, Any]:
    return {
        "schema_version": MACHINE_SCHEMA_VERSION,
        "request_id": request_id,
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "result": result,
        "warnings": [dict(value) for value in warnings],
        "errors": [dict(value) for value in errors],
        "actions_required": [dict(value) for value in actions_required],
    }


def _project_inspection_projection(inspection: ProjectInspection) -> Dict[str, Any]:
    root = inspection.context.project_root.resolve()
    tables: Dict[str, Any] = {}
    for table in inspection.tables:
        try:
            relative = table.path.resolve().relative_to(root).as_posix()
        except ValueError:
            raise HeadlessCommandError("PROJECT_PATH_INVALID", EXIT_PROJECT) from None
        key = "symbol" if table.root_name == "sym_lib_table" else "footprint"
        tables[key] = {
            "path": relative,
            "path_base": "project",
            "exists": table.exists,
            "sha256": table.sha256,
            "entries": [
                {"nickname": entry.nickname, "uri": entry.uri}
                for entry in table.entries
            ],
        }
    return {
        "project_file": inspection.context.project_file.name,
        "project_file_path_base": "project",
        "tables": tables,
    }


def _project_plan_projection(plan: ProjectRegistrationPlan) -> List[Dict[str, Any]]:
    root = plan.context.project_root.resolve()
    output: List[Dict[str, Any]] = []
    for update in plan.updates:
        try:
            relative = update.path.resolve().relative_to(root).as_posix()
        except ValueError:
            raise HeadlessCommandError("PROJECT_PATH_INVALID", EXIT_PROJECT) from None
        output.append(
            {
                "path": relative,
                "path_base": "project",
                "action": update.action,
                "nickname": update.entry.nickname,
                "uri": update.entry.uri,
            }
        )
    return sorted(output, key=lambda item: (item["path"], item["nickname"]))


def _credential_state() -> Dict[str, bool]:
    return {
        "lcsc": True,
        "digikey": bool(
            os.environ.get("DIGIKEY_CLIENT_ID")
            and os.environ.get("DIGIKEY_CLIENT_SECRET")
        ),
        "mouser": bool(os.environ.get("MOUSER_API_KEY")),
    }


def _normalize_providers(value: Any, *, allow_empty: bool = False) -> List[str]:
    if value is None:
        return [] if allow_empty else ["lcsc"]
    if isinstance(value, str):
        candidates: Sequence[Any] = value.split(",")
    elif isinstance(value, Sequence):
        candidates = value
    else:
        raise HeadlessCommandError("PROVIDERS_INVALID", EXIT_INVALID_REQUEST)
    providers = [
        str(candidate).strip().lower()
        for candidate in candidates
        if str(candidate).strip()
    ]
    unsupported = set(providers).difference(_PROVIDERS)
    if unsupported or (not providers and not allow_empty):
        raise HeadlessCommandError("PROVIDERS_INVALID", EXIT_INVALID_REQUEST)
    return list(dict.fromkeys(providers))


def _credential_action(provider: str) -> Dict[str, Any]:
    setup_urls = {
        "digikey": "https://developer.digikey.com/products",
        "mouser": "https://www.mouser.com/api-search/",
    }
    return {
        "code": "CREDENTIALS_MISSING",
        "provider": provider,
        "action": "Configure credentials for the official provider API",
        "handoff_url": sanitize_public_url(setup_urls[provider]),
    }


def _diagnostic(code: str, provider: Optional[str] = None) -> Dict[str, Any]:
    return {"code": code, "provider": provider}


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _verify_artifact(
    raw: Mapping[str, Any],
    bases: Mapping[str, Optional[Path]],
) -> Dict[str, Any]:
    kind = raw.get("kind")
    path_text = raw.get("path")
    path_base = raw.get("path_base")
    expected = raw.get("sha256")
    if (
        not isinstance(kind, str)
        or not kind
        or not isinstance(path_text, str)
        or not isinstance(path_base, str)
        or path_base not in bases
        or not isinstance(expected, str)
        or _SHA256_RE.fullmatch(expected) is None
    ):
        raise HeadlessCommandError("MACHINE_RESULT_INVALID", EXIT_INVALID_REQUEST)
    verification = {
        "kind": kind,
        "path": path_text,
        "path_base": path_base,
        "expected_sha256": expected,
        "actual_sha256": None,
        "status": "BASE_MISSING",
    }
    relative = _safe_relative_path(path_text)
    if relative is None:
        verification["status"] = "UNSAFE_PATH"
        return verification
    base = bases[path_base]
    if base is None or base.is_symlink() or not base.is_dir():
        return verification
    resolved_base = base.resolve()
    if _contains_symlink(resolved_base, relative):
        verification["status"] = "UNSAFE_PATH"
        return verification
    candidate = resolved_base.joinpath(*relative.parts).resolve()
    try:
        candidate.relative_to(resolved_base)
    except ValueError:
        verification["status"] = "UNSAFE_PATH"
        return verification
    if not candidate.is_file():
        verification["status"] = "MISSING"
        return verification
    actual = _sha256_file(candidate)
    verification["actual_sha256"] = actual
    verification["status"] = "VERIFIED" if actual == expected else "HASH_MISMATCH"
    return verification


def _safe_relative_path(value: str) -> Optional[PurePosixPath]:
    if "\\" in value:
        return None
    path = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        path.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        return None
    return path


def _contains_symlink(base: Path, relative: PurePosixPath) -> bool:
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "HEADLESS_COMMANDS",
    "HeadlessCommandError",
    "acquire_plan_result",
    "capabilities_result",
    "error_result",
    "project_inspection_result",
    "verify_artifacts_result",
]
