"""Versioned local-package adapters and atomic KiCad library installation."""

from __future__ import annotations

# Global imports
import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# Local imports
from easyeda2kicad_digimou.metadata.merge import PARTIAL
from easyeda2kicad_digimou.metadata.models import (
    CAD_PACKAGE_READY,
    CadArtifact,
    CadDiscoveryResult,
    CadProvenance,
    CadRecord,
    CadRequest,
    NormalizedCadPackage,
)

from .archive import extract_zip_safely
from .evidence import CadPackageEvidence, load_package_evidence
from .errors import CadPackageError
from .kicad import (
    FootprintSelection,
    SymbolSelection,
    extract_properties,
    merge_symbol_library,
    rewrite_footprint_model,
    rewrite_symbol_footprint,
    select_attested_symbol,
    select_exact_symbol,
    select_footprint,
    validate_model,
    verify_pin_pad_identity,
)

CAD_PACKAGE_FORMATS = (
    "auto",
    "ultralibrarian-kicad",
    "samacsys-kicad",
)
_MAX_TEXT_ARTIFACT_SIZE = 64 * 1024 * 1024
_NOTICE_SUFFIXES = (".txt", ".md", ".html", ".htm")
_SAFE_BASENAME_RE = re.compile(r"^[^<>:\"/\\|?*\x00-\x1f]+$")
_WINDOWS_DEVICE_RE = re.compile(r"(?i)^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$")


@dataclass(frozen=True)
class PackageAdapter:
    format_name: str
    format_version: str
    source: str
    delivery_partner: str
    marker_phrases: Tuple[str, ...]


@dataclass(frozen=True)
class PreparedCadPackage:
    request: CadRequest
    normalized: NormalizedCadPackage
    symbol: SymbolSelection
    footprint: FootprintSelection
    footprint_path: Path
    model_paths: Tuple[Path, ...]
    extraction_root: Path


@dataclass(frozen=True)
class CadPackageIngestResult:
    package: NormalizedCadPackage
    cad: CadRecord
    discovery: CadDiscoveryResult


@dataclass(frozen=True)
class CadPackageInspection:
    """Output-free evidence used to compare validated CAD candidates."""

    package: NormalizedCadPackage
    symbol_name: str
    footprint_name: str
    pin_numbers: Tuple[str, ...]
    pad_numbers: Tuple[str, ...]
    primary_model_name: str

    def material_signature(
        self,
    ) -> Tuple[Tuple[str, ...], Tuple[str, ...], str, str]:
        return (
            self.pin_numbers,
            self.pad_numbers,
            self.footprint_name.casefold(),
            self.primary_model_name.casefold(),
        )


_ADAPTERS: Dict[str, PackageAdapter] = {
    "ultralibrarian-kicad": PackageAdapter(
        format_name="ultralibrarian-kicad",
        format_version="1",
        source="digikey",
        delivery_partner="ultralibrarian",
        marker_phrases=("ultra librarian", "ultralibrarian"),
    ),
    "samacsys-kicad": PackageAdapter(
        format_name="samacsys-kicad",
        format_version="1",
        source="mouser",
        delivery_partner="samacsys",
        marker_phrases=("samacsys", "component search engine"),
    ),
}


