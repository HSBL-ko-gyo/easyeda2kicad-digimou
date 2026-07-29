"""Verify exact provider records in a JSON manifest without exposing secrets."""

from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

PROVIDERS = ("lcsc", "digikey", "mouser")
VERIFICATION_STATES = ("VERIFIED", "PARTIAL", "CAD_NOT_FOUND")


def _identity_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("identity value is missing")
    return unicodedata.normalize("NFKC", value).strip().casefold()


def check_manifest(
    document: Mapping[str, Any],
    *,
    manufacturer: str,
    mpn: str,
    providers: Sequence[str],
    verification_status: str,
) -> dict[str, Any]:
    identity = document.get("identity")
    records = document.get("distributor_records")
    errors = document.get("provider_errors")
    if (
        not isinstance(identity, Mapping)
        or not isinstance(records, list)
        or not isinstance(errors, Mapping)
        or document.get("verification_status") != verification_status
    ):
        raise ValueError("manifest shape or verification status is invalid")
    expected_manufacturer = _identity_text(manufacturer)
    expected_mpn = _identity_text(mpn)
    if (
        _identity_text(identity.get("manufacturer")) != expected_manufacturer
        or _identity_text(identity.get("mpn")) != expected_mpn
    ):
        raise ValueError("merged identity does not match")

    checked: list[str] = []
    for provider in providers:
        if provider in errors:
            raise ValueError("required provider has an error")
        matches = [
            record
            for record in records
            if isinstance(record, Mapping) and record.get("provider") == provider
        ]
        if len(matches) != 1:
            raise ValueError("required provider does not have exactly one record")
        record = matches[0]
        if (
            _identity_text(record.get("manufacturer")) != expected_manufacturer
            or _identity_text(record.get("mpn")) != expected_mpn
            or not isinstance(record.get("distributor_part_number"), str)
            or not record["distributor_part_number"].strip()
        ):
            raise ValueError("provider record identity is invalid")
        checked.append(provider)
    return {
        "status": "PASS",
        "verification_status": verification_status,
        "providers": checked,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--manufacturer", required=True)
    parser.add_argument("--mpn", required=True)
    parser.add_argument(
        "--provider",
        action="append",
        choices=PROVIDERS,
        required=True,
    )
    parser.add_argument(
        "--verification-status",
        choices=VERIFICATION_STATES,
        default="VERIFIED",
    )
    args = parser.parse_args(argv)
    try:
        raw = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("manifest root is not an object")
        result = check_manifest(
            raw,
            manufacturer=args.manufacturer,
            mpn=args.mpn,
            providers=args.provider,
            verification_status=args.verification_status,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        print(json.dumps({"status": "FAIL"}, separators=(",", ":")))
        return 1
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
