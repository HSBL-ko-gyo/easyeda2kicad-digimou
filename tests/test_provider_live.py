from __future__ import annotations

# Global imports
import os
from urllib.parse import parse_qsl, urlsplit

import pytest

# Local imports
from easyeda2kicad.cad import DigiKeyCadSource
from easyeda2kicad.metadata.models import (
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CadRequest,
    normalize_manufacturer,
    normalize_mpn,
)
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
def test_digikey_live_ad5314_cad_handoff_smoke() -> None:
    required = ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET")
    if not all(os.environ.get(name, "").strip() for name in required):
        pytest.skip(
            "DigiKey CAD handoff smoke requires DIGIKEY_CLIENT_ID and "
            "DIGIKEY_CLIENT_SECRET"
        )

    requested_manufacturer = "Analog Devices Inc."
    requested_mpn = "AD5314BRM"
    provider = DigiKeyProvider(timeout=30.0)
    # One OAuth transaction, one exact keyword lookup, and one Media request
    # are sufficient. Never multiply live traffic with automatic retries.
    provider.max_attempts = 1

    record = provider.search_exact_mpn(requested_manufacturer, requested_mpn)
    assert normalize_manufacturer(record.manufacturer) == normalize_manufacturer(
        requested_manufacturer
    )
    assert normalize_mpn(record.mpn) == normalize_mpn(requested_mpn)
    assert record.distributor_part_number

    result = DigiKeyCadSource(provider).discover(
        CadRequest(
            manufacturer=requested_manufacturer,
            mpn=requested_mpn,
            source="digikey",
        ),
        exact_record=record,
    )

    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.package is None
    assert result.provenance.distributor == "digikey"
    assert result.provenance.delivery_partner == "ultralibrarian"
    assert result.provenance.model_creator is None
    assert result.action_required is not None
    assert result.action_required.code == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.action_required.setup_url
    assert result.provenance.landing_url == result.action_required.setup_url

    handoff = urlsplit(result.action_required.setup_url)
    assert handoff.scheme == "https"
    assert handoff.username is None
    assert handoff.password is None
    assert handoff.fragment == ""
    assert handoff.hostname in {
        "mm.digikey.com",
        "ultralibrarian.com",
        "app.ultralibrarian.com",
    } or (handoff.hostname or "").endswith(".ultralibrarian.com")
    secret_query_names = {
        "access_token",
        "apikey",
        "api_key",
        "client_secret",
        "key",
        "signature",
        "token",
    }
    assert not secret_query_names.intersection(
        name.casefold() for name, _value in parse_qsl(handoff.query)
    )


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
