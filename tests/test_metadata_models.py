from __future__ import annotations

# Global imports
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

import pytest

from easyeda2kicad_digimou.metadata.models import (
    CadRecord,
    Conflict,
    DistributorRecord,
    MergedPart,
    PartIdentity,
    PriceBreak,
    ProvenanceEntry,
    model_from_dict,
    normalize_manufacturer,
    normalize_mpn,
)


def test_normalize_mpn_preserves_ordering_code_separators_and_positions() -> None:
    assert normalize_mpn(" LM321MF/NOPB ") == "LM321MF/NOPB"
    assert normalize_mpn("AB-12") != normalize_mpn("A-B12")
    assert normalize_mpn("AB-12") != normalize_mpn("AB_12")
    assert normalize_mpn("AB_12") != normalize_mpn("AB/12")


def test_normalize_mpn_nfkc_dash_and_whitespace_only() -> None:
    assert normalize_mpn("  ａｂ‐１２\t rev a ") == "AB-12 REV A"
    assert normalize_mpn(None) == ""


@pytest.mark.parametrize("minus", ["−", "⁻", "₋", "﹣", "－"])
def test_normalize_mpn_maps_presentation_equivalent_minus_in_place(
    minus: str,
) -> None:
    assert normalize_mpn("AB{0}12/CD_E".format(minus)) == "AB-12/CD_E"


@pytest.mark.parametrize("value", [123, True, ["AB-12"], {"mpn": "AB-12"}])
def test_normalize_mpn_never_coerces_non_text_identity(value: object) -> None:
    with pytest.raises(TypeError):
        normalize_mpn(value)  # type: ignore[arg-type]


def test_normalize_manufacturer_is_conservative_and_has_no_aliases() -> None:
    assert normalize_manufacturer(" Texas Instruments, Inc. ") == (
        "TEXASINSTRUMENTSINC"
    )
    assert normalize_manufacturer("Texas-Instruments Inc") == ("TEXASINSTRUMENTSINC")
    assert normalize_manufacturer("TI") != normalize_manufacturer("Texas Instruments")


def test_models_round_trip_nested_data_and_paths() -> None:
    merged = MergedPart(
        identity=PartIdentity(
            manufacturer="Texas Instruments",
            mpn="LM321MF/NOPB",
            package="SOT-23-5",
            lifecycle="Active",
            manufacturer_datasheet_url="https://ti.example/lm321.pdf",
        ),
        distributor_records=[
            DistributorRecord(
                provider="DigiKey",
                distributor_part_number="296-LM321-ND",
                product_url="https://digikey.example/part",
                manufacturer="Texas Instruments",
                mpn="LM321MF/NOPB",
                stock=42,
                minimum_order_quantity=1,
                price_breaks=[PriceBreak(1, 1.25, "USD")],
                raw_response_cache_key="a" * 64,
            )
        ],
        cad=CadRecord(
            source="EasyEDA",
            lcsc_part_number="C131103",
            symbol_path=PureWindowsPath(r"C:\libs\part.kicad_sym"),
            footprint_path=PurePosixPath("/srv/libs/part.kicad_mod"),
            verification_status="VERIFIED",
        ),
        conflicts=[Conflict("package", {"lcsc": "SOT-23", "digikey": "SOT-23-5"})],
        verification_status="VERIFIED",
        provenance={
            "identity.mpn": [ProvenanceEntry("user", "--mpn")],
        },
        provider_errors={"mouser": "AUTH_MISSING"},
    )

    payload = merged.to_dict()
    restored = model_from_dict(MergedPart, payload)

    assert restored == MergedPart.from_dict(payload)
    assert restored.distributor_records[0].price_breaks[0].unit_price == 1.25
    assert payload["cad"]["symbol_path"] == r"C:\libs\part.kicad_sym"
    assert payload["cad"]["footprint_path"] == "/srv/libs/part.kicad_mod"
    assert restored.identity.mpn_normalized == "LM321MF/NOPB"


@pytest.mark.parametrize(
    "payload",
    [
        {"quantity": -1, "unit_price": 1.0},
        {"quantity": 1, "unit_price": float("nan")},
        {"quantity": True, "unit_price": 1.0},
    ],
)
def test_price_break_rejects_non_json_safe_or_negative_values(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        PriceBreak.from_dict(payload)


def test_from_dict_rejects_malformed_nested_collections() -> None:
    with pytest.raises(ValueError, match="price_breaks"):
        DistributorRecord.from_dict({"provider": "mouser", "price_breaks": {}})
    with pytest.raises(ValueError, match="provenance"):
        MergedPart.from_dict(
            {
                "identity": {"mpn": "X"},
                "provenance": {"identity.mpn": {"provider": "user"}},
            }
        )


def test_identity_rejects_inconsistent_cached_normalized_values() -> None:
    with pytest.raises(ValueError, match="mpn_normalized"):
        PartIdentity.from_dict({"mpn": "AB-12", "mpn_normalized": "AB12"})


@pytest.mark.parametrize(
    "field_name",
    ["provider", "distributor_part_number", "manufacturer", "mpn"],
)
@pytest.mark.parametrize("value", [True, 123, ["identity"], {"id": "identity"}, ""])
def test_distributor_record_direct_construction_rejects_non_text_identity(
    field_name: str, value: object
) -> None:
    values: dict[str, object] = {
        "provider": "mouser",
        "distributor_part_number": "123-PART",
        "manufacturer": "Example",
        "mpn": "PART",
    }
    values[field_name] = value

    with pytest.raises(ValueError):
        DistributorRecord(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field_name",
    ["provider", "distributor_part_number", "manufacturer", "mpn"],
)
@pytest.mark.parametrize("value", [True, 123, ["identity"], {"id": "identity"}, ""])
def test_distributor_record_from_dict_rejects_non_text_identity(
    field_name: str, value: object
) -> None:
    values: dict[str, object] = {
        "provider": "mouser",
        "distributor_part_number": "123-PART",
        "manufacturer": "Example",
        "mpn": "PART",
    }
    values[field_name] = value

    with pytest.raises(ValueError):
        DistributorRecord.from_dict(values)


@pytest.mark.parametrize("value", [True, 123, ["C1"], {"id": "C1"}, ""])
def test_cad_record_rejects_non_text_lcsc_identity(value: object) -> None:
    with pytest.raises(ValueError):
        CadRecord(source="easyeda", lcsc_part_number=value)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        CadRecord.from_dict({"source": "easyeda", "lcsc_part_number": value})
