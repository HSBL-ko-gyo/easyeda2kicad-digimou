from __future__ import annotations

import pytest

from easyeda2kicad.metadata.merge import (
    CAD_NOT_FOUND,
    PARTIAL,
    VERIFIED,
    IdentityMismatchError,
    merge_metadata,
    merge_records,
)
from easyeda2kicad.metadata.models import CadRecord, DistributorRecord


def _record(provider: str, **values: object) -> DistributorRecord:
    defaults: dict[str, object] = {
        "provider": provider,
        "manufacturer": "Texas Instruments",
        "mpn": "OPA333AIDBVR",
        "distributor_part_number": provider + "-part",
    }
    defaults.update(values)
    return DistributorRecord.from_dict(defaults)


def test_merge_is_deterministic_with_conflicts_and_provenance() -> None:
    records = [
        _record(
            "mouser",
            package="SOT-23-5",
            lifecycle="Active",
            datasheet_url="https://ti.example/opa333.pdf",
        ),
        _record(
            "lcsc",
            package="SOT-23",
            lifecycle="Active",
            datasheet_url="https://lcsc.example/opa333.pdf",
        ),
        _record(
            "digikey",
            package="SOT-23-5",
            lifecycle="Not Recommended for New Designs",
            datasheet_url="https://ti.example/opa333.pdf",
        ),
    ]
    cad = CadRecord(source="easyeda", verification_status="VERIFIED")

    merged = merge_records(records, mpn="OPA333AIDBVR", cad=cad)

    assert [record.provider for record in merged.distributor_records] == [
        "lcsc",
        "digikey",
        "mouser",
    ]
    assert merged.identity.package == "SOT-23"
    assert merged.identity.lifecycle == "Active"
    assert merged.identity.manufacturer_datasheet_url == (
        "https://lcsc.example/opa333.pdf"
    )
    assert [conflict.field for conflict in merged.conflicts] == [
        "lifecycle",
        "manufacturer_datasheet_url",
        "package",
    ]
    assert merged.provenance["identity.mpn"][0].provider == "user"
    assert merged.provenance["identity.package"][0].provider == "lcsc"
    assert merged.verification_status == VERIFIED
    assert (
        merged.to_dict()
        == merge_records(list(reversed(records)), mpn="OPA333AIDBVR", cad=cad).to_dict()
    )


def test_merge_rejects_false_distributor_match_as_partial_result() -> None:
    records = [
        _record("digikey", mpn="OPA333AIDBVR"),
        _record("mouser", mpn="OPA333AIDBVT"),
    ]

    merged = merge_records(
        records,
        mpn="OPA333AIDBVR",
        cad=CadRecord(source="easyeda", verification_status="VERIFIED"),
    )

    assert [record.provider for record in merged.distributor_records] == ["digikey"]
    assert merged.provider_errors["mouser"].startswith("NOT_FOUND")
    assert merged.verification_status == PARTIAL


def test_merge_lcsc_mismatch_is_fatal() -> None:
    with pytest.raises(IdentityMismatchError) as error:
        merge_records(
            [_record("lcsc", mpn="OPA333AIDBVT")],
            mpn="OPA333AIDBVR",
        )
    assert error.value.category == "MPN_MISMATCH"


def test_merge_does_not_conflate_separator_positions() -> None:
    merged = merge_records(
        [_record("digikey", mpn="A-B12")],
        mpn="AB-12",
    )
    assert merged.distributor_records == []
    assert merged.provider_errors["digikey"].startswith("NOT_FOUND")


def test_merge_preserves_slash_suffix_and_accepts_unicode_dash_variant() -> None:
    record = _record("lcsc", mpn="LM321MF/NOPB")
    record.manufacturer = "Texas Instruments"
    merged = merge_metadata(
        [record],
        requested_mpn="LM321MF/NOPB",
        requested_manufacturer="Texas-Instruments",
    )
    assert merged.identity.mpn == "LM321MF/NOPB"
    assert merged.identity.mpn_normalized == "LM321MF/NOPB"
    assert merged.distributor_records == [record]


