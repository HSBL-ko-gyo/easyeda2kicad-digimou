"""Sanitized evidence helpers for opt-in credentialed provider smoke tests."""

from __future__ import annotations

# Global imports
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, cast

# Local imports
from easyeda2kicad_digimou.metadata.cache import sanitize_public_url
from easyeda2kicad_digimou.metadata.models import (
    DistributorRecord,
    identity_text,
    normalize_manufacturer,
    normalize_mpn,
)
from easyeda2kicad_digimou.providers import ProviderError


LIVE_EVIDENCE_SCHEMA_VERSION = 1
LIVE_EVIDENCE_STATES = frozenset(("pass", "fail", "skip"))
LIVE_EVIDENCE_PROVIDERS = frozenset(("digikey", "mouser"))
LIVE_PROVIDER_SMOKE_CONTRACT = {
    "digikey": (
        "Texas Instruments",
        "OPA333AIDBVR",
        "Product Information V4 KeywordSearch",
        "v4",
    ),
    "mouser": (
        "Texas Instruments",
        "LM321MF/NOPB",
        "Search API V2 SearchByPartnumber",
        "v2",
    ),
}
LIVE_SECRET_ENVIRONMENT_VARIABLES = (
    "DIGIKEY_CLIENT_ID",
    "DIGIKEY_CLIENT_SECRET",
    "MOUSER_API_KEY",
)
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_PART_NUMBER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+:-]*")
_TOP_LEVEL_KEYS = frozenset(
    (
        "schema_version",
        "repository_commit",
        "run_utc",
        "provider",
        "requested",
        "state",
        "operation",
        "api_version",
        "http_status_category",
        "failure_category",
        "identity",
        "test_config_sha256",
    )
)
_REQUEST_KEYS = frozenset(("manufacturer", "mpn"))
_IDENTITY_KEYS = frozenset(
    (
        "manufacturer",
        "mpn",
        "distributor_part_number",
        "product_url",
        "datasheet_url",
    )
)


def utc_timestamp() -> str:
    """Return a stable seconds-precision UTC timestamp."""

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def file_sha256(path: Path) -> str:
    """Hash test code/config without retaining its contents in evidence."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def http_status_category(status: Optional[int]) -> Optional[str]:
    """Return only a non-sensitive HTTP status category."""

    if status is None:
        return None
    if status == 403:
        return "403"
    if status == 429:
        return "429"
    return "{0}xx".format(status // 100)


def classify_provider_failure(error: ProviderError) -> Tuple[str, Optional[str]]:
    """Reduce a provider failure to a credential-safe stable category."""

    if error.status == 403:
        return "FORBIDDEN_OR_ACCOUNT_PLAN", "403"
    if error.status == 429:
        return "RATE_LIMITED", "429"
    if error.status is not None and 500 <= error.status <= 599:
        return "PROVIDER_OUTAGE", "5xx"
    return error.code, http_status_category(error.status)


def build_live_provider_evidence(
    *,
    repository_commit: str,
    provider: str,
    requested_manufacturer: str,
    requested_mpn: str,
    state: str,
    operation: str,
    api_version: str,
    test_config_sha256: str,
    record: Optional[DistributorRecord] = None,
    failure_category: Optional[str] = None,
    status_category: Optional[str] = None,
    run_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a strict allow-listed evidence record; raw responses are impossible."""

    normalized_provider = identity_text(provider, "provider").lower()
    requested_manufacturer = identity_text(
        requested_manufacturer, "requested_manufacturer"
    )
    requested_mpn = identity_text(requested_mpn, "requested_mpn")
    state = identity_text(state, "state").lower()
    if normalized_provider not in LIVE_EVIDENCE_PROVIDERS:
        raise ValueError("unsupported live provider")
    if state not in LIVE_EVIDENCE_STATES:
        raise ValueError("unsupported live evidence state")
    repository_commit = identity_text(repository_commit, "repository_commit").lower()
    if _SHA_RE.fullmatch(repository_commit) is None:
        raise ValueError("repository_commit must be a full Git SHA")
    test_config_sha256 = identity_text(test_config_sha256, "test_config_sha256").lower()
    if _SHA256_RE.fullmatch(test_config_sha256) is None:
        raise ValueError("test_config_sha256 must be SHA-256")
    run_utc = identity_text(run_utc or utc_timestamp(), "run_utc")
    if _UTC_RE.fullmatch(run_utc) is None:
        raise ValueError("run_utc must be seconds-precision UTC")

    identity: Optional[Dict[str, Optional[str]]] = None
    if state == "pass":
        if record is None:
            raise ValueError("passing evidence requires a normalized record")
        if record.provider != normalized_provider:
            raise ValueError("record provider does not match live provider")
        if normalize_manufacturer(record.manufacturer) != normalize_manufacturer(
            requested_manufacturer
        ):
            raise ValueError("record manufacturer does not exactly match request")
        if normalize_mpn(record.mpn) != normalize_mpn(requested_mpn):
            raise ValueError("record MPN does not exactly match request")
        distributor_part_number = identity_text(
            record.distributor_part_number,
            "distributor_part_number",
        )
        if _PART_NUMBER_RE.fullmatch(distributor_part_number) is None:
            raise ValueError("distributor part number is not well formed")
        identity = {
            "manufacturer": identity_text(record.manufacturer, "manufacturer"),
            "mpn": identity_text(record.mpn, "mpn"),
            "distributor_part_number": distributor_part_number,
            "product_url": sanitize_public_url(record.product_url),
            "datasheet_url": sanitize_public_url(record.datasheet_url),
        }
        failure_category = None
        status_category = "2xx"
    elif record is not None:
        raise ValueError("failed or skipped evidence cannot contain provider records")

    if state == "skip":
        failure_category = "CREDENTIALS_ABSENT"
        status_category = None
    elif state == "fail":
        failure_category = identity_text(failure_category, "failure_category")

    evidence = {
        "schema_version": LIVE_EVIDENCE_SCHEMA_VERSION,
        "repository_commit": repository_commit,
        "run_utc": run_utc,
        "provider": normalized_provider,
        "requested": {
            "manufacturer": requested_manufacturer,
            "mpn": requested_mpn,
        },
        "state": state,
        "operation": identity_text(operation, "operation"),
        "api_version": identity_text(api_version, "api_version"),
        "http_status_category": status_category,
        "failure_category": failure_category,
        "identity": identity,
        "test_config_sha256": test_config_sha256,
    }
    validate_live_provider_evidence(evidence)
    return evidence


