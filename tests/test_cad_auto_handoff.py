from __future__ import annotations

# Global imports
from typing import Any

import pytest

# Local imports
import easyeda2kicad_digimou.__main__ as cli
from easyeda2kicad_digimou.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad_digimou.metadata.merge import PARTIAL
from easyeda2kicad_digimou.metadata import service
from easyeda2kicad_digimou.metadata.models import (
    CAD_AUTH_REQUIRED,
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CadActionRequired,
    CadDiscoveryResult,
    CadProvenance,
    CadRecord,
    CadRequest,
    CadSourceAvailability,
)
from easyeda2kicad_digimou.metadata.service import MetadataResolution

MANUFACTURER = "Synthetic Devices"
MPN = "SYNTH-PART-01"


def _discovery(source: str, status: str) -> CadDiscoveryResult:
    partner = "ultralibrarian" if source == "digikey" else "samacsys"
    return CadDiscoveryResult(
        requested_source=source,
        status=status,
        request=CadRequest(
            manufacturer=MANUFACTURER,
            mpn=MPN,
            source=source,
        ),
        provenance=CadProvenance(
            distributor=source,
            delivery_partner=partner,
            landing_url="https://www.{0}.com/productdetail/example/part".format(source),
            retrieval_mode="official-api-handoff",
        ),
        action_required=CadActionRequired(
            code=status,
            detail="manual handoff only",
            setup_url="https://www.{0}.com/productdetail/example/part".format(source),
        ),
        available_sources=[
            CadSourceAvailability(
                delivery_partner=partner,
                artifact_kinds=["footprint", "model_3d"],
                source_urls=[
                    "https://www.{0}.com/productdetail/example/part".format(source)
                ],
                support_status="manual-handoff",
            )
        ],
        missing_artifacts=["symbol"],
    )


def _discovery_with_artifacts(
    source: str, artifact_kinds: list[str]
) -> CadDiscoveryResult:
    discovery = _discovery(source, CAD_MANUAL_DOWNLOAD_REQUIRED)
    discovery.available_sources[0].artifact_kinds = sorted(artifact_kinds)
    discovery.missing_artifacts = sorted(
        {"symbol", "footprint", "model_3d"}.difference(artifact_kinds)
    )
    return discovery


def _unused_factory(*_args: Any, **_kwargs: Any) -> Any:
    pytest.fail("provider factory must not be used by patched discovery")


def test_auto_handoff_preserves_priority_but_never_marks_landing_as_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "_discover_digikey_cad",
        lambda *_args, **_kwargs: _discovery("digikey", CAD_MANUAL_DOWNLOAD_REQUIRED),
    )
    monkeypatch.setattr(
        service,
        "_discover_mouser_cad",
        lambda *_args, **_kwargs: pytest.fail(
            "DigiKey manual handoff has deterministic priority"
        ),
    )

    result = service._discover_auto_cad_handoff(
        MetadataResolution(
            trusted_manufacturer=MANUFACTURER,
            trusted_mpn=MPN,
        ),
        ("digikey", "mouser"),
        {},
        {},
        provider_factory=_unused_factory,
        metadata_api=EasyedaApi(use_cache=False),
        offline=False,
    )

    assert result is not None
    assert result.requested_source == "auto"
    assert result.request is not None
    assert result.request.source == "auto"
    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.package is None
    assert result.provenance.distributor == "digikey"
    assert result.provenance.delivery_partner == "ultralibrarian"
    assert result.available_sources[0].delivery_partner == "ultralibrarian"
    assert result.missing_artifacts == ["symbol"]
    assert result.action_required is not None
    assert "No acquired, identity-verified" in result.action_required.detail


def test_auto_handoff_continues_past_auth_gap_to_actionable_mouser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "_discover_digikey_cad",
        lambda *_args, **_kwargs: _discovery("digikey", CAD_AUTH_REQUIRED),
    )
    monkeypatch.setattr(
        service,
        "_discover_mouser_cad",
        lambda *_args, **_kwargs: _discovery("mouser", CAD_MANUAL_DOWNLOAD_REQUIRED),
    )

    result = service._discover_auto_cad_handoff(
        MetadataResolution(
            trusted_manufacturer=MANUFACTURER,
            trusted_mpn=MPN,
        ),
        ("digikey", "mouser"),
        {},
        {},
        provider_factory=_unused_factory,
        metadata_api=EasyedaApi(use_cache=False),
        offline=False,
    )

    assert result is not None
    assert result.requested_source == "auto"
    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.package is None
    assert result.provenance.distributor == "mouser"
    assert result.provenance.delivery_partner == "samacsys"