def test_distributor_product_page_is_not_manufacturer_datasheet() -> None:
    record = _record(
        "digikey",
        product_url="https://digikey.example/products/OPA333",
        datasheet_url="https://digikey.example/products/OPA333",
    )
    merged = merge_records([record], mpn="OPA333AIDBVR")
    assert merged.identity.manufacturer_datasheet_url is None
    assert merged.distributor_records[0].datasheet_url == record.datasheet_url


def test_manufacturer_host_datasheet_is_preferred_over_lcsc_mirror() -> None:
    records = [
        _record(
            "lcsc",
            datasheet_url="https://datasheet.lcsc.com/szlcsc/OPA333.pdf",
        ),
        _record(
            "digikey",
            datasheet_url="https://www.ti.com/lit/ds/symlink/opa333.pdf",
        ),
    ]

    merged = merge_records(records, mpn="OPA333AIDBVR")

    assert merged.identity.manufacturer_datasheet_url == (
        "https://www.ti.com/lit/ds/symlink/opa333.pdf"
    )
    assert [
        (entry.provider, entry.source_field)
        for entry in merged.provenance["identity.manufacturer_datasheet_url"]
    ] == [("digikey", "datasheet_url")]
    conflict = next(
        item for item in merged.conflicts if item.field == "manufacturer_datasheet_url"
    )
    assert conflict.selected_value == "https://www.ti.com/lit/ds/symlink/opa333.pdf"


def test_all_distributor_mirror_datasheets_keep_provider_priority() -> None:
    records = [
        _record(
            "mouser",
            datasheet_url="https://www.mouser.com/datasheet/opa333.pdf",
        ),
        _record(
            "digikey",
            datasheet_url="https://media.digikey.com/pdf/opa333.pdf",
        ),
        _record(
            "lcsc",
            datasheet_url="https://datasheet.lcsc.com/szlcsc/opa333.pdf",
        ),
    ]

    merged = merge_records(records, mpn="OPA333AIDBVR")

    assert merged.identity.manufacturer_datasheet_url == (
        "https://datasheet.lcsc.com/szlcsc/opa333.pdf"
    )


def test_metadata_without_cad_is_successful_cad_not_found_state() -> None:
    merged = merge_records([_record("digikey")], mpn="OPA333AIDBVR")
    assert merged.verification_status == CAD_NOT_FOUND


def test_untrusted_manufacturer_disagreement_is_retained_as_conflict() -> None:
    records = [
        _record("digikey", manufacturer="Acme Devices"),
        _record("mouser", manufacturer="Other Devices"),
    ]

    merged = merge_records(records, mpn="OPA333AIDBVR")

    assert len(merged.distributor_records) == 2
    conflict = next(item for item in merged.conflicts if item.field == "manufacturer")
    assert conflict.values == {
        "digikey": "Acme Devices",
        "mouser": "Other Devices",
    }


def test_inferred_manufacturer_seed_is_consistent_with_one_external_record() -> None:
    merged = merge_records(
        [_record("digikey", manufacturer="Texas Instruments")],
        mpn="OPA333AIDBVR",
        manufacturer_seed="TI(德州仪器)",
        manufacturer_seed_source="easyeda",
    )

    assert merged.identity.manufacturer == "TI(德州仪器)"
    assert merged.identity.manufacturer_normalized == "TI德州仪器"
    assert merged.provenance["identity.manufacturer"][0].provider == "easyeda"
    assert merged.provenance["identity.manufacturer"][0].source_field == (
        "dataStr.head.c_para.Manufacturer"
    )
    assert (
        merged.provenance["identity.manufacturer_normalized"][0].provider == "easyeda"
    )
    conflict = next(item for item in merged.conflicts if item.field == "manufacturer")
    assert conflict.values == {
        "easyeda": "TI(德州仪器)",
        "digikey": "Texas Instruments",
    }
    assert conflict.selected_value == merged.identity.manufacturer
    assert conflict.reason == "inferred manufacturer display names disagree"


def test_explicit_invalid_verification_status_is_rejected() -> None:
    with pytest.raises(ValueError, match="verification status"):
        merge_records(
            [_record("digikey")],
            mpn="OPA333AIDBVR",
            verification_status="MAYBE",
        )
