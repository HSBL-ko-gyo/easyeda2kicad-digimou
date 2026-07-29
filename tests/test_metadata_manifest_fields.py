from __future__ import annotations

# Global imports
import csv
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from easyeda2kicad_digimou.metadata.manifest import (
    CSV_COLUMNS,
    csv_manifest_rows,
    manifest_to_dict,
    write_csv_manifest,
    write_json_manifest,
)
from easyeda2kicad_digimou.metadata.models import (
    CadRecord,
    Conflict,
    DistributorRecord,
    MergedPart,
    PartIdentity,
    PriceBreak,
    ProvenanceEntry,
)
from easyeda2kicad_digimou.metadata.symbol_fields import (
    CUSTOM_SYMBOL_FIELD_ORDER,
    RESERVED_METADATA_FIELDS,
    build_all_symbol_fields,
    build_symbol_fields,
    select_datasheet,
)


def _merged() -> MergedPart:
    return MergedPart(
        identity=PartIdentity(
            manufacturer="Texas Instruments",
            mpn="OPA333AIDBVR",
            package="SOT-23-5",
            lifecycle="Active",
            manufacturer_datasheet_url="https://ti.example/opa333.pdf",
        ),
        distributor_records=[
            DistributorRecord(
                provider="mouser",
                distributor_part_number="595-OPA333AIDBVR",
                product_url="https://mouser.example/part",
                datasheet_url="https://mouser.example/opa333.pdf",
                manufacturer="Texas Instruments",
                mpn="OPA333AIDBVR",
                stock=77,
                minimum_order_quantity=1,
                packaging="Cut Tape",
                currency="USD",
                price_breaks=[PriceBreak(1, 2.5, "USD")],
                retrieved_at="2026-07-22T12:00:00Z",
            ),
            DistributorRecord(
                provider="digikey",
                distributor_part_number="296-OPA333-ND",
                product_url="https://digikey.example/part",
                datasheet_url="https://digikey.example/opa333.pdf",
                manufacturer="Texas Instruments",
                mpn="OPA333AIDBVR",
                stock=88,
                minimum_order_quantity=1,
                packaging="Tape & Reel",
                currency="USD",
                price_breaks=[PriceBreak(1, 2.25, "USD")],
                retrieved_at="2026-07-22T12:00:00Z",
            ),
            DistributorRecord(
                provider="lcsc",
                distributor_part_number="C30878",
                product_url="https://lcsc.example/C30878",
                datasheet_url="https://lcsc.example/opa333.pdf",
                manufacturer="Texas Instruments",
                mpn="OPA333AIDBVR",
            ),
        ],
        cad=CadRecord(
            source="easyeda",
            lcsc_part_number="C30878",
            symbol_path=PureWindowsPath(r"C:\project\parts.kicad_sym"),
            footprint_path=PurePosixPath("/srv/project/OPA333.kicad_mod"),
            model_3d_path=PureWindowsPath(r"C:\project\OPA333.step"),
            verification_status="VERIFIED",
        ),
        conflicts=[
            Conflict(
                field="package",
                values={"lcsc": "SOT-23", "digikey": "SOT-23-5"},
                selected_value="SOT-23-5",
            )
        ],
        verification_status="VERIFIED",
        provenance={
            "identity.mpn": [ProvenanceEntry("user", "--mpn")],
        },
        provider_errors={"mouser": "RATE_LIMITED"},
    )