def inspect_cad_package(
    archive_path: Path,
    *,
    package_format: str,
    request: CadRequest,
    evidence_path: Optional[Path] = None,
) -> CadPackageInspection:
    """Validate one package completely without installing any output."""

    normalized_format = package_format.strip().lower()
    if normalized_format not in CAD_PACKAGE_FORMATS:
        raise CadPackageError(
            "CAD_PACKAGE_FORMAT_UNSUPPORTED",
            "unsupported CAD package format",
        )
    package_hash = _sha256_file(archive_path)
    evidence = (
        load_package_evidence(
            evidence_path,
            request=request,
            archive_sha256=package_hash,
            requested_format=normalized_format,
        )
        if evidence_path is not None
        else None
    )
    with tempfile.TemporaryDirectory(
        prefix="easyeda2kicad_digimou-cad-inspect-"
    ) as temporary:
        extraction_root = Path(temporary) / "extracted"
        extracted = extract_zip_safely(archive_path, extraction_root)
        adapter = _select_adapter(
            extracted,
            extraction_root,
            normalized_format,
            evidence,
        )
        if request.source != adapter.source:
            raise CadPackageError(
                "CAD_PACKAGE_SOURCE_MISMATCH",
                "package format does not match the candidate CAD source",
            )
        prepared = _prepare_package(
            extraction_root,
            extracted,
            adapter,
            request,
            package_hash,
            evidence,
        )
        primary_model = _primary_model_path(prepared)
        return CadPackageInspection(
            package=prepared.normalized,
            symbol_name=prepared.symbol.name,
            footprint_name=prepared.footprint.name,
            pin_numbers=tuple(sorted(prepared.symbol.pin_numbers)),
            pad_numbers=tuple(sorted(prepared.footprint.pad_numbers)),
            primary_model_name=primary_model.name,
        )


def ingest_cad_package(
    archive_path: Path,
    *,
    package_format: str,
    request: CadRequest,
    output_base: Path,
    overwrite: bool = False,
    project_relative_model_path: Optional[str] = None,
    evidence_path: Optional[Path] = None,
    expected_package_hash: Optional[str] = None,
) -> CadPackageIngestResult:
    """Validate an untrusted package completely before changing output libraries."""

    normalized_format = package_format.strip().lower()
    if normalized_format not in CAD_PACKAGE_FORMATS:
        raise CadPackageError(
            "CAD_PACKAGE_FORMAT_UNSUPPORTED",
            "unsupported CAD package format",
        )
    if not output_base.parent.is_dir():
        raise CadPackageError(
            "CAD_OUTPUT_PARENT_MISSING",
            "output parent directory must already exist",
        )
    package_hash = _sha256_file(archive_path)
    if (
        expected_package_hash is not None
        and package_hash != expected_package_hash.strip().lower()
    ):
        raise CadPackageError(
            "CAD_SOURCE_LOCK_MISMATCH",
            "CAD package content changed after source selection",
        )
    evidence = (
        load_package_evidence(
            evidence_path,
            request=request,
            archive_sha256=package_hash,
            requested_format=normalized_format,
        )
        if evidence_path is not None
        else None
    )
    with tempfile.TemporaryDirectory(
        prefix="easyeda2kicad_digimou-cad-package-"
    ) as temporary:
        temporary_root = Path(temporary)
        extraction_root = temporary_root / "extracted"
        extracted = extract_zip_safely(archive_path, extraction_root)
        adapter = _select_adapter(
            extracted,
            extraction_root,
            normalized_format,
            evidence,
        )
        if request.source != adapter.source:
            raise CadPackageError(
                "CAD_PACKAGE_SOURCE_MISMATCH",
                "package format does not match the explicit CAD source",
            )
        prepared = _prepare_package(
            extraction_root,
            extracted,
            adapter,
            request,
            package_hash,
            evidence,
        )
        cad_record = _install_prepared_package(
            prepared,
            output_base,
            overwrite=overwrite,
            project_relative_model_path=project_relative_model_path,
        )
    discovery = CadDiscoveryResult(
        requested_source=request.source,
        status=CAD_PACKAGE_READY,
        request=request,
        provenance=prepared.normalized.provenance,
        package=prepared.normalized,
    )
    return CadPackageIngestResult(
        package=prepared.normalized,
        cad=cad_record,
        discovery=discovery,
    )


