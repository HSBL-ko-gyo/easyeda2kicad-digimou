from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import pytest

from easyeda2kicad_digimou import __main__ as cli
from easyeda2kicad_digimou.cad.digikey import DigiKeyCadSource
from easyeda2kicad_digimou.cad.errors import CadPackageError
from easyeda2kicad_digimou.cad.package import ingest_cad_package
from easyeda2kicad_digimou.cad.selection import (
    CadPackageCandidate,
    select_auto_cad_package,
)
from easyeda2kicad_digimou.metadata.models import (
    CAD_DOWNLOAD_UNAVAILABLE,
    CAD_MANUAL_DOWNLOAD_REQUIRED,
    CAD_PARTIAL,
    SYMBOL_UNAVAILABLE,
    CadDiscoveryResult,
    CadRequest,
    DistributorRecord,
)
from easyeda2kicad_digimou.providers import NotFoundError

FIXTURE = Path(__file__).parent / "fixtures" / "cad_packages" / "manufacturer-kicad-v1"
MANUFACTURER = "Same Sky (Formerly CUI Devices)"
MPN = "MJ-2523-SMT-TR"
PRODUCT_URL = (
    "https://www.digikey.com/en/products/detail/"
    "same-sky-formerly-cui-devices/MJ-2523-SMT-TR/281299"
)
MODEL_URL = "https://www.digikey.com/en/models/281299"
FOOTPRINT_URL = (
    "https://www.cuidevices.com/product/resource/digikeypcbfootprint/mj-2523-smt-tr"
)
MODEL_3D_URL = (
    "https://www.cuidevices.com/product/resource/digikey3dmodel/mj-2523-smt-tr"
)
OTHER_MANUFACTURER = "Northstar Components Inc."
OTHER_MPN = "NSC-42"
OTHER_PRODUCT_URL = (
    "https://www.digikey.com/en/products/detail/northstar-components/NSC-42/999001"
)
OTHER_MODEL_URL = "https://www.digikey.com/en/models/999001"
OTHER_FOOTPRINT_URL = "https://cad.northstar.com/parts/NSC-42-footprint"
OTHER_MODEL_3D_URL = "https://cad.northstar.com/parts/NSC-42.step"


def _record() -> DistributorRecord:
    return DistributorRecord(
        provider="digikey",
        distributor_part_number="CP-2523MJCT-ND",
        product_url=PRODUCT_URL,
        manufacturer=MANUFACTURER,
        mpn=MPN,
    )


class _Api:
    name = "digikey"

    def __init__(
        self,
        response: Mapping[str, Any],
        *,
        page_html: Optional[str] = None,
        record: Optional[DistributorRecord] = None,
    ) -> None:
        self.response = response
        self.page_html = page_html
        self.record = record or _record()

    def search_exact_mpn(
        self, manufacturer: Optional[str], mpn: str
    ) -> DistributorRecord:
        if manufacturer != self.record.manufacturer or mpn != self.record.mpn:
            raise NotFoundError("digikey", operation="exact-match")
        return self.record

    def validate_exact_match(
        self,
        candidates: Sequence[DistributorRecord],
        manufacturer: Optional[str],
        mpn: str,
    ) -> DistributorRecord:
        if (
            len(candidates) != 1
            or candidates[0].manufacturer != manufacturer
            or candidates[0].mpn != mpn
        ):
            raise NotFoundError("digikey", operation="exact-match")
        return candidates[0]

    def get_product_media(self, product_number: str) -> Mapping[str, Any]:
        assert product_number == self.record.distributor_part_number
        return self.response

    def get_public_model_page(self, model_page_url: str) -> Optional[str]:
        product_url = self.record.product_url
        assert product_url is not None
        assert model_page_url == (
            "https://www.digikey.com/en/models/"
            + product_url.rstrip("/").rsplit("/", 1)[-1]
        )
        return self.page_html