def test_json_manifest_is_complete_atomic_and_can_redact_volatile_values(
    tmp_path: Path,
) -> None:
    merged = _merged()
    path = write_json_manifest(
        merged,
        tmp_path / "nested" / "manifest.json",
        include_price=False,
        include_stock=False,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["identity"]["mpn"] == "OPA333AIDBVR"
    assert payload["cad"]["symbol_path"] == r"C:\project\parts.kicad_sym"
    assert payload["distributor_records"][1]["price_breaks"] == []
    assert all(record["stock"] is None for record in payload["distributor_records"])
    assert merged.distributor_records[1].price_breaks  # projection did not mutate input
    assert payload["provider_diagnostics"]["mouser"] == {
        "code": "RATE_LIMITED",
        "operation": None,
        "status": None,
    }
    assert list(path.parent.glob("*.tmp")) == []


def test_csv_has_one_deterministic_row_per_provider_and_compact_json(
    tmp_path: Path,
) -> None:
    path = write_csv_manifest(_merged(), tmp_path / "bom.csv")
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert [row["Provider"] for row in rows] == ["lcsc", "digikey", "mouser"]
    assert rows[0]["LCSC Part"] == "C30878"
    assert rows[1]["DigiKey Part"] == "296-OPA333-ND"
    assert rows[2]["Mouser Part"] == "595-OPA333AIDBVR"
    assert rows[0]["Symbol"] == r"C:\project\parts.kicad_sym"
    assert '": ' not in rows[0]["Conflicts"]
    assert ", " not in rows[0]["Conflicts"]
    assert json.loads(rows[0]["Provenance"])["identity.mpn"][0]["provider"] == ("user")
    assert json.loads(rows[0]["Provider Diagnostics"])["mouser"]["code"] == (
        "RATE_LIMITED"
    )
    assert tuple(rows[0]) == CSV_COLUMNS


def test_csv_redaction_and_stable_row_when_no_distributor_records() -> None:
    merged = _merged()
    rows = csv_manifest_rows(merged, include_price=False, include_stock=False)
    assert all(row["Stock"] == "" for row in rows)
    assert all(row["Currency"] == "" for row in rows)
    assert all(row["Price Breaks"] == "[]" for row in rows)

    empty = MergedPart(identity=PartIdentity(mpn="NO-CAD"))
    empty_rows = csv_manifest_rows(empty)
    assert len(empty_rows) == 1
    assert empty_rows[0]["Provider"] == ""
    assert empty_rows[0]["MPN"] == "NO-CAD"


def test_provider_and_volatile_metadata_are_manifest_only() -> None:
    fields = build_symbol_fields(_merged())
    payload = manifest_to_dict(_merged())

    assert fields == {}
    assert CUSTOM_SYMBOL_FIELD_ORDER == ()
    assert payload["distributor_records"][1]["distributor_part_number"] == (
        "296-OPA333-ND"
    )
    assert payload["distributor_records"][0]["product_url"] == (
        "https://mouser.example/part"
    )
    manifest_only = {
        "DigiKey Part",
        "Mouser Product URL",
        "Package",
        "Lifecycle",
        "CAD Source",
        "Verification Status",
        "Stock",
        "Price",
        "MOQ",
        "Currency",
        "Retrieved At",
        "Raw Response Cache Key",
        "Provider Errors",
    }
    assert manifest_only.isdisjoint(fields)
    assert "Manufacturer" in RESERVED_METADATA_FIELDS
    assert "Datasheet" in RESERVED_METADATA_FIELDS


def test_symbol_projection_stays_empty_despite_status_and_provider_error() -> None:
    merged = _merged()
    baseline_fields = build_symbol_fields(merged)
    merged.verification_status = "PARTIAL"
    merged.provider_errors = {"mouser": "AUTH_MISSING"}

    fields = build_symbol_fields(merged)

    assert merged.cad is not None
    assert merged.cad.verification_status == "VERIFIED"
    assert fields == {}
    assert fields == baseline_fields


def test_all_symbol_fields_put_native_fields_before_custom_fields() -> None:
    fields = build_all_symbol_fields(_merged(), default_datasheet="source-default.pdf")
    assert tuple(fields)[:4] == ("Manufacturer", "MPN", "LCSC Part", "Datasheet")
    assert fields["Datasheet"] == "source-default.pdf"
    assert tuple(fields)[4:] == CUSTOM_SYMBOL_FIELD_ORDER


def test_datasheet_default_is_byte_preserved_when_choice_absent() -> None:
    original = " https://easyeda.example/source.pdf?x=1&y=2 "
    assert select_datasheet(_merged(), choice=None, default=original) is original


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("manufacturer", "https://ti.example/opa333.pdf"),
        ("lcsc", "https://lcsc.example/opa333.pdf"),
        ("digikey", "https://digikey.example/opa333.pdf"),
        ("mouser", "https://mouser.example/opa333.pdf"),
    ],
)
def test_datasheet_explicit_choice_uses_datasheet_not_product_page(
    choice: str, expected: str
) -> None:
    assert select_datasheet(_merged(), choice=choice, default="source.pdf") == expected