def _prepare_package(
    extraction_root: Path,
    extracted: Sequence[Path],
    adapter: PackageAdapter,
    request: CadRequest,
    package_hash: str,
    evidence: Optional[CadPackageEvidence],
) -> PreparedCadPackage:
    symbol_files = sorted(
        (path for path in extracted if path.suffix.casefold() == ".kicad_sym"),
        key=lambda path: _relative(path, extraction_root).casefold(),
    )
    footprint_files = sorted(
        (path for path in extracted if path.suffix.casefold() == ".kicad_mod"),
        key=lambda path: _relative(path, extraction_root).casefold(),
    )
    model_files = sorted(
        (
            path
            for path in extracted
            if path.suffix.casefold() in (".step", ".stp", ".wrl")
        ),
        key=lambda path: _relative(path, extraction_root).casefold(),
    )
    if not symbol_files:
        raise CadPackageError(
            "CAD_SYMBOL_MISSING", "package has no native KiCad symbol"
        )
    if not footprint_files:
        raise CadPackageError(
            "CAD_FOOTPRINT_MISSING", "package has no native KiCad footprint"
        )
    if not model_files:
        raise CadPackageError("CAD_3D_MISSING", "package has no STEP or WRL model")

    symbol = _select_symbol_files(
        symbol_files,
        request,
        attested=evidence is not None,
    )
    footprint_texts = [(path, _read_text(path)) for path in footprint_files]
    footprint = select_footprint(
        footprint_texts,
        request,
        symbol.footprint_name,
    )
    matching_footprint_paths = [
        path for path, text in footprint_texts if text == footprint.text
    ]
    if len(matching_footprint_paths) != 1:
        raise CadPackageError(
            "CAD_FOOTPRINT_AMBIGUOUS",
            "selected footprint cannot be mapped to one package artifact",
        )
    verify_pin_pad_identity(symbol, footprint)

    model_stems = {path.stem.casefold() for path in model_files}
    if len(model_stems) != 1:
        raise CadPackageError(
            "CAD_3D_AMBIGUOUS",
            "package contains multiple unrelated 3D model names",
        )
    flattened_model_names = [path.name.casefold() for path in model_files]
    if len(flattened_model_names) != len(set(flattened_model_names)):
        raise CadPackageError(
            "CAD_3D_AMBIGUOUS",
            "package contains colliding 3D model filenames",
        )
    for model_path in model_files:
        validate_model(model_path, model_path.read_bytes())

    marker_files = _notice_files(extracted)
    license_paths = [
        _relative(path, extraction_root)
        for path in marker_files
        if "license" in path.name.casefold()
    ]
    notice_paths = [
        _relative(path, extraction_root)
        for path in marker_files
        if any(
            word in path.name.casefold()
            for word in ("notice", "readme", "import", "license")
        )
    ]
    properties = extract_properties(symbol.block)
    package_model_creator = _property_by_key(properties, "modelcreator")
    evidence_model_creator = evidence.model_creator if evidence is not None else None
    if (
        package_model_creator is not None
        and evidence_model_creator is not None
        and package_model_creator.casefold() != evidence_model_creator.casefold()
    ):
        raise CadPackageError(
            "CAD_MODEL_CREATOR_MISMATCH",
            "package and manual handoff evidence name different model creators",
        )
    model_creator = package_model_creator or evidence_model_creator
    license_items = sorted(license_paths)
    if evidence is not None and evidence.agreement_url is not None:
        license_items.append(evidence.agreement_url)
    provenance = CadProvenance(
        distributor=request.source,
        delivery_partner=adapter.delivery_partner,
        model_creator=model_creator,
        landing_url=(evidence.landing_url if evidence is not None else None),
        retrieval_mode=(
            evidence.retrieval_mode if evidence is not None else "local-package"
        ),
        package_hash=package_hash,
        license=";".join(license_items) or None,
        notice=";".join(sorted(notice_paths)) or None,
    )
    artifacts = [
        CadArtifact(
            kind=_artifact_kind(path),
            relative_path=_relative(path, extraction_root),
            sha256=_sha256_file(path),
        )
        for path in [*matching_footprint_paths, *model_files]
    ]
    # The filtered source library is intentionally not required to be byte-identical
    # when the provider bundled unrelated symbols. Always record the source file that
    # proved the exact selected symbol.
    symbol_artifacts = [
        CadArtifact(
            kind="symbol",
            relative_path=_relative(path, extraction_root),
            sha256=_sha256_file(path),
        )
        for path in symbol_files
        if _symbol_file_matches(
            path,
            symbol,
            request,
            attested=evidence is not None,
        )
    ]
    artifacts = [
        *symbol_artifacts,
        *artifacts,
    ]
    if len(symbol_artifacts) != 1:
        raise CadPackageError(
            "CAD_SYMBOL_AMBIGUOUS",
            "selected symbol cannot be mapped to one package artifact",
        )
    normalized = NormalizedCadPackage(
        request=request,
        format_name=adapter.format_name,
        format_version=adapter.format_version,
        artifacts=artifacts,
        provenance=provenance,
    )
    return PreparedCadPackage(
        request=request,
        normalized=normalized,
        symbol=symbol,
        footprint=footprint,
        footprint_path=matching_footprint_paths[0],
        model_paths=tuple(model_files),
        extraction_root=extraction_root,
    )