def _discover(
    *links: Mapping[str, str],
    record: Optional[DistributorRecord] = None,
) -> CadDiscoveryResult:
    selected_record = record or _record()
    manufacturer = selected_record.manufacturer
    mpn = selected_record.mpn
    assert manufacturer is not None
    assert mpn is not None
    return DigiKeyCadSource(
        _Api({"MediaLinks": list(links)}, record=selected_record)
    ).discover(
        CadRequest(
            manufacturer=manufacturer,
            mpn=mpn,
            source="digikey",
        ),
        exact_record=selected_record,
    )


def test_manufacturer_footprint_and_3d_are_not_misidentified_as_ultralibrarian() -> (
    None
):
    result = _discover(
        {
            "MediaType": "Model",
            "Title": "MJ-2523-SMT-TR - PCB Footprint",
            "Url": FOOTPRINT_URL,
        },
        {
            "MediaType": "Model",
            "Title": "MJ-2523-SMT-TR - 3D Model",
            "Url": MODEL_3D_URL,
        },
    )

    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.provenance.distributor == "digikey"
    assert result.provenance.delivery_partner == MANUFACTURER.casefold()
    assert result.provenance.model_creator == MANUFACTURER.casefold()
    assert result.provenance.landing_url == MODEL_URL
    assert result.missing_artifacts == ["symbol"]
    assert len(result.available_sources) == 1
    source = result.available_sources[0]
    assert source.delivery_partner == MANUFACTURER.casefold()
    assert source.artifact_kinds == ["footprint", "model_3d"]
    assert source.source_urls == [MODEL_3D_URL, FOOTPRINT_URL]
    assert source.support_status == "local-package-supported"
    assert "ultralibrarian" not in json.dumps(result.to_dict()).casefold()


def test_public_model_page_discovers_manufacturer_links_when_api_media_is_empty() -> (
    None
):
    page_html = f"""
    <html><body>
      <h1>{MPN} Footprints and Models</h1>
      <h2>Manufacturer EDA and CAD Models</h2>
      <a href="{FOOTPRINT_URL}">{MPN} - PCB Footprint</a>
      <a href="{MODEL_3D_URL}"><span>{MPN}</span> - 3D Model</a>
      <a href="https://example.invalid/unrelated">OTHER-PART - PCB Footprint</a>
    </body></html>
    """
    result = DigiKeyCadSource(_Api({"MediaLinks": []}, page_html=page_html)).discover(
        CadRequest(manufacturer=MANUFACTURER, mpn=MPN, source="digikey"),
        exact_record=_record(),
    )

    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.provenance.retrieval_mode == (
        "official-api-public-model-page-handoff"
    )
    assert result.missing_artifacts == ["symbol"]
    assert result.available_sources[0].source_urls == [
        MODEL_3D_URL,
        FOOTPRINT_URL,
    ]


def test_generic_manufacturer_host_is_not_same_sky_specific() -> None:
    record = DistributorRecord(
        provider="digikey",
        distributor_part_number="NSC-42-ND",
        product_url=OTHER_PRODUCT_URL,
        manufacturer=OTHER_MANUFACTURER,
        mpn=OTHER_MPN,
    )
    result = _discover(
        {
            "MediaType": "Model",
            "Title": f"{OTHER_MPN} - PCB Footprint",
            "Url": OTHER_FOOTPRINT_URL,
        },
        {
            "MediaType": "Model",
            "Title": f"{OTHER_MPN} - 3D Model",
            "Url": OTHER_MODEL_3D_URL,
        },
        record=record,
    )

    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.provenance.delivery_partner == OTHER_MANUFACTURER.casefold()
    assert result.provenance.model_creator == OTHER_MANUFACTURER.casefold()
    assert result.provenance.landing_url == OTHER_MODEL_URL
    assert result.available_sources[0].support_status == "local-package-supported"
    assert result.available_sources[0].artifact_kinds == [
        "footprint",
        "model_3d",
    ]