def test_datasheet_explicit_missing_value_is_clear_error() -> None:
    merged = _merged()
    merged.distributor_records = [
        record for record in merged.distributor_records if record.provider != "mouser"
    ]
    with pytest.raises(ValueError, match="mouser datasheet is unavailable"):
        select_datasheet(merged, choice="mouser", default="source.pdf")


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "javascript:alert(1)",
        "https:/missing-authority.pdf?apiKey=fake-secret",
    ],
)
def test_explicit_datasheet_rejects_nonpublic_or_malformed_url(
    unsafe_url: str,
) -> None:
    merged = _merged()
    mouser = next(
        record for record in merged.distributor_records if record.provider == "mouser"
    )
    mouser.datasheet_url = unsafe_url

    with pytest.raises(ValueError, match="mouser datasheet is unavailable"):
        select_datasheet(merged, choice="mouser", default="source.pdf")


def test_explicit_datasheet_rejects_distributor_product_page() -> None:
    merged = _merged()
    mouser = next(
        record for record in merged.distributor_records if record.provider == "mouser"
    )
    mouser.datasheet_url = mouser.product_url

    with pytest.raises(ValueError, match="distributor product page"):
        select_datasheet(merged, choice="mouser", default="source.pdf")


def test_explicit_datasheet_rejects_cosmetic_product_url_variant() -> None:
    merged = _merged()
    mouser = next(
        record for record in merged.distributor_records if record.provider == "mouser"
    )
    mouser.product_url = "https://MOUSER.example:443/part/"
    mouser.datasheet_url = "https://mouser.example/part"

    with pytest.raises(ValueError, match="distributor product page"):
        select_datasheet(merged, choice="mouser", default="source.pdf")


def test_explicit_manufacturer_datasheet_requires_public_http_authority() -> None:
    merged = _merged()
    merged.identity.manufacturer_datasheet_url = "javascript:alert(1)"

    with pytest.raises(ValueError, match="manufacturer datasheet is unavailable"):
        select_datasheet(merged, choice="manufacturer", default="source.pdf")


def test_manifest_and_symbol_urls_remove_credentials_but_keep_public_query() -> None:
    merged = _merged()
    digikey = next(
        record for record in merged.distributor_records if record.provider == "digikey"
    )
    digikey.product_url = (
        "https://fake-user:fake-password@digikey.example/part?"
        "q=OPA333&apiKey=fake-secret&lang=en"
    )
    digikey.datasheet_url = "https://digikey.example/data.pdf?token=fake-secret&lang=en"
    merged.identity.manufacturer_datasheet_url = (
        "https://manufacturer.example/data.pdf?clientId=fake-client&lang=en"
    )

    payload = manifest_to_dict(merged)
    fields = build_symbol_fields(merged)
    record = next(
        item for item in payload["distributor_records"] if item["provider"] == "digikey"
    )

    assert record["product_url"] == ("https://digikey.example/part?lang=en&q=OPA333")
    assert record["datasheet_url"] == "https://digikey.example/data.pdf?lang=en"
    assert payload["identity"]["manufacturer_datasheet_url"] == (
        "https://manufacturer.example/data.pdf?lang=en"
    )
    assert fields == {}
    assert "fake-secret" not in json.dumps(payload, sort_keys=True)


def test_csv_neutralizes_formula_cells_while_json_preserves_values() -> None:
    merged = _merged()
    merged.identity.manufacturer = "=FORMULA()"
    merged.distributor_records[0].description = "+FORMULA()"

    rows = csv_manifest_rows(merged)
    payload = manifest_to_dict(merged)
    mouser_row = next(row for row in rows if row["Provider"] == "mouser")

    assert mouser_row["Manufacturer"] == "'=FORMULA()"
    assert mouser_row["Description"] == "'+FORMULA()"
    assert payload["identity"]["manufacturer"] == "=FORMULA()"
    assert payload["distributor_records"][0]["description"] == "+FORMULA()"
