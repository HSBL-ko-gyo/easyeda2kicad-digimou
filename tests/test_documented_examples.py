"""Keep checked-in Release Candidate manifest examples aligned with models."""

from __future__ import annotations

# Global imports
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

# Local imports
from easyeda2kicad.metadata.models import MergedPart, normalize_mpn
from easyeda2kicad.metadata.symbol_fields import build_symbol_fields

EXAMPLE_ROOT = Path(__file__).parents[1] / "docs" / "examples"
EXAMPLES = (
    "OPA333AIDBVR.manifest.json",
    "LM321MF-NOPB.manifest.json",
    "CAD_NOT_FOUND.mock.manifest.json",
)


@pytest.mark.parametrize("filename", EXAMPLES)
def test_documented_manifest_is_lossless_and_exact(filename: str) -> None:
    document: dict[str, Any] = json.loads(
        (EXAMPLE_ROOT / filename).read_text(encoding="utf-8")
    )

    merged = MergedPart.from_dict(document)

    assert merged.to_dict() == document
    assert all(
        normalize_mpn(record.mpn) == merged.identity.mpn_normalized
        for record in merged.distributor_records
    )
    assert "provider_diagnostics" in document
    for record in merged.distributor_records:
        if record.raw_response_cache_key is not None:
            assert re.fullmatch(r"[0-9a-f]{64}", record.raw_response_cache_key)
        for url in (record.product_url, record.datasheet_url):
            if url is None:
                continue
            parsed = urlsplit(url)
            assert parsed.scheme in ("http", "https")
            assert parsed.hostname
            assert parsed.username is None
            assert parsed.password is None
            assert not {
                "apikey",
                "api_key",
                "client_secret",
                "access_token",
                "refresh_token",
                "token",
                "password",
            }.intersection(key.casefold() for key, _value in parse_qsl(parsed.query))
    if merged.cad is not None:
        for path_value in (
            merged.cad.symbol_path,
            merged.cad.footprint_path,
            merged.cad.model_3d_path,
        ):
            if path_value is None:
                continue
            path = Path(path_value)
            assert not path.is_absolute()
            assert ".." not in path.parts
            assert not re.match(r"^[A-Za-z]:[\\/]", str(path_value))
    symbol_fields = build_symbol_fields(merged)
    assert not {
        "Stock",
        "Price",
        "MOQ",
        "Currency",
        "Retrieved At",
        "Provider Errors",
        "Provider Diagnostics",
    }.intersection(symbol_fields)


def test_mock_cad_not_found_uses_explicit_manufacturer_authority() -> None:
    document: dict[str, Any] = json.loads(
        (EXAMPLE_ROOT / "CAD_NOT_FOUND.mock.manifest.json").read_text(encoding="utf-8")
    )

    manufacturer_sources = document["provenance"]["identity.manufacturer"]
    normalized_sources = document["provenance"]["identity.manufacturer_normalized"]

    assert manufacturer_sources == [
        {"provider": "user", "source_field": "--manufacturer"}
    ]
    assert normalized_sources == [
        {"provider": "user", "source_field": "normalized(--manufacturer)"}
    ]
    assert document["verification_status"] == "CAD_NOT_FOUND"
    assert document["cad"]["verification_status"] == "CAD_NOT_FOUND"