def test_unknown_linked_provider_is_preserved_without_claiming_manufacturer() -> None:
    unknown_host = "cad-assets.partner-example.net"
    result = _discover(
        {
            "MediaType": "Model",
            "Title": f"{MPN} - PCB Footprint and 3D Model",
            "Url": f"https://{unknown_host}/parts/{MPN}",
        }
    )

    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.provenance.delivery_partner == unknown_host
    assert result.provenance.model_creator is None
    assert result.available_sources[0].support_status == "manual-handoff"
    assert result.available_sources[0].delivery_partner == unknown_host


def test_manufacturer_provided_label_supports_unrelated_download_hostname() -> None:
    result = _discover(
        {
            "MediaType": "Model",
            "Title": f"Manufacturer Provided {MPN} PCB Footprint",
            "Url": f"https://downloads.example-cdn.net/parts/{MPN}.kicad_mod",
        }
    )

    assert result.provenance.delivery_partner == MANUFACTURER.casefold()
    assert result.provenance.model_creator == MANUFACTURER.casefold()
    assert result.available_sources[0].support_status == "local-package-supported"


def test_linked_interactive_provider_is_reported_without_false_support() -> None:
    result = _discover(
        {
            "MediaType": "Model",
            "Title": "Schematic Symbol and PCB Footprint",
            "Url": "https://www.snapeda.com/parts/MJ-2523-SMT-TR/example",
        }
    )

    assert result.status == CAD_DOWNLOAD_UNAVAILABLE
    assert result.provenance.delivery_partner == "snapmagic"
    assert result.available_sources[0].support_status == "unsupported-interactive"
    assert set(result.missing_artifacts) == {"model_3d"}


def test_multiple_official_sources_remain_separate_and_unselected() -> None:
    result = _discover(
        {
            "MediaType": "Model",
            "Title": "PCB Footprint",
            "Url": FOOTPRINT_URL,
        },
        {
            "MediaType": "Model",
            "Title": "KiCad symbol footprint and 3D model",
            "Url": "https://app.ultralibrarian.com/details/MJ-2523-SMT-TR",
        },
    )

    assert result.status == CAD_MANUAL_DOWNLOAD_REQUIRED
    assert result.provenance.delivery_partner is None
    assert [item.delivery_partner for item in result.available_sources] == [
        MANUFACTURER.casefold(),
        "ultralibrarian",
    ]


