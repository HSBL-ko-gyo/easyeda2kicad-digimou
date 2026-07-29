from __future__ import annotations

from typing import Any

import pytest

from easyeda2kicad_digimou.metadata.cad_identity import (
    CadIdentityConflictError,
    CadIdentityError,
    CadIdentityMismatchError,
    CadIdentityMissingError,
    extract_cad_identity,
)


def payload(
    *,
    lcsc: str = "C30878",
    symbol_mpn: str | None = "OPA333AIDBVR",
    package_mpn: str | None = "OPA333AIDBVR",
) -> dict[str, Any]:
    symbol = {
        "Manufacturer": "TI(德州仪器)",
        "Supplier Part": lcsc,
    }
    package = {"BOM_Manufacturer": "TI(德州仪器)"}
    if symbol_mpn is not None:
        symbol["Manufacturer Part"] = symbol_mpn
    if package_mpn is not None:
        package["BOM_Manufacturer Part"] = package_mpn
    return {
        "uuid": "easyeda-component-1",
        "title": "UNTRUSTED_SEARCH_TITLE",
        "lcsc": {"number": lcsc},
        "dataStr": {"head": {"c_para": symbol}},
        "packageDetail": {"dataStr": {"head": {"c_para": package}}},
    }


def test_extracts_agreeing_payload_identity() -> None:
    result = extract_cad_identity(
        payload(), requested_lcsc_id="C30878", requested_mpn="opa333aidbvr"
    )

    assert result.lcsc_id == "C30878"
    assert result.mpn == "OPA333AIDBVR"
    assert result.manufacturer == "TI(德州仪器)"
    assert result.easyeda_component_id == "easyeda-component-1"


def test_rejects_requested_lcsc_mismatch() -> None:
    with pytest.raises(CadIdentityMismatchError) as exc_info:
        extract_cad_identity(payload(), requested_lcsc_id="C131103")

    assert exc_info.value.field_name == "lcsc_id"


def test_rejects_symbol_package_mpn_disagreement() -> None:
    with pytest.raises(CadIdentityConflictError):
        extract_cad_identity(payload(package_mpn="OPA333AIDBVR-T"))


def test_accepts_bom_fallback_without_primary_mpn() -> None:
    result = extract_cad_identity(payload(symbol_mpn=None))

    assert result.mpn == "OPA333AIDBVR"


def test_missing_mpn_never_falls_back_to_title() -> None:
    with pytest.raises(CadIdentityMissingError):
        extract_cad_identity(
            payload(symbol_mpn=None, package_mpn=None),
            requested_mpn="UNTRUSTED_SEARCH_TITLE",
        )


def test_preserves_ordering_code_separators() -> None:
    lm321 = payload(
        lcsc="C131103",
        symbol_mpn="LM321MF/NOPB",
        package_mpn="LM321MF/NOPB",
    )

    assert extract_cad_identity(lm321, requested_mpn="lm321mf/nopb").mpn == (
        "LM321MF/NOPB"
    )
    with pytest.raises(CadIdentityMismatchError):
        extract_cad_identity(lm321, requested_mpn="LM321MF-NOPB")


def test_rejects_different_separator_positions() -> None:
    value = payload(symbol_mpn="AB-12", package_mpn="AB-12")

    with pytest.raises(CadIdentityMismatchError):
        extract_cad_identity(value, requested_mpn="A-B12")


def test_subpart_identity_participates_in_reconciliation() -> None:
    value = payload()
    value["subparts"] = [
        {"dataStr": {"head": {"c_para": {"Manufacturer Part": "OPA333AIDBVR-X"}}}}
    ]

    with pytest.raises(CadIdentityConflictError):
        extract_cad_identity(value)


@pytest.mark.parametrize("malformed", [{"bad": 1}, ["OPA333AIDBVR"], True])
def test_rejects_container_or_boolean_identity_evidence(malformed: object) -> None:
    value = payload()
    value["dataStr"]["head"]["c_para"]["Manufacturer Part"] = malformed

    with pytest.raises(CadIdentityError):
        extract_cad_identity(value)