def _install_prepared_package(
    prepared: PreparedCadPackage,
    output_base: Path,
    *,
    overwrite: bool,
    project_relative_model_path: Optional[str],
) -> CadRecord:
    _safe_artifact_filename(output_base.name)
    symbol_target = Path("{0}.kicad_sym".format(output_base))
    footprint_directory = Path("{0}.pretty".format(output_base))
    model_directory = Path("{0}.3dshapes".format(output_base))
    for target in (symbol_target, footprint_directory, model_directory):
        if target.is_symlink():
            raise CadPackageError(
                "CAD_OUTPUT_LINK_REJECTED",
                "output targets must not be symbolic links",
            )
    _reject_tree_links(footprint_directory)
    _reject_tree_links(model_directory)
    target_snapshots = {
        target: _path_fingerprint(target)
        for target in (symbol_target, footprint_directory, model_directory)
    }

    footprint_filename = _safe_artifact_filename(prepared.footprint.name + ".kicad_mod")
    primary_model = _primary_model_path(prepared)
    portable_model_directory = _safe_project_relative_model_path(
        project_relative_model_path or "{0}.3dshapes".format(output_base.name)
    )
    portable_model_path = "${{KIPRJMOD}}/{0}/{1}".format(
        portable_model_directory,
        primary_model.name,
    )
    rewritten_footprint = rewrite_footprint_model(
        prepared.footprint.text,
        portable_model_path,
    )
    parse_target = select_footprint(
        [(Path(footprint_filename), rewritten_footprint)],
        prepared.request,
        prepared.footprint.name,
    )
    installed_symbol = rewrite_symbol_footprint(
        prepared.symbol,
        prepared.request,
        output_base.name,
        parse_target.name,
    )
    verify_pin_pad_identity(installed_symbol, parse_target)

    existing_symbol_text = _read_text(symbol_target) if symbol_target.exists() else None
    merged_symbol_text = merge_symbol_library(
        existing_symbol_text,
        installed_symbol,
        prepared.request,
        overwrite=overwrite,
    )

    with tempfile.TemporaryDirectory(
        prefix=".easyeda2kicad_digimou-stage-",
        dir=output_base.parent,
    ) as transaction_directory:
        transaction_root = Path(transaction_directory)
        staged_symbol = transaction_root / symbol_target.name
        staged_footprints = transaction_root / footprint_directory.name
        staged_models = transaction_root / model_directory.name
        _write_text_fsync(staged_symbol, merged_symbol_text)
        _stage_directory(footprint_directory, staged_footprints)
        _stage_directory(model_directory, staged_models)

        staged_footprint = staged_footprints / footprint_filename
        _check_existing_footprint(
            staged_footprint,
            rewritten_footprint,
            prepared,
            overwrite=overwrite,
        )
        _write_text_fsync(staged_footprint, rewritten_footprint)

        for model_path in prepared.model_paths:
            target_model = staged_models / _safe_artifact_filename(model_path.name)
            model_data = model_path.read_bytes()
            if target_model.exists() and target_model.read_bytes() != model_data:
                if not overwrite:
                    raise CadPackageError(
                        "CAD_MODEL_EXISTS",
                        "3D model already exists; use --overwrite after identity review",
                        target_model.name,
                    )
            _write_bytes_fsync(target_model, model_data)

        _commit_paths_atomically(
            (
                (staged_symbol, symbol_target),
                (staged_footprints, footprint_directory),
                (staged_models, model_directory),
            ),
            transaction_root,
            target_snapshots,
        )

    installed_artifacts = [
        CadArtifact(
            kind="symbol",
            relative_path=symbol_target.name,
            sha256=_sha256_file(symbol_target),
        ),
        CadArtifact(
            kind="footprint",
            relative_path="{0}/{1}".format(
                footprint_directory.name, footprint_filename
            ),
            sha256=_sha256_file(footprint_directory / footprint_filename),
        ),
        *[
            CadArtifact(
                kind=_artifact_kind(model_path),
                relative_path="{0}/{1}".format(model_directory.name, model_path.name),
                sha256=_sha256_file(model_directory / model_path.name),
            )
            for model_path in prepared.model_paths
        ],
    ]
    provenance = prepared.normalized.provenance
    return CadRecord(
        source=prepared.request.source,
        symbol_name=prepared.symbol.name,
        footprint_name=prepared.footprint.name,
        model_3d=primary_model.stem,
        symbol_path=symbol_target.name,
        footprint_path="{0}/{1}".format(footprint_directory.name, footprint_filename),
        model_3d_path="{0}/{1}".format(model_directory.name, primary_model.name),
        verification_status=PARTIAL,
        distributor=provenance.distributor,
        delivery_partner=provenance.delivery_partner,
        model_creator=provenance.model_creator,
        retrieval_mode=provenance.retrieval_mode,
        package_hash=provenance.package_hash,
        license=provenance.license,
        notice=provenance.notice,
        artifacts=installed_artifacts,
    )