def _zip_fixture(
    destination: Path,
    *,
    invalid_step: bool = False,
    manufacturer: str = MANUFACTURER,
    mpn: str = MPN,
    library_name: str = "SameSky",
) -> Path:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(FIXTURE.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            if invalid_step and path.suffix.casefold() == ".step":
                data = b"not a STEP model"
            elif path.suffix.casefold() in (".kicad_mod", ".step", ".txt"):
                data = (
                    data.decode("utf-8")
                    .replace(MANUFACTURER, manufacturer)
                    .replace(MPN, mpn)
                    .replace("SameSky", library_name)
                    .encode("utf-8")
                )
            relative_path = (
                path.relative_to(FIXTURE)
                .as_posix()
                .replace(MPN, mpn)
                .replace("SameSky", library_name)
            )
            archive.writestr(relative_path, data)
    return destination


def _evidence(
    destination: Path,
    archive: Path,
    *,
    mpn: str = MPN,
    manufacturer: str = MANUFACTURER,
    product_url: str = PRODUCT_URL,
    model_url: str = MODEL_URL,
    footprint_url: str = FOOTPRINT_URL,
    model_3d_url: str = MODEL_3D_URL,
) -> Path:
    payload = {
        "agreement_url": model_url,
        "delivery_partner": manufacturer,
        "landing_url": footprint_url,
        "manufacturer": manufacturer,
        "model_creator": manufacturer,
        "mpn": mpn,
        "package_format": "manufacturer-kicad",
        "package_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "product_url": product_url,
        "retrieval_mode": "manual-official-download",
        "retrieved_at_utc": "2026-07-29T00:00:00Z",
        "schema_version": 1,
        "source": "digikey",
        "source_urls": [footprint_url, model_3d_url],
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def test_manufacturer_footprint_and_3d_install_as_typed_partial_package(
    tmp_path: Path,
) -> None:
    archive = _zip_fixture(tmp_path / "same-sky.zip")
    evidence = _evidence(tmp_path / "same-sky.evidence.json", archive)
    output = tmp_path / "parts"

    result = ingest_cad_package(
        archive,
        package_format="manufacturer-kicad",
        request=CadRequest(
            manufacturer=MANUFACTURER,
            mpn=MPN,
            source="digikey",
        ),
        output_base=output,
        evidence_path=evidence,
    )

    assert result.discovery.status == CAD_PARTIAL
    assert result.discovery.action_required is not None
    assert result.discovery.action_required.code == SYMBOL_UNAVAILABLE
    assert result.discovery.missing_artifacts == ["symbol"]
    assert result.discovery.available_sources[0].source_urls == [
        MODEL_3D_URL,
        FOOTPRINT_URL,
    ]
    assert result.package.format_name == "manufacturer-kicad"
    assert {artifact.kind for artifact in result.package.artifacts} == {
        "footprint",
        "step",
    }
    assert result.cad.symbol_name is None
    assert result.cad.symbol_path is None
    assert result.cad.footprint_name == MPN
    assert result.cad.model_3d == MPN
    assert result.cad.delivery_partner == MANUFACTURER.casefold()
    assert result.cad.model_creator == MANUFACTURER.casefold()
    assert result.cad.landing_url == FOOTPRINT_URL
    assert not output.with_suffix(".kicad_sym").exists()
    footprint = output.with_suffix(".pretty") / f"{MPN}.kicad_mod"
    model = output.with_suffix(".3dshapes") / f"{MPN}.step"
    assert footprint.is_file()
    assert model.is_file()
    assert f"${{KIPRJMOD}}/parts.3dshapes/{MPN}.step" in footprint.read_text(
        encoding="utf-8"
    )
    assert all(len(artifact.sha256) == 64 for artifact in result.cad.artifacts)


def test_manufacturer_adapter_imports_an_unrelated_manufacturer_package(
    tmp_path: Path,
) -> None:
    archive = _zip_fixture(
        tmp_path / "northstar.zip",
        manufacturer=OTHER_MANUFACTURER,
        mpn=OTHER_MPN,
        library_name="Northstar",
    )
    evidence = _evidence(
        tmp_path / "northstar.evidence.json",
        archive,
        manufacturer=OTHER_MANUFACTURER,
        mpn=OTHER_MPN,
        product_url=OTHER_PRODUCT_URL,
        model_url=OTHER_MODEL_URL,
        footprint_url=OTHER_FOOTPRINT_URL,
        model_3d_url=OTHER_MODEL_3D_URL,
    )
    output = tmp_path / "northstar-parts"

    result = ingest_cad_package(
        archive,
        package_format="manufacturer-kicad",
        request=CadRequest(
            manufacturer=OTHER_MANUFACTURER,
            mpn=OTHER_MPN,
            source="digikey",
        ),
        output_base=output,
        evidence_path=evidence,
    )

    assert result.discovery.status == CAD_PARTIAL
    assert result.cad.delivery_partner == OTHER_MANUFACTURER.casefold()
    assert result.cad.model_creator == OTHER_MANUFACTURER.casefold()
    assert result.cad.footprint_name == OTHER_MPN
    assert result.cad.model_3d == OTHER_MPN
    assert (output.with_suffix(".pretty") / f"{OTHER_MPN}.kicad_mod").is_file()
    assert (output.with_suffix(".3dshapes") / f"{OTHER_MPN}.step").is_file()


def test_auto_selection_accepts_validated_digikey_manufacturer_partial(
    tmp_path: Path,
) -> None:
    archive = _zip_fixture(tmp_path / "same-sky.zip")
    evidence = _evidence(tmp_path / "same-sky.evidence.json", archive)

    selection = select_auto_cad_package(
        [
            CadPackageCandidate(
                source="digikey",
                archive_path=archive,
                evidence_path=evidence,
            )
        ],
        manufacturer=MANUFACTURER,
        mpn=MPN,
    )

    assert selection.selected.inspection.package.format_name == "manufacturer-kicad"
    assert selection.selected.inspection.symbol_name is None
    assert selection.selected.inspection.pin_numbers == ()
    assert selection.selected.inspection.pad_numbers == ("1", "2", "3")


def test_manufacturer_package_identity_mismatch_and_malformed_model_fail_closed(
    tmp_path: Path,
) -> None:
    archive = _zip_fixture(tmp_path / "same-sky.zip")
    mismatched = _evidence(
        tmp_path / "mismatch.evidence.json",
        archive,
        mpn="MJ-2523-SMT",
    )
    request = CadRequest(
        manufacturer=MANUFACTURER,
        mpn=MPN,
        source="digikey",
    )

    with pytest.raises(CadPackageError, match="CAD_PACKAGE_EVIDENCE_IDENTITY_MISMATCH"):
        ingest_cad_package(
            archive,
            package_format="manufacturer-kicad",
            request=request,
            output_base=tmp_path / "mismatch",
            evidence_path=mismatched,
        )

    malformed = _zip_fixture(tmp_path / "malformed.zip", invalid_step=True)
    malformed_evidence = _evidence(
        tmp_path / "malformed.evidence.json",
        malformed,
    )
    with pytest.raises(CadPackageError, match="CAD_3D_INVALID"):
        ingest_cad_package(
            malformed,
            package_format="manufacturer-kicad",
            request=request,
            output_base=tmp_path / "malformed",
            evidence_path=malformed_evidence,
        )

    unsafe_payload = json.loads(
        _evidence(tmp_path / "unsafe.evidence.json", archive).read_text(
            encoding="utf-8"
        )
    )
    unsafe_payload["source_urls"] = [
        FOOTPRINT_URL,
        "https://127.0.0.1/private.step",
    ]
    unsafe_path = tmp_path / "unsafe.evidence.json"
    unsafe_path.write_text(
        json.dumps(unsafe_payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(CadPackageError, match="CAD_PACKAGE_EVIDENCE_URL_UNSAFE"):
        ingest_cad_package(
            archive,
            package_format="manufacturer-kicad",
            request=request,
            output_base=tmp_path / "unsafe",
            evidence_path=unsafe_path,
        )


def test_full_cli_preserves_partial_outputs_and_returns_nonzero(
    tmp_path: Path,
) -> None:
    archive = _zip_fixture(tmp_path / "same-sky.zip")
    evidence = _evidence(tmp_path / "same-sky.evidence.json", archive)
    output = tmp_path / "parts"
    manifest = tmp_path / "manifest.json"

    exit_code = cli.main(
        [
            "--manufacturer",
            MANUFACTURER,
            "--mpn",
            MPN,
            "--cad-source",
            "digikey",
            "--cad-package",
            str(archive),
            "--cad-package-format",
            "manufacturer-kicad",
            "--cad-package-evidence",
            str(evidence),
            "--full",
            "--output",
            str(output),
            "--manifest-json",
            str(manifest),
        ]
    )

    assert exit_code == 1
    assert not output.with_suffix(".kicad_sym").exists()
    assert (output.with_suffix(".pretty") / f"{MPN}.kicad_mod").is_file()
    assert (output.with_suffix(".3dshapes") / f"{MPN}.step").is_file()
    document = json.loads(manifest.read_text(encoding="utf-8"))
    assert document["cad_discovery"]["status"] == CAD_PARTIAL
    assert document["cad_discovery"]["missing_artifacts"] == ["symbol"]
    assert document["cad_discovery"]["available_sources"][0]["source_urls"] == [
        MODEL_3D_URL,
        FOOTPRINT_URL,
    ]
    assert document["cad"]["symbol_path"] is None
