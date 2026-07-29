from __future__ import annotations

# Global imports
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

# Local imports
from easyeda2kicad_digimou.live_provider import (
    LIVE_EVIDENCE_SCHEMA_VERSION,
    build_live_provider_evidence,
    classify_provider_failure,
    secret_value_hit_names,
    validate_live_provider_evidence,
    verify_live_evidence_directory,
    write_live_provider_evidence,
)
from easyeda2kicad_digimou.metadata.models import DistributorRecord
from easyeda2kicad_digimou.providers import (
    AuthFailedError,
    InvalidResponseError,
    NetworkError,
    NotFoundError,
    ProviderError,
    RateLimitedError,
)

COMMIT = "a" * 40
TEST_HASH = "b" * 64
RUN_UTC = "2026-07-29T04:00:00Z"


def _record(provider: str, mpn: str) -> DistributorRecord:
    part_numbers = {
        "digikey": "296-26269-1-ND",
        "mouser": "595-LM321MF/NOPB",
    }
    return DistributorRecord(
        provider=provider,
        manufacturer="Texas Instruments",
        mpn=mpn,
        distributor_part_number=part_numbers[provider],
        product_url=("https://example.test/product?token=seeded-private-value&lang=en"),
        datasheet_url=(
            "https://example.test/data.pdf?api_key=seeded-private-value&lang=en"
        ),
        stock=123,
        currency="USD",
    )


def _evidence(
    provider: str,
    mpn: str,
    *,
    state: str = "pass",
) -> Mapping[str, Any]:
    return build_live_provider_evidence(
        repository_commit=COMMIT,
        provider=provider,
        requested_manufacturer="Texas Instruments",
        requested_mpn=mpn,
        state=state,
        operation=(
            "Product Information V4 KeywordSearch"
            if provider == "digikey"
            else "Search API V2 SearchByPartnumber"
        ),
        api_version="v4" if provider == "digikey" else "v2",
        test_config_sha256=TEST_HASH,
        record=_record(provider, mpn) if state == "pass" else None,
        run_utc=RUN_UTC,
    )


def test_passing_evidence_is_allow_listed_stable_and_sanitized() -> None:
    evidence = _evidence("digikey", "OPA333AIDBVR")

    assert evidence["schema_version"] == LIVE_EVIDENCE_SCHEMA_VERSION
    assert evidence["state"] == "pass"
    assert evidence["http_status_category"] == "2xx"
    assert evidence["failure_category"] is None
    identity = evidence["identity"]
    assert isinstance(identity, dict)
    assert identity["manufacturer"] == "Texas Instruments"
    assert identity["mpn"] == "OPA333AIDBVR"
    assert identity["distributor_part_number"] == "296-26269-1-ND"
    assert identity["product_url"] == "https://example.test/product?lang=en"
    assert identity["datasheet_url"] == "https://example.test/data.pdf?lang=en"
    serialized = json.dumps(evidence, sort_keys=True)
    assert "seeded-private-value" not in serialized
    assert "stock" not in serialized
    assert "currency" not in serialized


@pytest.mark.parametrize(
    ("error", "expected_failure", "expected_status"),
    [
        (
            AuthFailedError("digikey", status=401, operation="oauth"),
            "AUTH_FAILED",
            "4xx",
        ),
        (
            AuthFailedError("digikey", status=403, operation="oauth"),
            "FORBIDDEN_OR_ACCOUNT_PLAN",
            "403",
        ),
        (
            RateLimitedError("mouser", status=429, operation="part-search"),
            "RATE_LIMITED",
            "429",
        ),
        (
            NetworkError("mouser", status=503, operation="part-search"),
            "PROVIDER_OUTAGE",
            "5xx",
        ),
        (
            InvalidResponseError("mouser", operation="part-search"),
            "INVALID_RESPONSE",
            None,
        ),
        (
            NotFoundError("mouser", operation="part-search"),
            "NOT_FOUND",
            None,
        ),
    ],
)
def test_failure_classification_is_typed_and_contains_no_raw_detail(
    error: ProviderError,
    expected_failure: str,
    expected_status: str | None,
) -> None:
    failure, status = classify_provider_failure(error)

    assert failure == expected_failure
    assert status == expected_status


