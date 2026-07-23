from __future__ import annotations

# Global imports
import os

import pytest

# Local imports
from easyeda2kicad.metadata.models import normalize_mpn
from easyeda2kicad.providers import DigiKeyProvider, MouserProvider


@pytest.mark.network
def test_digikey_live_exact_mpn_smoke() -> None:
    required = ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET")
    if not all(os.environ.get(name, "").strip() for name in required):
        pytest.skip(
            "DigiKey live smoke requires DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET"
        )

    requested_mpn = "OPA333AIDBVR"
    provider = DigiKeyProvider(timeout=30.0)
    # One OAuth transaction and one keyword request are the minimum. Disable
    # automatic retries so this smoke test cannot multiply live API traffic.
    provider.max_attempts = 1

    record = provider.search_exact_mpn(None, requested_mpn)

    assert record.provider == "digikey"
    assert normalize_mpn(record.mpn) == normalize_mpn(requested_mpn)


@pytest.mark.network
def test_mouser_live_exact_mpn_smoke() -> None:
    if not os.environ.get("MOUSER_API_KEY", "").strip():
        pytest.skip("Mouser live smoke requires MOUSER_API_KEY")

    requested_mpn = "LM321MF/NOPB"
    provider = MouserProvider(timeout=30.0)
    # A single official exact-part request is sufficient for this smoke test.
    provider.max_attempts = 1

    record = provider.search_exact_mpn(None, requested_mpn)

    assert record.provider == "mouser"
    assert normalize_mpn(record.mpn) == normalize_mpn(requested_mpn)