def _primary_model_path(prepared: PreparedCadPackage) -> Path:
    return next(
        (
            path
            for path in prepared.model_paths
            if path.suffix.casefold() in (".step", ".stp")
        ),
        prepared.model_paths[0],
    )


def _select_adapter(
    files: Sequence[Path],
    root: Path,
    requested_format: str,
    evidence: Optional[CadPackageEvidence],
) -> PackageAdapter:
    marker_text = "\n".join(_read_marker_text(path) for path in _notice_files(files))
    relative_names = "\n".join(_relative(path, root) for path in files)
    package_evidence_text = (relative_names + "\n" + marker_text).casefold()
    matches = [
        adapter
        for adapter in _ADAPTERS.values()
        if any(marker in package_evidence_text for marker in adapter.marker_phrases)
    ]
    if requested_format != "auto":
        selected = _ADAPTERS[requested_format]
        if selected not in matches:
            if (
                evidence is not None
                and evidence.package_format == selected.format_name
                and _matches_attested_layout(selected, files, root)
            ):
                return replace(selected, format_version="2")
            raise CadPackageError(
                "CAD_PACKAGE_FORMAT_UNPROVEN",
                "package does not contain evidence for the selected adapter",
            )
        return selected
    if not matches and evidence is not None:
        selected = _ADAPTERS[evidence.package_format]
        if _matches_attested_layout(selected, files, root):
            return replace(selected, format_version="2")
    if len(matches) != 1:
        raise CadPackageError(
            "CAD_PACKAGE_FORMAT_AMBIGUOUS",
            "package format cannot be identified uniquely",
        )
    return matches[0]


def _matches_attested_layout(
    adapter: PackageAdapter,
    files: Sequence[Path],
    root: Path,
) -> bool:
    if adapter.format_name != "ultralibrarian-kicad":
        return False
    relative_paths = [PurePosixPath(_relative(path, root)) for path in files]
    symbol_paths = [
        path
        for path in relative_paths
        if path.suffix.casefold() == ".kicad_sym"
        and path.parts
        and path.parts[0].casefold() == "kicadv6"
    ]
    footprint_paths = [
        path
        for path in relative_paths
        if path.suffix.casefold() == ".kicad_mod"
        and any(part.casefold().endswith(".pretty") for part in path.parts[:-1])
    ]
    model_paths = [
        path
        for path in relative_paths
        if path.suffix.casefold() in (".step", ".stp", ".wrl")
    ]
    return len(symbol_paths) == 1 and bool(footprint_paths) and bool(model_paths)


