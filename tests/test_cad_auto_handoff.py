from __future__ import annotations

# Global imports
from types import SimpleNamespace
from typing import Any

import pytest

# Local imports
import easyeda2kicad_digimou.__main__ as cli
from easyeda2kicad_digimou.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad_digimou.metadata.merge import (
    CAD_NOT_FOUND,
    CAD_PIN_PAD_MISMATCH,
    PARTIAL,
)
from easyeda2kicad_digimou.metadata import service
from easyeda2kicad_digimou.metadata.models import (
    CAD_AUTH_REQUIRED,
    CAD_DOWNLOAD_UNAVAILABLE,
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
    partner = "ultralibrarian" if source == "digikey" else "snapmagic"
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


def _symbol_with_pins(*numbers: str) -> SimpleNamespace:
    return SimpleNamespace(
        pins=[
            SimpleNamespace(
                settings=SimpleNamespace(spice_pin_number=number),
            )
            for number in numbers
        ],
        sub_symbols=[],
    )


def _footprint_with_pads(*numbers: str) -> SimpleNamespace:
    return SimpleNamespace(
        pads=[
            SimpleNamespace(
                number=number,
                hole_radius=0.0,
                is_plated=True,
            )
            for number in numbers
        ]
    )


def _patch_artifact_importers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    symbol: SimpleNamespace,
    footprint: SimpleNamespace,
) -> None:
    monkeypatch.setattr(
        cli,
        "EasyedaSymbolImporter",
        lambda **_kwargs: SimpleNamespace(get_symbol=lambda: symbol),
    )
    monkeypatch.setattr(
        cli,
        "EasyedaFootprintImporter",
        lambda **_kwargs: SimpleNamespace(get_footprint=lambda: footprint),
    )


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
    assert result.provenance.delivery_partner == "snapmagic"


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
    assert result.available_sources[0].artifact_kinds == ["footprint"]
    assert result.missing_artifacts == []


def test_required_artifacts_must_exist_in_one_provider_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digikey = _discovery_with_artifacts("digikey", ["symbol"])
    digikey.available_sources.append(
        CadSourceAvailability(
            delivery_partner="ultralibrarian",
            artifact_kinds=["footprint"],
            source_urls=["https://www.digikey.com/en/models/example"],
            support_status="manual-handoff",
        )
    )
    monkeypatch.setattr(
        service,
        "_discover_digikey_cad",
        lambda *_args, **_kwargs: digikey,
    )
    monkeypatch.setattr(
        service,
        "_discover_mouser_cad",
        lambda *_args, **_kwargs: _discovery_with_artifacts("mouser", ["symbol"]),
    )

    result = service.discover_auto_cad_fallback(
        MetadataResolution(
            trusted_manufacturer=MANUFACTURER,
            trusted_mpn=MPN,
        ),
        ("digikey", "mouser"),
        ("symbol", "footprint"),
        provider_factory=_unused_factory,
        metadata_api=EasyedaApi(use_cache=False),
        offline=False,
    )

    assert result is not None
    assert result.status == CAD_DOWNLOAD_UNAVAILABLE
    assert result.provenance.distributor is None
    assert result.available_sources == []
    assert result.missing_artifacts == ["footprint", "symbol"]


