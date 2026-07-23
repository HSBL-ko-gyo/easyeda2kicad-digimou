from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from easyeda2kicad.__main__ import _reconcile_symbol_identity, parse_custom_fields
from easyeda2kicad.kicad.parameters_kicad_symbol import (
    KICAD_SYM_VERSION_20251024,
    KiSymbolInfo,
    escape_kicad_string,
)
from easyeda2kicad.metadata.symbol_fields import CUSTOM_SYMBOL_FIELD_ORDER


def test_parse_custom_fields_last_wins() -> None:
    assert parse_custom_fields(
        ["Manufacturer:Texas Instruments", "Manufacturer:TI", "LCSC ID:C2040"]
    ) == {
        "Manufacturer": "TI",
        "LCSC ID": "C2040",
    }


@pytest.mark.parametrize(
    "value",
    [
        "Manufacturer",
        ":Texas Instruments",
        "   :Texas Instruments",
    ],
)
def test_parse_custom_fields_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_custom_fields([value])


def test_symbol_export_includes_custom_fields() -> None:
    symbol = KiSymbolInfo(
        name="TestPart",
        prefix="U",
        package="Lib:Footprint",
        manufacturer="",
        datasheet="",
        lcsc_id="C2040",
        custom_fields={
            "Manufacturer": "Texas Instruments",
            "Package": "LQFN-56",
        },
    )

    exported = "\n".join(symbol.export())

    assert '"Manufacturer"' in exported
    assert '"Texas Instruments"' in exported
    assert "(id 10)" in exported
    assert '"Package"' in exported
    assert '"LQFN-56"' in exported
    assert "(id 11)" in exported


@pytest.mark.parametrize(
    ("version", "kicad_10"),
    [(None, False), (KICAD_SYM_VERSION_20251024, True)],
)
def test_only_native_metadata_properties_are_hidden_in_supported_syntax(
    version: int | None,
    kicad_10: bool,
) -> None:
    native_fields = ("Manufacturer", "MPN", "LCSC Part", "Datasheet")
    symbol = KiSymbolInfo(
        name="TestPart",
        prefix="U",
        package="",
        manufacturer="Texas Instruments",
        mpn="OPA333AIDBVR",
        datasheet="https://example.invalid/datasheet.pdf",
        lcsc_id="C30878",
        custom_fields={
            key: "metadata-value-{0}".format(index)
            for index, key in enumerate(CUSTOM_SYMBOL_FIELD_ORDER)
        },
    )

    properties = symbol.export() if version is None else symbol.export(version=version)
    for key in native_fields + CUSTOM_SYMBOL_FIELD_ORDER:
        matching = [block for block in properties if '"{0}"'.format(key) in block]
        assert len(matching) == 1, key
        property_block = matching[0]
        if kicad_10:
            assert "(hide yes)" in property_block, key
            assert " hide)" not in property_block, key
        else:
            assert "(hide yes)" not in property_block, key
            assert " hide)" in property_block, key
    exported = "\n".join(properties)
    assert "DigiKey" not in exported
    assert "Mouser" not in exported
    assert "Verification Status" not in exported


def test_kicad_property_strings_are_escaped() -> None:
    assert escape_kicad_string('A\\B "quoted"\r\nnext') == (
        'A\\\\B \\"quoted\\"\\r\\nnext'
    )

    symbol = KiSymbolInfo(
        name="TestPart",
        prefix="U",
        package="",
        manufacturer="",
        datasheet="",
        lcsc_id="",
        custom_fields={'Provider "Note"': "line1\nline2\\tail"},
    )
    exported = "\n".join(symbol.export())
    assert '"Provider \\"Note\\""' in exported
    assert '"line1\\nline2\\\\tail"' in exported


def test_verified_identity_fills_only_empty_native_properties() -> None:
    info = SimpleNamespace(manufacturer="", mpn="", lcsc_id="")

    _reconcile_symbol_identity(
        info,
        {
            "manufacturer": "Texas Instruments",
            "mpn": "OPA333AIDBVR",
            "lcsc_id": "C30878",
        },
    )

    assert vars(info) == {
        "manufacturer": "Texas Instruments",
        "mpn": "OPA333AIDBVR",
        "lcsc_id": "C30878",
    }


def test_verified_manufacturer_alias_preserves_nonempty_cad_property(
    caplog: pytest.LogCaptureFixture,
) -> None:
    info = SimpleNamespace(
        manufacturer="TI(德州仪器)",
        mpn="OPA333AIDBVR",
        lcsc_id="C30878",
    )

    with caplog.at_level(logging.WARNING):
        _reconcile_symbol_identity(
            info,
            {
                "manufacturer": "Texas Instruments",
                "mpn": "OPA333AIDBVR",
                "lcsc_id": "C30878",
            },
        )

    assert info.manufacturer == "TI(德州仪器)"
    assert "preserving the CAD value" in caplog.text


@pytest.mark.parametrize(
    ("field_name", "existing", "verified"),
    (
        ("mpn", "OPA333AIDBVR-T", "OPA333AIDBVR"),
        ("lcsc_id", "C99999", "C30878"),
    ),
)
def test_conflicting_nonempty_part_identity_fails_closed(
    field_name: str,
    existing: str,
    verified: str,
) -> None:
    info = SimpleNamespace(
        manufacturer="Texas Instruments",
        mpn="OPA333AIDBVR",
        lcsc_id="C30878",
    )
    setattr(info, field_name, existing)

    with pytest.raises(ValueError, match=field_name):
        _reconcile_symbol_identity(
            info,
            {
                "manufacturer": "Texas Instruments",
                "mpn": "OPA333AIDBVR",
                "lcsc_id": "C30878",
                field_name: verified,
            },
        )