def _select_symbol_files(
    symbol_files: Sequence[Path],
    request: CadRequest,
    *,
    attested: bool = False,
) -> SymbolSelection:
    selections: List[SymbolSelection] = []
    mismatch_seen = False
    for path in symbol_files:
        try:
            selector = select_attested_symbol if attested else select_exact_symbol
            selections.append(selector(_read_text(path), request))
        except CadPackageError as error:
            if error.code == "CAD_IDENTITY_MISMATCH":
                mismatch_seen = True
                continue
            if error.code == "CAD_IDENTITY_UNPROVEN":
                continue
            raise CadPackageError(error.code, error.detail, path.name) from None
    if len(selections) > 1:
        raise CadPackageError(
            "CAD_SYMBOL_AMBIGUOUS",
            "multiple symbol libraries prove the requested identity",
        )
    if not selections:
        raise CadPackageError(
            "CAD_IDENTITY_MISMATCH" if mismatch_seen else "CAD_IDENTITY_UNPROVEN",
            (
                "package symbol identity conflicts with the requested part"
                if mismatch_seen
                else "no package symbol proves manufacturer and exact MPN"
            ),
        )
    return selections[0]


def _symbol_file_matches(
    path: Path,
    selection: SymbolSelection,
    request: CadRequest,
    *,
    attested: bool = False,
) -> bool:
    try:
        selector = select_attested_symbol if attested else select_exact_symbol
        candidate = selector(_read_text(path), request)
    except CadPackageError:
        return False
    return candidate.name == selection.name and candidate.block == selection.block


def _check_existing_footprint(
    target: Path,
    incoming_text: str,
    prepared: PreparedCadPackage,
    *,
    overwrite: bool,
) -> None:
    if not target.exists():
        return
    existing_text = _read_text(target)
    try:
        existing = select_footprint(
            [(target, existing_text)],
            prepared.request,
            prepared.footprint.name,
        )
    except CadPackageError as error:
        if error.code == "CAD_IDENTITY_MISMATCH":
            raise
        raise CadPackageError(
            "CAD_FOOTPRINT_EXISTS_UNVERIFIED",
            "existing footprint cannot be identity-checked safely",
            target.name,
        ) from None
    verify_pin_pad_identity(prepared.symbol, existing)
    if _canonical_text(existing_text) == _canonical_text(incoming_text):
        return
    if not overwrite:
        raise CadPackageError(
            "CAD_FOOTPRINT_EXISTS",
            "footprint already exists; use --overwrite after identity review",
            target.name,
        )


def _stage_directory(source: Path, destination: Path) -> None:
    if source.exists():
        if not source.is_dir():
            raise CadPackageError(
                "CAD_OUTPUT_CONFLICT", "library directory path is occupied by a file"
            )
        shutil.copytree(source, destination, symlinks=True)
    else:
        destination.mkdir(parents=True)


def _commit_paths_atomically(
    staged_targets: Sequence[Tuple[Path, Path]],
    transaction_root: Path,
    expected_snapshots: Mapping[Path, Optional[str]],
) -> None:
    for _staged, target in staged_targets:
        if _path_fingerprint(target) != expected_snapshots[target]:
            raise CadPackageError(
                "CAD_OUTPUT_CONCURRENT_MODIFICATION",
                "an output library changed while the package was staged",
            )
    backups: List[Tuple[Path, Path]] = []
    installed: List[Path] = []
    try:
        for index, (staged, target) in enumerate(staged_targets):
            backup = transaction_root / "backup-{0}".format(index)
            if target.exists():
                os.replace(target, backup)
                backups.append((backup, target))
            os.replace(staged, target)
            installed.append(target)
    except OSError:
        for target in reversed(installed):
            _remove_path(target)
        for backup, target in reversed(backups):
            if backup.exists():
                os.replace(backup, target)
        raise CadPackageError(
            "CAD_INSTALL_FAILED",
            "atomic CAD library installation failed and was rolled back",
        ) from None


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _reject_tree_links(root: Path) -> None:
    if not root.exists():
        return
    if not root.is_dir():
        raise CadPackageError(
            "CAD_OUTPUT_CONFLICT", "library directory path is occupied by a file"
        )
    if any(path.is_symlink() for path in root.rglob("*")):
        raise CadPackageError(
            "CAD_OUTPUT_LINK_REJECTED",
            "existing library directories must not contain symbolic links",
        )


