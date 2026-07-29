from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from easyeda2kicad_digimou.__main__ import get_parser, valid_arguments
from easyeda2kicad_digimou.easyeda.easyeda_api import EasyedaApi
from easyeda2kicad_digimou.metadata.cache import MetadataCache
from easyeda2kicad_digimou.metadata.manifest import manifest_to_dict
from easyeda2kicad_digimou.metadata.models import (
    CAD_IDENTITY_UNRESOLVED,
    CAD_NOT_ACQUIRED,
    CAD_PACKAGE_READY,
    CadArtifact,
    CadDiscoveryResult,
    CadProvenance,
    CadRequest,
    MergedPart,
    NormalizedCadPackage,
    PartIdentity,
)
from easyeda2kicad_digimou.metadata.service import resolve_metadata
from easyeda2kicad_digimou.providers import MetadataProvider, NotFoundError


class _UnusedMetadataProvider:
    name = "lcsc"

    def get_cache_context(self) -> dict[str, str]:
        return {}

    def search_exact_mpn(self, manufacturer: str | None, mpn: str) -> Any:
        del manufacturer, mpn
        raise NotFoundError("lcsc", operation="exact-match")

    def get_part_by_distributor_id(self, part_id: str) -> Any:
        del part_id
        raise NotFoundError("lcsc", operation="id-lookup")


def _provider_factory(_name: str, _api: EasyedaApi) -> MetadataProvider:
    return cast(MetadataProvider, _UnusedMetadataProvider())


def _arguments(*argv: str) -> dict[str, object]:
    return vars(get_parser().parse_args(list(argv)))


def test_unspecified_cad_source_keeps_legacy_lcsc_mode(tmp_path: Path) -> None:
    arguments = _arguments(
        "--lcsc_id", "C2040", "--symbol", "--output", str(tmp_path / "lib")
    )

    assert arguments["cad_source"] == "easyeda"
    assert valid_arguments(arguments)
    assert arguments["metadata_mode"] is False


@pytest.mark.parametrize("source", ["digikey", "mouser"])
def test_explicit_external_cad_source_never_constructs_easyeda_provider(
    source: str,
    tmp_path: Path,
) -> None:
    def fail_if_called(_api: EasyedaApi) -> Any:
        raise AssertionError("explicit external source fell back to EasyEDA")

    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer="Texas Instruments",
        requested_lcsc_id=None,
        provider_names=(),
        cad_api=EasyedaApi(offline=True),
        cad_source=source,
        cache=MetadataCache(tmp_path / "cache"),
        provider_factory=_provider_factory,
        cad_provider_factory=fail_if_called,
    )

    assert result.cad is None
    assert result.cad_data is None
    assert result.blocking_error == CAD_NOT_ACQUIRED
    assert result.cad_discovery is not None
    assert result.cad_discovery.status == CAD_NOT_ACQUIRED
    assert result.cad_discovery.request == CadRequest(
        manufacturer="Texas Instruments",
        mpn="OPA333AIDBVR",
        source=source,
    )


def test_external_cad_request_requires_complete_identity(tmp_path: Path) -> None:
    result = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer=None,
        requested_lcsc_id=None,
        provider_names=(),
        cad_api=EasyedaApi(offline=True),
        cad_source="digikey",
        cache=MetadataCache(tmp_path / "cache"),
        provider_factory=_provider_factory,
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )

    assert result.cad_discovery is not None
    assert result.cad_discovery.status == CAD_IDENTITY_UNRESOLVED
    assert result.cad_discovery.request is None
    assert result.blocking_error == CAD_IDENTITY_UNRESOLVED


@pytest.mark.parametrize(
    ("source", "delivery_partner"),
    [("digikey", None), ("mouser", "samacsys")],
)
def test_manifest_keeps_cad_provenance_roles_separate(
    source: str, delivery_partner: str | None, tmp_path: Path
) -> None:
    resolution = resolve_metadata(
        requested_mpn="OPA333AIDBVR",
        requested_manufacturer="Texas Instruments",
        requested_lcsc_id=None,
        provider_names=(),
        cad_api=EasyedaApi(offline=True),
        cad_source=source,
        cache=MetadataCache(tmp_path / "cache"),
        provider_factory=_provider_factory,
        cad_provider_factory=lambda _api: pytest.fail("EasyEDA fallback"),
    )

    payload = manifest_to_dict(resolution.to_merged())
    provenance = payload["cad_discovery"]["provenance"]
    assert provenance["distributor"] == source
    assert provenance["delivery_partner"] == delivery_partner
    assert provenance["model_creator"] is None


def test_normalized_package_contract_is_content_addressed_and_round_trips() -> None:
    digest = "a" * 64
    package = NormalizedCadPackage(
        request=CadRequest(
            manufacturer="Texas Instruments",
            mpn="OPA333AIDBVR",
            source="digikey",
        ),
        format_name="ultralibrarian-kicad",
        format_version="1",
        artifacts=[
            CadArtifact(
                kind="symbol",
                relative_path="symbols/OPA333.kicad_sym",
                sha256=digest,
            )
        ],
        provenance=CadProvenance(
            distributor="digikey",
            delivery_partner="ultralibrarian",
            model_creator="symbol-author-from-package",
            retrieval_mode="local-package",
            package_hash="b" * 64,
        ),
    )
    result = CadDiscoveryResult(
        requested_source="digikey",
        status=CAD_PACKAGE_READY,
        request=package.request,
        provenance=package.provenance,
        package=package,
    )

    assert CadDiscoveryResult.from_dict(result.to_dict()) == result


@pytest.mark.parametrize(
    "relative_path",
    [
        "/absolute/model.step",
        r"C:\absolute\model.step",
        r"\\server\share\model.step",
        "../escape.kicad_mod",
        "symbols/../escape.kicad_sym",
    ],
)
def test_cad_artifact_rejects_nonportable_relative_paths(
    relative_path: str,
) -> None:
    with pytest.raises(ValueError, match="safe relative path"):
        CadArtifact(kind="symbol", relative_path=relative_path, sha256="a" * 64)