def validate_live_provider_evidence(value: Mapping[str, Any]) -> None:
    """Reject unknown, missing, malformed, or semantically inconsistent fields."""

    if frozenset(value) != _TOP_LEVEL_KEYS:
        raise ValueError("live evidence top-level fields do not match schema v1")
    if value.get("schema_version") != LIVE_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported live evidence schema")
    repository_commit = value.get("repository_commit")
    test_hash = value.get("test_config_sha256")
    run_utc = value.get("run_utc")
    if (
        not isinstance(repository_commit, str)
        or _SHA_RE.fullmatch(repository_commit) is None
    ):
        raise ValueError("invalid live evidence repository commit")
    if not isinstance(test_hash, str) or _SHA256_RE.fullmatch(test_hash) is None:
        raise ValueError("invalid live evidence test hash")
    if not isinstance(run_utc, str) or _UTC_RE.fullmatch(run_utc) is None:
        raise ValueError("invalid live evidence UTC timestamp")
    provider = value.get("provider")
    state = value.get("state")
    if provider not in LIVE_EVIDENCE_PROVIDERS:
        raise ValueError("invalid live evidence provider")
    if state not in LIVE_EVIDENCE_STATES:
        raise ValueError("invalid live evidence state")
    request = value.get("requested")
    if not isinstance(request, dict) or frozenset(request) != _REQUEST_KEYS:
        raise ValueError("invalid live evidence request")
    identity_text(request.get("manufacturer"), "requested.manufacturer")
    identity_text(request.get("mpn"), "requested.mpn")
    operation = identity_text(value.get("operation"), "operation")
    api_version = identity_text(value.get("api_version"), "api_version")
    expected_manufacturer, expected_mpn, expected_operation, expected_version = (
        LIVE_PROVIDER_SMOKE_CONTRACT[cast(str, provider)]
    )
    if normalize_manufacturer(request.get("manufacturer")) != normalize_manufacturer(
        expected_manufacturer
    ):
        raise ValueError("live evidence requested manufacturer is not the canary")
    if normalize_mpn(request.get("mpn")) != normalize_mpn(expected_mpn):
        raise ValueError("live evidence requested MPN is not the canary")
    if operation != expected_operation or api_version != expected_version:
        raise ValueError("live evidence API operation/version does not match provider")

    identity = value.get("identity")
    failure = value.get("failure_category")
    status = value.get("http_status_category")
    if state == "pass":
        if not isinstance(identity, dict) or frozenset(identity) != _IDENTITY_KEYS:
            raise ValueError("passing evidence requires the exact identity fields")
        identity_text(identity.get("manufacturer"), "identity.manufacturer")
        identity_text(identity.get("mpn"), "identity.mpn")
        if normalize_manufacturer(
            identity.get("manufacturer")
        ) != normalize_manufacturer(request.get("manufacturer")):
            raise ValueError("evidence identity manufacturer does not match request")
        if normalize_mpn(identity.get("mpn")) != normalize_mpn(request.get("mpn")):
            raise ValueError("evidence identity MPN does not match request")
        part_number = identity_text(
            identity.get("distributor_part_number"),
            "identity.distributor_part_number",
        )
        if _PART_NUMBER_RE.fullmatch(part_number) is None:
            raise ValueError("invalid evidence distributor part number")
        for field_name in ("product_url", "datasheet_url"):
            url = identity.get(field_name)
            if url is not None and (
                not isinstance(url, str) or sanitize_public_url(url) != url
            ):
                raise ValueError("evidence URL is not sanitized")
        if failure is not None or status != "2xx":
            raise ValueError("passing evidence has a failure state")
    else:
        if identity is not None:
            raise ValueError("non-passing evidence cannot contain identity data")
        identity_text(failure, "failure_category")
        if state == "skip" and (failure != "CREDENTIALS_ABSENT" or status is not None):
            raise ValueError("skipped evidence must identify missing credentials")
        if (
            state == "fail"
            and status is not None
            and status
            not in (
                "3xx",
                "4xx",
                "5xx",
                "403",
                "429",
            )
        ):
            raise ValueError("invalid failure HTTP status category")