def test_irrelevant_manual_handoffs_are_not_returned(
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
        lambda *_args, **_kwargs: _discovery_with_artifacts("mouser", ["model_3d"]),
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
    assert result.status == CAD_DOWNLOAD_UNAVAILABLE
    assert result.available_sources == []
    assert result.missing_artifacts == ["footprint"]
    assert result.action_required is not None
    assert result.action_required.setup_url is None


def test_auth_gap_is_preserved_when_no_visible_source_offers_required_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digikey_auth = _discovery("digikey", CAD_AUTH_REQUIRED)
    digikey_auth.available_sources = []
    digikey_auth.missing_artifacts = ["footprint", "model_3d", "symbol"]
    monkeypatch.setattr(
        service,
        "_discover_digikey_cad",
        lambda *_args, **_kwargs: digikey_auth,
    )
    monkeypatch.setattr(
        service,
        "_discover_mouser_cad",
        lambda *_args, **_kwargs: _discovery_with_artifacts("mouser", ["symbol"]),
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
    assert result.status == CAD_AUTH_REQUIRED
    assert result.provenance.distributor == "digikey"
    assert result.available_sources == []
    assert result.missing_artifacts == ["footprint"]


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
    service_flags: list[bool] = []

    def resolve(**kwargs: Any) -> MetadataResolution:
        service_flags.append(kwargs["discover_auto_handoff"])
        return resolution

    monkeypatch.setattr(cli, "resolve_metadata", resolve)
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
    assert service_flags == [False]
    assert seen == [(("lcsc", "digikey", "mouser"), ("footprint",))]
    assert resolution.cad_discovery is not None
    assert resolution.cad_discovery.requested_source == "digikey"
    assert resolution.blocking_error == CAD_MANUAL_DOWNLOAD_REQUIRED


def test_cli_total_easyeda_miss_expands_beyond_metadata_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolution = MetadataResolution(
        trusted_manufacturer=MANUFACTURER,
        trusted_mpn=MPN,
    )
    service_flags: list[bool] = []

    def resolve(**kwargs: Any) -> MetadataResolution:
        service_flags.append(kwargs["discover_auto_handoff"])
        return resolution

    monkeypatch.setattr(cli, "resolve_metadata", resolve)
    monkeypatch.setattr(
        cli,
        "_verify_metadata_cad",
        lambda *_args, **_kwargs: (CAD_NOT_FOUND, None, None),
    )
    seen: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def discover(*args: Any, **_kwargs: Any) -> CadDiscoveryResult:
        seen.append((tuple(args[1]), tuple(args[2])))
        return _discovery("mouser", CAD_MANUAL_DOWNLOAD_REQUIRED)

    monkeypatch.setattr(cli, "discover_auto_cad_fallback", discover)

    resolved = cli._resolve_metadata_request(
        {
            "use_cache": False,
            "offline": False,
            "mpn": MPN,
            "manufacturer": MANUFACTURER,
            "lcsc_id": [],
            "provider_names": ["digikey"],
            "cad_source": "auto",
            "refresh_metadata": False,
            "symbol": True,
            "footprint": True,
            "3d": True,
        }
    )

    assert resolved is not None
    assert service_flags == [False]
    assert seen == [(("digikey", "mouser"), ("symbol", "footprint", "model_3d"))]


@pytest.mark.parametrize(
    ("arguments", "status", "symbol", "footprint", "expected"),
    [
        (
            {"symbol": True, "footprint": False, "3d": False},
            PARTIAL,
            None,
            object(),
            ("symbol",),
        ),
        (
            {"symbol": False, "footprint": False, "3d": True},
            PARTIAL,
            object(),
            object(),
            ("model_3d",),
        ),
        (
            {"symbol": True, "footprint": True, "3d": False},
            CAD_PIN_PAD_MISMATCH,
            object(),
            object(),
            ("symbol", "footprint"),
        ),
    ],
)
def test_missing_requested_artifact_matrix(
    arguments: dict[str, bool],
    status: str,
    symbol: object | None,
    footprint: object | None,
    expected: tuple[str, ...],
) -> None:
    assert (
        cli._missing_requested_easyeda_artifacts(
            arguments,
            MetadataResolution(
                cad=CadRecord(source="easyeda", verification_status=status),
            ),
            status,
            symbol,
            footprint,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("require_symbol", "require_footprint", "symbol", "footprint", "expected"),
    [
        (True, False, _symbol_with_pins(), _footprint_with_pads("1"), ("symbol",)),
        (
            False,
            True,
            _symbol_with_pins("1"),
            _footprint_with_pads(),
            ("footprint",),
        ),
        (
            True,
            True,
            _symbol_with_pins(),
            _footprint_with_pads("1"),
            ("symbol",),
        ),
        (
            True,
            True,
            _symbol_with_pins("1"),
            _footprint_with_pads(),
            ("footprint",),
        ),
    ],
)
def test_parsed_empty_artifact_is_invalid_and_missing(
    monkeypatch: pytest.MonkeyPatch,
    require_symbol: bool,
    require_footprint: bool,
    symbol: SimpleNamespace,
    footprint: SimpleNamespace,
    expected: tuple[str, ...],
) -> None:
    _patch_artifact_importers(
        monkeypatch,
        symbol=symbol,
        footprint=footprint,
    )
    resolution = MetadataResolution(
        cad=CadRecord(source="easyeda"),
        cad_data={"synthetic": True},
    )

    status, parsed_symbol, parsed_footprint = cli._verify_metadata_cad(
        resolution,
        require_symbol=require_symbol,
        require_footprint=require_footprint,
    )
    missing = cli._missing_requested_easyeda_artifacts(
        {
            "symbol": require_symbol,
            "footprint": require_footprint,
            "3d": False,
        },
        resolution,
        status,
        parsed_symbol,
        parsed_footprint,
    )

    assert status == PARTIAL
    assert resolution.blocking_error == "INVALID_RESPONSE"
    assert missing == expected


def test_parsed_empty_artifact_with_no_external_match_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolution = MetadataResolution(
        trusted_manufacturer=MANUFACTURER,
        trusted_mpn=MPN,
        cad=CadRecord(source="easyeda"),
        cad_data={"synthetic": True},
    )
    monkeypatch.setattr(cli, "resolve_metadata", lambda **_kwargs: resolution)
    _patch_artifact_importers(
        monkeypatch,
        symbol=_symbol_with_pins(),
        footprint=_footprint_with_pads("1"),
    )
    seen: list[tuple[str, ...]] = []

    def discover(*args: Any, **_kwargs: Any) -> CadDiscoveryResult:
        seen.append(tuple(args[2]))
        return CadDiscoveryResult(
            requested_source="auto",
            status=CAD_DOWNLOAD_UNAVAILABLE,
            provenance=CadProvenance(),
            missing_artifacts=["symbol"],
        )

    monkeypatch.setattr(cli, "discover_auto_cad_fallback", discover)

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
            "footprint": True,
            "3d": False,
        }
    )

    assert resolved is not None
    assert seen == [("symbol",)]
    assert resolution.cad_discovery is not None
    assert resolution.cad_discovery.status == CAD_DOWNLOAD_UNAVAILABLE
    assert resolution.blocking_error == CAD_DOWNLOAD_UNAVAILABLE


def test_evidence_free_mouser_handoff_never_infers_samacsys() -> None:
    result = service._external_cad_not_acquired(
        "mouser",
        MANUFACTURER,
        MPN,
    )

    assert result.provenance.distributor == "mouser"
    assert result.provenance.delivery_partner is None
    assert result.provenance.model_creator is None
    assert result.action_required is not None
    assert "Mouser-linked official" in result.action_required.detail
    assert "samacsys" not in result.action_required.detail.casefold()


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