def test_failure_and_skip_evidence_never_accept_provider_records() -> None:
    skipped = build_live_provider_evidence(
        repository_commit=COMMIT,
        provider="mouser",
        requested_manufacturer="Texas Instruments",
        requested_mpn="LM321MF/NOPB",
        state="skip",
        operation="Search API V2 SearchByPartnumber",
        api_version="v2",
        test_config_sha256=TEST_HASH,
        run_utc=RUN_UTC,
    )
    assert skipped["failure_category"] == "CREDENTIALS_ABSENT"
    assert skipped["identity"] is None

    with pytest.raises(ValueError, match="cannot contain provider records"):
        build_live_provider_evidence(
            repository_commit=COMMIT,
            provider="mouser",
            requested_manufacturer="Texas Instruments",
            requested_mpn="LM321MF/NOPB",
            state="fail",
            operation="Search API V2 SearchByPartnumber",
            api_version="v2",
            test_config_sha256=TEST_HASH,
            record=_record("mouser", "LM321MF/NOPB"),
            failure_category="INVALID_RESPONSE",
            run_utc=RUN_UTC,
        )


def test_evidence_schema_rejects_unknown_fields_and_identity_mismatch() -> None:
    evidence = dict(_evidence("digikey", "OPA333AIDBVR"))
    evidence["raw_response"] = {"private": True}
    with pytest.raises(ValueError, match="top-level"):
        validate_live_provider_evidence(evidence)

    with pytest.raises(ValueError, match="manufacturer"):
        build_live_provider_evidence(
            repository_commit=COMMIT,
            provider="digikey",
            requested_manufacturer="Wrong Manufacturer",
            requested_mpn="OPA333AIDBVR",
            state="pass",
            operation="Product Information V4 KeywordSearch",
            api_version="v4",
            test_config_sha256=TEST_HASH,
            record=_record("digikey", "OPA333AIDBVR"),
            run_utc=RUN_UTC,
        )


def test_atomic_evidence_directory_requires_both_provider_passes(
    tmp_path: Path,
) -> None:
    evidence_directory = tmp_path / "evidence"
    digikey_path = write_live_provider_evidence(
        evidence_directory,
        _evidence("digikey", "OPA333AIDBVR"),
    )
    mouser_path = write_live_provider_evidence(
        evidence_directory,
        _evidence("mouser", "LM321MF/NOPB"),
    )

    assert digikey_path.name == "digikey.json"
    assert mouser_path.name == "mouser.json"
    assert not list(evidence_directory.glob("*.tmp"))
    assert (
        verify_live_evidence_directory(
            evidence_directory,
            required_passes=("digikey", "mouser"),
            secret_values=("seeded-private-value",),
        )
        == 2
    )

    mouser_path.unlink()
    with pytest.raises(ValueError, match="required provider"):
        verify_live_evidence_directory(
            evidence_directory,
            required_passes=("digikey", "mouser"),
        )


def test_seeded_canary_scan_covers_every_output_surface() -> None:
    canary = "provider-live-secret-canary"
    seeded = {
        "stdout": "message " + canary,
        "stderr": "error " + canary,
        "cache": b'{"token":"' + canary.encode("utf-8") + b'"}',
        "manifest": '{"client_secret":"' + canary + '"}',
        "artifact": "url=https://example.test/?api_key=" + canary,
    }

    assert secret_value_hit_names(seeded, (canary,)) == (
        "artifact",
        "cache",
        "manifest",
        "stderr",
        "stdout",
    )
    safe = {name: "<redacted>" for name in seeded}
    assert secret_value_hit_names(safe, (canary,)) == ()


def test_live_workflow_is_manual_protected_read_only_and_low_traffic() -> None:
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "provider-live.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "contents: read" in workflow
    assert "environment: provider-live" in workflow
    assert "github.ref_name == github.event.repository.default_branch" in workflow
    assert "timeout-minutes: 10" in workflow
    assert "group: provider-live" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "-m live_provider --run-live-provider" in workflow.replace("\n", " ")
    assert "--require-pass digikey" in workflow.replace("\n", " ")
    assert "--require-pass mouser" in workflow.replace("\n", " ")
    assert "secrets.DIGIKEY_CLIENT_ID" in workflow
    assert "secrets.DIGIKEY_CLIENT_SECRET" in workflow
    assert "secrets.MOUSER_API_KEY" in workflow
    assert "upload-artifact@v4" in workflow


def test_readme_documents_explicit_live_opt_in_and_owner_gate() -> None:
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    section = readme.split(
        "### Credentialed provider live smoke (maintainers)", maxsplit=1
    )[1].split("The three-provider example below", maxsplit=1)[0]
    flattened = section.replace("\n", " ")

    assert "-m live_provider" in flattened
    assert "--run-live-provider" in flattened
    assert "DIGIKEY_CLIENT_ID" in section
    assert "DIGIKEY_CLIENT_SECRET" in section
    assert "MOUSER_API_KEY" in section
    assert "Check presence without printing values" in section
    assert "protected `provider-live` environment" in flattened
    assert "actual default branch" in flattened
    assert "one attempt per provider" in flattened
    assert "requires a pass from both providers" in flattened
    assert "Raw responses" in flattened
    assert "Issue #8 remains open" in section