def test_auto_handoff_does_not_query_unrequested_external_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "_discover_digikey_cad",
        lambda *_args, **_kwargs: pytest.fail("DigiKey was not requested"),
    )
    monkeypatch.setattr(
        service,
        "_discover_mouser_cad",
        lambda *_args, **_kwargs: pytest.fail("Mouser was not requested"),
    )

    assert (
        service._discover_auto_cad_handoff(
            MetadataResolution(
                trusted_manufacturer=MANUFACTURER,
                trusted_mpn=MPN,
            ),
            ("lcsc",),
            {},
            {},
            provider_factory=_unused_factory,
            metadata_api=EasyedaApi(use_cache=False),
            offline=False,
        )
        is None
    )


def test_missing_footprint_skips_source_that_only_advertises_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "_discover_digikey_cad",
        lambda *_args, **_kwargs: _discovery_with_artifacts("digikey", ["symbol"]),
    )
    monkeypatch.setattr(
        service,
        "_discover_mouser_cad",
        lambda *_args, **_kwargs: _discovery_with_artifacts(
            "mouser", ["footprint", "model_3d"]
        ),
    )

    result = service.discover_auto_cad_fallback(
        MetadataResolution(
            trusted_manufacturer=MANUFACTURER,
            trusted_mpn=MPN,
        ),
        ("digikey", "mouser"),
        ("footprint",),
        provider_factory=_unused_factory,
        metadata_api=EasyedaApi(use_cache=False),
        offline=False,
    )

    assert result is not None
    assert result.provenance.distributor == "mouser"
    assert result.action_required is not None
    assert "EasyEDA" in result.action_required.detail
    assert "footprint" in result.action_required.detail


def test_cli_auto_discovers_provider_when_easyeda_footprint_is_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolution = MetadataResolution(
        trusted_manufacturer=MANUFACTURER,
        trusted_mpn=MPN,
        cad=CadRecord(
            source="easyeda",
            symbol_name="SYNTH_SYMBOL",
            verification_status=PARTIAL,
        ),
        cad_data={"synthetic": True},
    )
    monkeypatch.setattr(cli, "resolve_metadata", lambda **_kwargs: resolution)
    symbol = object()
    monkeypatch.setattr(
        cli,
        "_verify_metadata_cad",
        lambda *_args, **_kwargs: (PARTIAL, symbol, None),
    )
    seen: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def discover(
        *_args: Any,
        **_kwargs: Any,
    ) -> CadDiscoveryResult:
        seen.append((tuple(_args[1]), tuple(_args[2])))
        return _discovery("digikey", CAD_MANUAL_DOWNLOAD_REQUIRED)

    monkeypatch.setattr(cli, "discover_auto_cad_fallback", discover)

    resolved = cli._resolve_metadata_request(
        {
            "use_cache": False,
            "offline": False,
            "mpn": MPN,
            "manufacturer": MANUFACTURER,
            "lcsc_id": [],
            "provider_names": ["lcsc"],
            "cad_source": "auto",
            "refresh_metadata": False,
            "symbol": True,
            "footprint": True,
            "3d": False,
        }
    )

    assert resolved is not None
    assert resolved[3] is symbol
    assert resolved[4] is None
    assert seen == [(("lcsc", "digikey", "mouser"), ("footprint",))]
    assert resolution.cad_discovery is not None
    assert resolution.cad_discovery.requested_source == "digikey"
    assert resolution.blocking_error == CAD_MANUAL_DOWNLOAD_REQUIRED


def test_cli_does_not_fallback_for_unrequested_footprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolution = MetadataResolution(
        trusted_manufacturer=MANUFACTURER,
        trusted_mpn=MPN,
        cad=CadRecord(
            source="easyeda",
            symbol_name="SYNTH_SYMBOL",
            verification_status=PARTIAL,
        ),
        cad_data={"synthetic": True},
    )
    monkeypatch.setattr(cli, "resolve_metadata", lambda **_kwargs: resolution)
    symbol = object()
    monkeypatch.setattr(
        cli,
        "_verify_metadata_cad",
        lambda *_args, **_kwargs: (PARTIAL, symbol, None),
    )
    monkeypatch.setattr(
        cli,
        "discover_auto_cad_fallback",
        lambda *_args, **_kwargs: pytest.fail(
            "an unrequested footprint must not trigger external discovery"
        ),
    )

    resolved = cli._resolve_metadata_request(
        {
            "use_cache": False,
            "offline": False,
            "mpn": MPN,
            "manufacturer": MANUFACTURER,
            "lcsc_id": [],
            "provider_names": ["digikey", "mouser"],
            "cad_source": "auto",
            "refresh_metadata": False,
            "symbol": True,
            "footprint": False,
            "3d": False,
        }
    )

    assert resolved is not None
    assert resolved[3] is symbol
    assert resolution.cad_discovery is None