def _path_fingerprint(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(b"file\x00")
        digest.update(bytes.fromhex(_sha256_file(path)))
        return digest.hexdigest()
    if not path.is_dir():
        raise CadPackageError(
            "CAD_OUTPUT_CONFLICT", "output target has an unsupported filesystem type"
        )
    digest.update(b"directory\x00")
    for item in sorted(path.rglob("*"), key=lambda value: value.as_posix().casefold()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\x00")
        if item.is_dir():
            digest.update(b"directory\x00")
        elif item.is_file():
            digest.update(b"file\x00")
            digest.update(bytes.fromhex(_sha256_file(item)))
        else:
            raise CadPackageError(
                "CAD_OUTPUT_CONFLICT",
                "output tree has an unsupported filesystem entry",
            )
    return digest.hexdigest()


def _notice_files(files: Sequence[Path]) -> List[Path]:
    return [
        path
        for path in files
        if path.suffix.casefold() in _NOTICE_SUFFIXES
        and any(
            word in path.name.casefold()
            for word in ("notice", "readme", "license", "import", "samac", "ultra")
        )
    ]


def _read_marker_text(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            return stream.read(1024 * 1024).decode("utf-8-sig", errors="ignore")
    except OSError:
        return ""


def _read_text(path: Path) -> str:
    try:
        if path.stat().st_size > _MAX_TEXT_ARTIFACT_SIZE:
            raise CadPackageError(
                "CAD_KICAD_TOO_LARGE",
                "KiCad text artifact exceeds the 64 MiB parser limit",
                path.name,
            )
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise CadPackageError(
            "CAD_KICAD_ENCODING_INVALID",
            "KiCad text artifacts must be UTF-8",
            path.name,
        ) from None
    except OSError:
        raise CadPackageError(
            "CAD_KICAD_READ_FAILED",
            "KiCad artifact could not be read",
            path.name,
        ) from None


def _write_text_fsync(path: Path, value: str) -> None:
    _write_bytes_fsync(path, value.encode("utf-8"))


def _write_bytes_fsync(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        raise CadPackageError(
            "CAD_INSTALL_FAILED", "staged CAD artifact could not be written"
        ) from None


def _safe_artifact_filename(value: str) -> str:
    if (
        not value
        or value in (".", "..")
        or value.endswith((" ", "."))
        or _SAFE_BASENAME_RE.fullmatch(value) is None
        or _WINDOWS_DEVICE_RE.fullmatch(value)
    ):
        raise CadPackageError(
            "CAD_ARTIFACT_NAME_UNSAFE",
            "package-derived artifact name is not portable",
        )
    return value


def _safe_project_relative_model_path(value: str) -> str:
    portable = value.replace("\\", "/")
    path = PurePosixPath(portable)
    if (
        not portable
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in portable)
    ):
        raise CadPackageError(
            "CAD_PROJECT_MODEL_PATH_UNSAFE",
            "project-relative 3D model path is not portable",
        )
    return path.as_posix()


def _artifact_kind(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix == ".kicad_sym":
        return "symbol"
    if suffix == ".kicad_mod":
        return "footprint"
    if suffix in (".step", ".stp"):
        return "step"
    if suffix == ".wrl":
        return "wrl"
    raise CadPackageError("CAD_ARTIFACT_UNSUPPORTED", "unsupported CAD artifact type")


def _property_by_key(properties: Dict[str, str], requested_key: str) -> Optional[str]:
    for key, value in properties.items():
        normalized = "".join(
            character for character in key.casefold() if character.isalnum()
        )
        if normalized == requested_key and value.strip():
            return value.strip()
    return None


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_text(value: str) -> str:
    return value.replace("\r\n", "\n").strip()


__all__ = [
    "CAD_PACKAGE_FORMATS",
    "CadPackageIngestResult",
    "ingest_cad_package",
]