def write_live_provider_evidence(directory: Path, evidence: Mapping[str, Any]) -> Path:
    """Atomically write one sanitized provider result."""

    validate_live_provider_evidence(evidence)
    directory.mkdir(parents=True, exist_ok=True)
    provider = cast(str, evidence["provider"])
    filename = "{0}.json".format(provider)
    destination = directory / filename
    temporary = directory / (filename + ".tmp")
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)
    return destination


def secret_value_hit_names(
    payloads: Mapping[str, Any],
    secret_values: Sequence[str],
) -> Tuple[str, ...]:
    """Return only payload names containing exact configured secret values."""

    encoded_secrets = tuple(
        secret.encode("utf-8")
        for secret in secret_values
        if isinstance(secret, str) and len(secret) >= 4
    )
    hits = []
    for name, payload in payloads.items():
        if isinstance(payload, bytes):
            encoded = payload
        else:
            encoded = str(payload).encode("utf-8")
        if any(secret in encoded for secret in encoded_secrets):
            hits.append(str(name))
    return tuple(sorted(set(hits)))


def verify_live_evidence_directory(
    directory: Path,
    *,
    required_passes: Sequence[str] = (),
    secret_values: Sequence[str] = (),
) -> int:
    """Validate evidence files and exact-secret absence without printing values."""

    evidence_files = sorted(directory.glob("*.json")) if directory.is_dir() else []
    if not evidence_files:
        raise ValueError("no live-provider evidence files were produced")
    payloads: Dict[str, bytes] = {}
    states: Dict[str, str] = {}
    for path in evidence_files:
        payload = path.read_bytes()
        payloads[path.name] = payload
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError(
                "invalid live-provider evidence JSON: {0}".format(path.name)
            )
        if not isinstance(value, dict):
            raise ValueError("live-provider evidence root must be an object")
        validate_live_provider_evidence(value)
        provider = cast(str, value["provider"])
        if provider in states:
            raise ValueError("duplicate live-provider evidence")
        states[provider] = cast(str, value["state"])
    hits = secret_value_hit_names(payloads, secret_values)
    if hits:
        raise ValueError(
            "configured secret value found in evidence: {0}".format(", ".join(hits))
        )
    for provider in required_passes:
        normalized = provider.strip().lower()
        if normalized not in LIVE_EVIDENCE_PROVIDERS:
            raise ValueError("unsupported required provider")
        if states.get(normalized) != "pass":
            raise ValueError(
                "required provider did not produce passing evidence: {0}".format(
                    normalized
                )
            )
    return len(evidence_files)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate sanitized live evidence")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--require-pass", action="append", default=[])
    parser.add_argument("--secret-env", action="append", default=[])
    arguments = parser.parse_args(argv)
    secret_values = [
        os.environ.get(name, "")
        for name in arguments.secret_env
        if name in LIVE_SECRET_ENVIRONMENT_VARIABLES
    ]
    count = verify_live_evidence_directory(
        arguments.directory,
        required_passes=arguments.require_pass,
        secret_values=secret_values,
    )
    print("validated {0} sanitized live-provider evidence file(s)".format(count))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
