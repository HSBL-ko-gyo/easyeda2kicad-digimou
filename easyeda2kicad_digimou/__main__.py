from __future__ import annotations

# Global imports
import argparse
import ctypes
import json
import logging
import re
import sys
import unicodedata
import uuid
from pathlib import Path, PurePath
from typing import Any, TextIO

# Local imports
from ._version import CLI_NAME, __version__, version_identity
from .cad import (
    CAD_PACKAGE_FORMATS,
    CadPackageCandidate,
    CadPackageError,
    CadPackageIngestResult,
    ingest_cad_package,
    select_auto_cad_package,
    write_source_lock,
)
from .easyeda.easyeda_api import EasyedaApi
from .easyeda.easyeda_importer import (
    Easyeda3dModelImporter,
    EasyedaFootprintImporter,
    EasyedaSymbolImporter,
)
from .easyeda.easyeda_svg_renderer import render_footprint_svg, render_symbol_svg
from .easyeda.parameters_easyeda import EeFootprint, EeSymbol
from .kicad.export_kicad_3d_model import Exporter3dModelKicad
from .kicad.export_kicad_footprint import ExporterFootprintKicad
from .kicad.export_kicad_symbol import ExporterSymbolKicad
from .headless import (
    HEADLESS_COMMANDS,
    HeadlessCommandError,
    acquire_plan_result,
    capabilities_result,
    error_result,
    project_inspection_result,
    verify_artifacts_result,
)
from .machine import (
    MachineEventWriter,
    build_machine_result,
    emit_machine_result_events,
    internal_machine_result,
    invalid_machine_result,
    write_machine_json,
)
from .metadata.cache import (
    redact_configured_secret_text,
    sanitize_public_url,
    strip_secrets,
)
from .metadata.manifest import write_csv_manifest, write_json_manifest
from .metadata.merge import (
    CAD_NOT_FOUND,
    CAD_PIN_PAD_MISMATCH,
    PARTIAL,
    VERIFIED,
)
from .metadata.models import (
    CAD_SOURCE_CONFLICT,
    CAD_SOURCE_LOCK_MISMATCH,
    CadActionRequired,
    CadDiscoveryResult,
    CadProvenance,
    CadRequest,
    MergedPart,
    PartIdentity,
    SUPPORTED_CAD_SOURCES,
    model_to_dict,
    normalize_manufacturer,
    normalize_mpn,
)
from .metadata.service import MetadataResolution, MetadataServiceError, resolve_metadata
from .metadata.symbol_fields import (
    build_native_symbol_fields,
    build_symbol_fields,
)
from .project_registration import (
    ProjectRegistrationError,
    ProjectRegistrationPlan,
    apply_project_registration,
    plan_project_registration,
    project_relative_path,
    resolve_project,
)

SUPPORTED_PROVIDERS = ("lcsc", "digikey", "mouser")
SUPPORTED_CAD_SOURCE_CHOICES = ("easyeda", "digikey", "mouser", "auto")
RESERVED_METADATA_FIELDS = {
    "Reference",
    "Value",
    "Footprint",
    "Datasheet",
    "Manufacturer",
    "MPN",
    "LCSC Part",
    "LCSC Product URL",
    "DigiKey Part",
    "DigiKey Product URL",
    "Mouser Part",
    "Mouser Product URL",
    "Manufacturer Datasheet",
    "Package",
    "Lifecycle",
    "CAD Source",
    "Verification Status",
    "Description",
    "ki_description",
    "ki_keywords",
    # Distributor sales/cache data belongs in manifests, never KiCad symbols.
    "Stock",
    "Price",
    "Price Breaks",
    "price_breaks",
    "MOQ",
    "Minimum Order Quantity",
    "minimum_order_quantity",
    "Currency",
    "Retrieved At",
    "retrieved_at",
    "Raw Response Cache Key",
    "raw_response_cache_key",
    "Raw Cache Key",
    "raw_cache_key",
    "Raw/Cache Key",
    "Cache Key",
    "cache_key",
    "Packaging",
}
RESERVED_METADATA_FIELD_KEYS = {
    unicodedata.normalize("NFKC", key).strip().casefold()
    for key in RESERVED_METADATA_FIELDS
}
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CONIN$",
        "CONOUT$",
        *("COM{0}".format(number) for number in range(1, 10)),
        *("LPT{0}".format(number) for number in range(1, 10)),
    }
)


def is_safe_cad_artifact_basename(value: Any) -> bool:
    """Return whether a CAD-derived name stays one portable filesystem entry."""

    if not isinstance(value, str) or not value:
        return False
    normalized = unicodedata.normalize("NFKC", value)
    if normalized in (".", "..") or normalized.endswith((" ", ".")):
        return False
    if any(
        ord(character) < 32 or ord(character) == 127 or character in '<>:"/\\|?*'
        for character in normalized
    ):
        return False
    device_name = normalized.split(".", 1)[0].upper()
    return device_name not in _WINDOWS_RESERVED_BASENAMES


def relative_path_if_within(root: PurePath, candidate: PurePath) -> PurePath | None:
    """Return a relative path only when candidate is within the same root."""

    try:
        return candidate.relative_to(root)
    except ValueError:
        return None


def _same_or_descendant(candidate: PurePath, parent: PurePath) -> bool:
    return candidate == parent or parent in candidate.parents


def parse_custom_fields(custom_field_args: list[str]) -> dict[str, str]:
    custom_fields: dict[str, str] = {}
    for custom_field in custom_field_args:
        key, separator, value = custom_field.partition(":")
        key = key.strip()
        value = value.strip()
        if not separator:
            raise ValueError(
                f'Invalid custom field "{custom_field}". Expected KEY:VALUE.'
            )
        if not key:
            raise ValueError(
                f'Invalid custom field "{custom_field}". Key must not be empty.'
            )
        custom_fields[key] = value
    return custom_fields


def normalize_footprint_pad_number(number: str) -> str:
    """Apply the same EasyEDA pad-number normalization as the KiCad exporter."""
    normalized = number.strip()
    if "(" in normalized and ")" in normalized:
        normalized = normalized.split("(", 1)[1].split(")", 1)[0]
    return normalized.strip()


def is_electrical_footprint_pad(pad: Any) -> bool:
    """Include SMD pads and plated through-holes, but not NPTH mechanics."""
    hole_radius = getattr(pad, "hole_radius", None)
    if hole_radius is None:
        return bool(getattr(pad, "is_plated", False))
    return float(hole_radius) <= 0 or bool(getattr(pad, "is_plated", False))


def verify_symbol_footprint_pins(
    symbol: EeSymbol, footprint: EeFootprint
) -> tuple[bool, set[str], set[str]]:
    """Compare electrical symbol pins with plated, numbered footprint pads."""
    symbol_units = [symbol, *symbol.sub_symbols]
    pin_numbers = {
        pin.settings.spice_pin_number.strip()
        for unit in symbol_units
        for pin in unit.pins
        if pin.settings.spice_pin_number.strip()
    }
    pad_numbers = {
        normalize_footprint_pad_number(pad.number)
        for pad in footprint.pads
        if is_electrical_footprint_pad(pad)
        and normalize_footprint_pad_number(pad.number)
    }
    return (
        bool(pin_numbers and pad_numbers and pin_numbers == pad_numbers),
        pin_numbers,
        pad_numbers,
    )


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=CLI_NAME,
        description=(
            "A Python script that convert any electronic components from LCSC or"
            " EasyEDA to a Kicad library"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=version_identity(),
    )

    parser.add_argument(
        "--lcsc_id",
        help="LCSC id(s); optional when --mpn is provided",
        required=False,
        type=str,
        nargs="+",
        default=[],
    )

    parser.add_argument(
        "--mpn",
        help="Exact manufacturer part number",
        required=False,
        type=str,
    )

    parser.add_argument(
        "--manufacturer",
        help="Manufacturer name used to constrain exact MPN matching",
        required=False,
        type=str,
    )

    parser.add_argument(
        "--providers",
        help="Comma-separated metadata providers: lcsc,digikey,mouser",
        required=False,
        type=str,
    )

    parser.add_argument(
        "--cad-source",
        choices=SUPPORTED_CAD_SOURCE_CHOICES,
        default="easyeda",
        help=(
            "CAD source; explicit digikey/mouser never fall back to EasyEDA "
            "(default: easyeda)"
        ),
        required=False,
    )

    parser.add_argument(
        "--cad-package",
        type=str,
        help="Import a locally downloaded Ultra Librarian or SamacSys ZIP package",
        required=False,
    )

    parser.add_argument(
        "--cad-package-format",
        choices=CAD_PACKAGE_FORMATS,
        default="auto",
        help="Local CAD package adapter (default: auto)",
        required=False,
    )

    parser.add_argument(
        "--cad-package-evidence",
        type=str,
        help=("Sanitized hash-bound JSON receipt for an official manual CAD download"),
        required=False,
    )

    parser.add_argument(
        "--cad-candidate",
        action="append",
        default=[],
        metavar="SOURCE=ZIP",
        help=(
            "Validated local package candidate for --cad-source auto; "
            "repeat with digikey=PATH and mouser=PATH"
        ),
        required=False,
    )

    parser.add_argument(
        "--cad-candidate-evidence",
        action="append",
        default=[],
        metavar="SOURCE=JSON",
        help="Optional hash-bound evidence for the matching --cad-candidate source",
        required=False,
    )

    parser.add_argument(
        "--cad-source-lock",
        type=str,
        help="Atomic source/package SHA-256 lock for reproducible auto selection",
        required=False,
    )

    parser.add_argument(
        "--datasheet-link",
        choices=("manufacturer", "lcsc", "digikey", "mouser"),
        help="Select the KiCad Datasheet property source",
        required=False,
    )

    parser.add_argument(
        "--manifest-json",
        type=str,
        help="Write the merged part manifest as JSON",
        required=False,
    )

    parser.add_argument(
        "--manifest-csv",
        type=str,
        help="Write a BOM-compatible merged part manifest as CSV",
        required=False,
    )

    parser.add_argument(
        "--require-cad",
        action="store_true",
        help="Return a non-zero status when exact EasyEDA CAD is unavailable",
    )

    parser.add_argument(
        "--require-providers",
        action="store_true",
        help="Return a non-zero status unless every selected provider returns a record",
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help="Forbid network access and use cache entries only",
    )

    parser.add_argument(
        "--refresh-metadata",
        action="store_true",
        help="Bypass distributor metadata cache without refreshing CAD",
    )

    parser.add_argument(
        "--show-conflicts",
        action="store_true",
        help="Print structured metadata conflicts",
    )

    parser.add_argument(
        "--no-price",
        action="store_true",
        help="Exclude volatile price breaks from manifest output",
    )

    parser.add_argument(
        "--no-stock",
        action="store_true",
        help="Exclude volatile stock values from manifest output",
    )

    parser.add_argument(
        "--symbol", help="Get symbol of this id", required=False, action="store_true"
    )

    parser.add_argument(
        "--footprint",
        help="Get footprint of this id",
        required=False,
        action="store_true",
    )

    parser.add_argument(
        "--3d",
        help="Get the 3d model of this id",
        required=False,
        action="store_true",
    )

    parser.add_argument(
        "--full",
        help="Get the symbol, footprint and 3d model of this id",
        required=False,
        action="store_true",
    )

    parser.add_argument(
        "--svg",
        help="Export symbol and footprint as SVG (from raw API data, no KiCad conversion)",
        required=False,
        action="store_true",
    )

    parser.add_argument(
        "--output",
        required=False,
        metavar="file.kicad_sym",
        help="Output file",
        type=str,
    )

    parser.add_argument(
        "--overwrite",
        required=False,
        help=(
            "overwrite symbol, footprint, and 3D model if there is already a component"
            " with this lcsc_id"
        ),
        action="store_true",
    )

    parser.add_argument(
        "--project-relative",
        required=False,
        help="Sets the 3D file path stored relative to the project",
        action="store_true",
    )

    parser.add_argument(
        "--project",
        required=False,
        type=str,
        help="KiCad .kicad_pro file or unambiguous project directory",
    )

    parser.add_argument(
        "--register-project-libraries",
        required=False,
        action="store_true",
        help="Opt in to project-local sym-lib-table and fp-lib-table registration",
    )

    parser.add_argument(
        "--dry-run",
        required=False,
        action="store_true",
        help="Preview project library registration without CAD or project writes",
    )

    parser.add_argument(
        "--debug",
        help="set the logging level to debug",
        required=False,
        default=False,
        action="store_true",
    )

    # Preserve argparse abbreviations accepted before metadata options made
    # --debug and --project-relative ambiguous.  Keep them out of --help so no
    # new shorthand is advertised as a stable public spelling.
    parser.add_argument(
        "--d",
        dest="debug",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--p",
        "--pr",
        "--pro",
        dest="project_relative",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--use-cache",
        dest="use_cache",
        help="cache API responses in .easyeda_cache/ to avoid repeated network requests",
        required=False,
        default=False,
        action="store_true",
    )

    parser.add_argument(
        "--custom-field",
        dest="custom_field",
        nargs="+",
        default=[],
        metavar="KEY:VALUE",
        help="Add custom symbol properties, e.g. --custom-field 'Mfr:TI' 'Package:SOT-23'",
    )

    return parser


def get_acquire_parser() -> argparse.ArgumentParser:
    """Return the additive machine-acquire parser without changing legacy syntax."""

    parser = get_parser()
    parser.prog = f"{CLI_NAME} acquire"
    parser.allow_abbrev = False
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--machine-json",
        action="store_true",
        help="Write one schema-v1 UTF-8 result document to stdout",
    )
    output.add_argument(
        "--json-events",
        action="store_true",
        help="Write a versioned UTF-8 JSON Lines event stream to stdout",
    )
    parser.add_argument(
        "--require-provider",
        action="append",
        choices=SUPPORTED_PROVIDERS,
        default=[],
        help="Require one provider record; repeat for multiple providers",
    )
    parser.add_argument(
        "--require-jlcpcb-resolution",
        action="store_true",
        help="Require a canonical JLCPCB/LCSC part-number resolution",
    )
    parser.add_argument(
        "--require-project-registration",
        action="store_true",
        help="Require successful opt-in project library registration",
    )
    return parser


def get_headless_parser(command: str) -> argparse.ArgumentParser:
    """Return one read-only discovery parser."""

    parser = argparse.ArgumentParser(
        prog="{0} {1}".format(CLI_NAME, command),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--machine-json",
        action="store_true",
        help="Accepted for explicit machine-mode invocation; output is always JSON",
    )
    if command == "capabilities":
        return parser
    if command == "inspect-project":
        parser.add_argument("project_path", nargs="?")
        parser.add_argument("--project")
        return parser
    if command == "plan-acquire":
        parser.add_argument("--manufacturer")
        parser.add_argument("--mpn")
        parser.add_argument("--lcsc-id", "--lcsc_id", dest="lcsc_id")
        parser.add_argument("--providers", default="lcsc")
        parser.add_argument(
            "--require-provider",
            dest="required_providers",
            action="append",
            choices=SUPPORTED_PROVIDERS,
            default=[],
        )
        parser.add_argument(
            "--cad-source",
            choices=SUPPORTED_CAD_SOURCE_CHOICES,
            default="easyeda",
        )
        parser.add_argument("--cad-package")
        parser.add_argument("--offline", action="store_true")
        parser.add_argument("--require-cad", action="store_true")
        parser.add_argument("--require-jlcpcb-resolution", action="store_true")
        parser.add_argument("--project")
        parser.add_argument("--output")
        parser.add_argument("--register-project-libraries", action="store_true")
        parser.add_argument("--require-project-registration", action="store_true")
        return parser
    if command == "verify-artifacts":
        parser.add_argument("result_path", nargs="?")
        parser.add_argument("--result")
        parser.add_argument("--project-root")
        parser.add_argument("--output-root")
        parser.add_argument("--cwd-root")
        return parser
    raise ValueError("unsupported headless command")


def is_metadata_mode(arguments: dict[str, Any]) -> bool:
    """Return whether any additive metadata behavior was explicitly requested."""
    return bool(
        arguments.get("mpn")
        or arguments.get("manufacturer")
        or arguments.get("providers") is not None
        or arguments.get("cad_source", "easyeda") != "easyeda"
        or arguments.get("cad_package")
        or arguments.get("cad_package_format", "auto") != "auto"
        or arguments.get("cad_package_evidence")
        or arguments.get("cad_candidate")
        or arguments.get("cad_candidate_evidence")
        or arguments.get("cad_source_lock")
        or arguments.get("datasheet_link") is not None
        or arguments.get("manifest_json")
        or arguments.get("manifest_csv")
        or arguments.get("require_cad")
        or arguments.get("require_providers")
        or arguments.get("machine_json")
        or arguments.get("json_events")
        or arguments.get("offline")
        or arguments.get("refresh_metadata")
        or arguments.get("show_conflicts")
        or arguments.get("no_price")
        or arguments.get("no_stock")
    )


def parse_providers(value: str | None, metadata_mode: bool) -> list[str]:
    """Parse and validate a comma-separated provider selection."""
    if value is None:
        return ["lcsc"] if metadata_mode else []

    providers = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not providers:
        raise ValueError("--providers must include at least one provider")
    unsupported = sorted(set(providers).difference(SUPPORTED_PROVIDERS))
    if unsupported:
        raise ValueError(
            "Unsupported provider(s): "
            + ", ".join(unsupported)
            + ". Choose from lcsc,digikey,mouser."
        )
    # Preserve user order while preventing duplicate requests.
    return list(dict.fromkeys(providers))


def parse_cad_candidate_paths(
    values: list[str],
    *,
    option_name: str,
) -> dict[str, str]:
    """Parse repeatable source=path values without guessing a provider."""

    parsed: dict[str, str] = {}
    for value in values:
        source, separator, raw_path = value.partition("=")
        source = source.strip().lower()
        raw_path = raw_path.strip()
        if not separator or source not in ("digikey", "mouser") or not raw_path:
            raise ValueError(f"{option_name} requires digikey=PATH or mouser=PATH")
        if source in parsed:
            raise ValueError(f"{option_name} accepts one path per source")
        parsed[source] = raw_path
    return parsed


def _manifest_collides_with_selected_cad_output(arguments: dict[str, Any]) -> bool:
    """Return whether a metadata file would occupy a selected output ancestor."""

    output = arguments.get("output")
    if not output:
        return False

    selected_outputs: list[tuple[str, Path, bool]] = []
    imports_package = bool(
        arguments.get("cad_package") or arguments.get("cad_candidates")
    )
    if arguments["symbol"] or imports_package:
        selected_outputs.append(("symbol", Path(f"{output}.kicad_sym"), True))
    if arguments["footprint"] or imports_package:
        selected_outputs.append(
            ("footprint directory", Path(f"{output}.pretty"), False)
        )
    if arguments["3d"] or imports_package:
        selected_outputs.append(
            ("3D model directory", Path(f"{output}.3dshapes"), False)
        )
    if arguments["svg"]:
        selected_outputs.append(("SVG directory", Path(f"{output}.svgs"), False))

    resolved_outputs = [
        (description, path.resolve(), is_file)
        for description, path, is_file in selected_outputs
    ]
    for option_name in ("manifest_json", "manifest_csv", "cad_source_lock"):
        manifest = arguments.get(option_name)
        if not manifest:
            continue
        resolved_manifest = Path(manifest).resolve()
        for description, resolved_output, output_is_file in resolved_outputs:
            if (
                _same_or_descendant(resolved_output, resolved_manifest)
                or (
                    output_is_file
                    and _same_or_descendant(resolved_manifest, resolved_output)
                )
                or (
                    option_name == "cad_source_lock"
                    and _same_or_descendant(resolved_manifest, resolved_output)
                )
            ):
                logging.error(
                    "--%s path conflicts with the selected %s output tree",
                    option_name.replace("_", "-"),
                    description,
                )
                return True
    return False


def valid_arguments(arguments: dict[str, Any]) -> bool:
    metadata_mode = is_metadata_mode(arguments)
    arguments["metadata_mode"] = metadata_mode
    if arguments.get("cad_source") not in SUPPORTED_CAD_SOURCES:
        logging.error("Unsupported CAD source")
        return False
    raw_candidates = arguments.get("cad_candidate") or []
    raw_candidate_evidence = arguments.get("cad_candidate_evidence") or []
    if isinstance(raw_candidates, str):
        raw_candidates = [raw_candidates]
    if isinstance(raw_candidate_evidence, str):
        raw_candidate_evidence = [raw_candidate_evidence]
    try:
        arguments["cad_candidates"] = parse_cad_candidate_paths(
            raw_candidates,
            option_name="--cad-candidate",
        )
        arguments["cad_candidate_evidence_paths"] = parse_cad_candidate_paths(
            raw_candidate_evidence,
            option_name="--cad-candidate-evidence",
        )
    except ValueError as error:
        logging.error("%s", error)
        return False
    if arguments["cad_candidates"]:
        if arguments.get("cad_package"):
            logging.error("--cad-candidate cannot be combined with --cad-package")
            return False
        if arguments.get("cad_source") != "auto":
            logging.error("--cad-candidate requires --cad-source auto")
            return False
        if not arguments.get("manufacturer") or not arguments.get("mpn"):
            logging.error("--cad-candidate requires --manufacturer and an exact --mpn")
            return False
        if arguments.get("cad_package_format", "auto") != "auto":
            logging.error("--cad-package-format cannot be used with --cad-candidate")
            return False
        unknown_evidence = set(arguments["cad_candidate_evidence_paths"]).difference(
            arguments["cad_candidates"]
        )
        if unknown_evidence:
            logging.error(
                "--cad-candidate-evidence requires a matching --cad-candidate"
            )
            return False
        for source, candidate_path in arguments["cad_candidates"].items():
            if not Path(candidate_path).is_file():
                logging.error(
                    "--cad-candidate %s path must be an existing ZIP file",
                    source,
                )
                return False
        for source, evidence_path in arguments["cad_candidate_evidence_paths"].items():
            if not Path(evidence_path).is_file():
                logging.error(
                    "--cad-candidate-evidence %s path must be an existing JSON file",
                    source,
                )
                return False
        source_lock = arguments.get("cad_source_lock")
        if (
            source_lock
            and Path(source_lock).exists()
            and not Path(source_lock).is_file()
        ):
            logging.error("--cad-source-lock must name a JSON file")
            return False
    elif arguments["cad_candidate_evidence_paths"]:
        logging.error("--cad-candidate-evidence requires --cad-candidate")
        return False
    elif arguments.get("cad_source_lock"):
        logging.error("--cad-source-lock requires --cad-candidate")
        return False
    if arguments.get("cad_package"):
        if not arguments.get("manufacturer") or not arguments.get("mpn"):
            logging.error("--cad-package requires --manufacturer and an exact --mpn")
            return False
        if arguments.get("cad_source") not in ("digikey", "mouser"):
            logging.error(
                "--cad-package requires --cad-source digikey or --cad-source mouser"
            )
            return False
        if not Path(arguments["cad_package"]).is_file():
            logging.error("--cad-package path must be an existing ZIP file")
            return False
        if (
            arguments.get("cad_package_evidence")
            and not Path(arguments["cad_package_evidence"]).is_file()
        ):
            logging.error("--cad-package-evidence path must be an existing JSON file")
            return False
    elif arguments.get("cad_package_format", "auto") != "auto":
        logging.error("--cad-package-format requires --cad-package")
        return False
    elif arguments.get("cad_package_evidence"):
        logging.error("--cad-package-evidence requires --cad-package")
        return False

    if not arguments["lcsc_id"] and not arguments.get("mpn"):
        logging.error("At least one of --lcsc_id or --mpn is required")
        return False

    for lcsc_id in arguments["lcsc_id"]:
        is_valid_lcsc = (
            bool(re.fullmatch(r"C[1-9][0-9]*", lcsc_id))
            if metadata_mode
            else lcsc_id.startswith("C")
        )
        if not is_valid_lcsc:
            logging.error(f"lcsc_id '{lcsc_id}' should start with C")
            return False

    if arguments.get("mpn"):
        arguments["mpn"] = arguments["mpn"].strip()
        if not arguments["mpn"]:
            logging.error("--mpn must not be empty")
            return False

    if arguments.get("manufacturer") is not None:
        arguments["manufacturer"] = arguments["manufacturer"].strip()
        if not arguments["manufacturer"]:
            logging.error("--manufacturer must not be empty")
            return False

    if metadata_mode and len(arguments["lcsc_id"]) > 1:
        logging.error("Metadata mode accepts at most one --lcsc_id")
        return False

    if arguments.get("offline") and arguments.get("refresh_metadata"):
        logging.error("--offline and --refresh-metadata cannot be used together")
        return False

    try:
        arguments["provider_names"] = parse_providers(
            arguments.get("providers"), metadata_mode
        )
    except ValueError as err:
        logging.error(str(err))
        return False
    arguments["required_provider_names"] = (
        list(arguments["provider_names"]) if arguments.get("require_providers") else []
    )

    datasheet_provider = arguments.get("datasheet_link")
    if (
        datasheet_provider in SUPPORTED_PROVIDERS
        and datasheet_provider not in arguments["provider_names"]
    ):
        # An explicitly requested distributor datasheet must be fetched even
        # when --providers omitted or excluded that provider. Preserve the
        # user's provider order and append only the missing source.
        arguments["provider_names"].append(datasheet_provider)

    if arguments["full"]:
        arguments["symbol"], arguments["footprint"], arguments["3d"] = True, True, True

    if arguments.get("register_project_libraries"):
        if not arguments.get("project"):
            logging.error("--register-project-libraries requires --project")
            return False
        if not arguments.get("output"):
            logging.error("--register-project-libraries requires an explicit --output")
            return False
        if not (
            arguments.get("cad_package")
            or arguments.get("cad_candidates")
            or (arguments["symbol"] and arguments["footprint"])
        ):
            logging.error(
                "--register-project-libraries requires symbol and footprint generation"
            )
            return False
        # Registration promises portable project-local 3D references. This does
        # not make --project-relative imply registration in the other direction.
        arguments["project_relative"] = True
    if arguments.get("dry_run") and not arguments.get("register_project_libraries"):
        logging.error("--dry-run requires --register-project-libraries")
        return False
    if (
        arguments.get("project")
        and not arguments.get("register_project_libraries")
        and not arguments.get("project_relative")
    ):
        logging.error(
            "--project requires --register-project-libraries or --project-relative"
        )
        return False

    if not any(
        [
            arguments["symbol"],
            arguments["footprint"],
            arguments["3d"],
            arguments["svg"],
            arguments.get("manifest_json"),
            arguments.get("manifest_csv"),
            arguments.get("require_cad"),
            arguments.get("require_providers"),
            arguments.get("machine_json"),
            arguments.get("json_events"),
            arguments.get("show_conflicts"),
            arguments.get("cad_package"),
            arguments.get("cad_candidates"),
        ]
    ):
        logging.error(
            "Missing action arguments\n"
            "  easyeda2kicad-digimou --lcsc_id=C2040 --footprint\n"
            "  easyeda2kicad-digimou --lcsc_id=C2040 --symbol\n"
            "  easyeda2kicad-digimou --lcsc_id=C2040 --svg"
        )
        return False

    try:
        arguments["custom_fields"] = parse_custom_fields(arguments["custom_field"])
    except ValueError as err:
        logging.error(str(err))
        return False

    if metadata_mode:
        reserved = sorted(
            key
            for key in arguments["custom_fields"]
            if unicodedata.normalize("NFKC", key).strip().casefold()
            in RESERVED_METADATA_FIELD_KEYS
        )
        if reserved:
            logging.error(
                "Metadata fields cannot be overridden with --custom-field: "
                + ", ".join(reserved)
            )
            return False

    if arguments.get("manifest_json") and arguments.get("manifest_csv"):
        json_manifest = Path(arguments["manifest_json"]).resolve()
        csv_manifest = Path(arguments["manifest_csv"]).resolve()
        if json_manifest == csv_manifest:
            logging.error("--manifest-json and --manifest-csv must use different paths")
            return False
        if _same_or_descendant(json_manifest, csv_manifest) or _same_or_descendant(
            csv_manifest, json_manifest
        ):
            logging.error(
                "--manifest-json and --manifest-csv paths cannot contain one another"
            )
            return False

    if arguments["project_relative"] and not arguments["output"]:
        logging.error(
            "A project specific library path should be given with --output option when"
            " using --project-relative option\nFor example: easyeda2kicad-digimou"
            " --lcsc_id=C2040 --full"
            " --output=C:/Users/your_username/Documents/Kicad/6.0/projects/my_project"
            " --project-relative"
        )
        return False

    needs_cad_output = any(
        [
            arguments["symbol"],
            arguments["footprint"],
            arguments["3d"],
            arguments["svg"],
            arguments.get("cad_package"),
            arguments.get("cad_candidates"),
        ]
    )

    create_default_folder = False
    if arguments["output"]:
        output_path = Path(arguments["output"])

        # If the user passed a directory (no filename), use default lib name
        if output_path.is_dir():
            base_folder = output_path
            lib_name = "easyeda2kicad"
        else:
            base_folder = output_path.parent
            lib_name = output_path.stem or "easyeda2kicad"
    elif needs_cad_output or not metadata_mode:
        base_folder = Path.home() / "Documents" / "Kicad" / "easyeda2kicad"
        lib_name = "easyeda2kicad"
        create_default_folder = True
        arguments["use_default_folder"] = True

    else:
        arguments["output"] = None
        return True

    arguments["output"] = str(base_folder / lib_name)
    if arguments.get("cad_candidates") and not arguments.get("cad_source_lock"):
        arguments["cad_source_lock"] = "{0}.cad-source-lock.json".format(
            arguments["output"]
        )
    if arguments.get("cad_source_lock"):
        source_lock_path = Path(arguments["cad_source_lock"]).resolve()
        for manifest_option in ("manifest_json", "manifest_csv"):
            manifest_value = arguments.get(manifest_option)
            if not manifest_value:
                continue
            manifest_path = Path(manifest_value).resolve()
            if (
                source_lock_path == manifest_path
                or _same_or_descendant(source_lock_path, manifest_path)
                or _same_or_descendant(manifest_path, source_lock_path)
            ):
                logging.error(
                    "--cad-source-lock and --%s paths cannot contain one another",
                    manifest_option.replace("_", "-"),
                )
                return False

    if arguments["project_relative"]:
        try:
            project_context = (
                resolve_project(arguments["project"])
                if arguments.get("project")
                else None
            )
        except ProjectRegistrationError as error:
            logging.error("%s", error)
            return False
        project_root = (
            project_context.project_root
            if project_context is not None
            else Path.cwd().resolve()
        )
        model_directory = Path(f"{arguments['output']}.3dshapes").resolve()
        relative_model_directory: str | None
        try:
            if project_context is not None:
                relative_model_directory = project_relative_path(
                    project_context, model_directory
                )
            else:
                current_project_relative = relative_path_if_within(
                    project_root, model_directory
                )
                relative_model_directory = (
                    current_project_relative.as_posix()
                    if current_project_relative is not None
                    else None
                )
        except ProjectRegistrationError as error:
            logging.error("%s", error)
            return False
        if relative_model_directory is None:
            logging.error(
                "--project-relative output must remain within the current project directory"
            )
            return False
        arguments["project_relative_3d_path"] = relative_model_directory
        if project_context is not None:
            arguments["project_file"] = str(project_context.project_file)
            arguments["project_root"] = str(project_context.project_root)

    if metadata_mode and _manifest_collides_with_selected_cad_output(arguments):
        return False

    if create_default_folder:
        base_folder.mkdir(parents=True, exist_ok=True)
    elif not base_folder.is_dir() and not arguments.get("dry_run"):
        logging.error(f"Can't find the folder : {base_folder}")
        return False

    if arguments.get("register_project_libraries"):
        try:
            arguments["project_registration_plan"] = plan_project_registration(
                arguments["project"],
                arguments["output"],
                require_artifacts=False,
            )
        except ProjectRegistrationError as error:
            logging.error("%s", error)
            return False

    return True


def _reconcile_symbol_identity(
    symbol_info: Any, verified_identity: dict[str, str]
) -> None:
    """Fill empty native fields without replacing non-empty CAD properties."""

    fields = (
        ("manufacturer", "manufacturer", normalize_manufacturer),
        ("mpn", "mpn", normalize_mpn),
        ("lcsc_id", "lcsc_id", lambda value: str(value).strip().casefold()),
    )
    for identity_key, attribute, normalizer in fields:
        incoming = verified_identity.get(identity_key, "")
        if not incoming:
            continue
        existing = str(getattr(symbol_info, attribute, "") or "")
        if not existing.strip():
            setattr(symbol_info, attribute, incoming)
            continue
        if normalizer(existing) == normalizer(incoming):
            continue
        if identity_key == "manufacturer":
            logging.warning(
                "Verified manufacturer display differs from the existing CAD "
                "property; preserving the CAD value"
            )
            continue
        raise ValueError(
            "verified {0} conflicts with the existing CAD property".format(identity_key)
        )


def _process_component(
    component_id: str,
    arguments: dict[str, Any],
    api: EasyedaApi,
    cad_data_override: dict[str, Any] | None = None,
    symbol_metadata: dict[str, str] | None = None,
    symbol_identity: dict[str, str] | None = None,
    datasheet_url: str | None = None,
) -> bool:
    """Process a single LCSC component. Returns True on success, False on error."""
    cad_data = (
        cad_data_override
        if cad_data_override is not None
        else api.get_cad_data_of_component(lcsc_id=component_id)
    )
    if not cad_data:
        logging.error(f"Failed to fetch data from EasyEDA API for part {component_id}")
        return False

    output = arguments["output"]

    if arguments["symbol"]:
        # ---------------- SYMBOL ----------------
        easyeda_symbol: EeSymbol = EasyedaSymbolImporter(
            easyeda_cp_cad_data=cad_data
        ).get_symbol()
        if symbol_identity:
            _reconcile_symbol_identity(easyeda_symbol.info, symbol_identity)
        if datasheet_url is not None:
            easyeda_symbol.info.datasheet = datasheet_url

        custom_fields = dict(symbol_metadata or {})
        custom_fields.update(arguments["custom_fields"])
        lib_path = f"{output}.kicad_sym"
        exporter = ExporterSymbolKicad(
            symbol=easyeda_symbol,
            lib_path=lib_path,
            custom_fields=custom_fields,
        )
        if not exporter.save_to_lib(
            lib_path=lib_path,
            footprint_lib_name=Path(output).stem,
            overwrite=arguments["overwrite"],
        ):
            logging.error(
                f"Symbol for {component_id} already exists. Use --overwrite to update"
            )
            return False
        if easyeda_symbol.sub_symbols:
            logging.info(
                f"Integrated {len(easyeda_symbol.sub_symbols)} sub-symbols into main symbol"
            )
        logging.info(
            f"Created Kicad symbol for ID : {component_id}\n"
            f"       Symbol name : {easyeda_symbol.info.name}\n"
            f"       Library path : {lib_path}"
        )

    if arguments["footprint"]:
        # ---------------- FOOTPRINT ----------------
        easyeda_footprint = EasyedaFootprintImporter(
            easyeda_cp_cad_data=cad_data
        ).get_footprint()
        if not is_safe_cad_artifact_basename(easyeda_footprint.info.name):
            logging.error("Unsafe CAD-derived footprint artifact name")
            return False
        if (
            Path(f"{output}.pretty") / f"{easyeda_footprint.info.name}.kicad_mod"
        ).is_file() and not arguments["overwrite"]:
            logging.error(
                f"Footprint for {component_id} already exists. Use --overwrite to replace"
            )
            return False
        footprint_path = Path(f"{output}.pretty")
        if arguments.get("use_default_folder"):
            model_3d_path = "${EASYEDA2KICAD}/easyeda2kicad.3dshapes"
        elif arguments["project_relative"]:
            relative_3d_path = arguments.get("project_relative_3d_path")
            if not isinstance(relative_3d_path, str):
                logging.error("Project-relative 3D output path was not validated")
                return False
            model_3d_path = "${KIPRJMOD}/" + relative_3d_path
        else:
            model_3d_path = Path(f"{output}.3dshapes").as_posix()
        footprint_filename = f"{easyeda_footprint.info.name}.kicad_mod"
        ExporterFootprintKicad(footprint=easyeda_footprint).export(
            footprint_full_path=str(footprint_path / footprint_filename),
            model_3d_path=model_3d_path,
        )
        logging.info(
            f"Created Kicad footprint for ID: {component_id}\n"
            f"       Footprint name: {easyeda_footprint.info.name}\n"
            f"       Footprint path: {footprint_path / footprint_filename}"
        )

    if arguments["svg"]:
        # ---------------- SVG ----------------
        svg_dir = Path(f"{output}.svgs")
        svg_dir.mkdir(parents=True, exist_ok=True)

        sym_svg_path = svg_dir / f"{component_id}_symbol.svg"
        sym_svg = render_symbol_svg(cad_data)
        sym_svg_path.write_text(sym_svg, encoding="utf-8")
        logging.info(
            f"Created SVG symbol for ID: {component_id}\n       Path: {sym_svg_path}"
        )

        fp_svg_path = svg_dir / f"{component_id}_footprint.svg"
        fp_svg = render_footprint_svg(cad_data)
        fp_svg_path.write_text(fp_svg, encoding="utf-8")
        logging.info(
            f"Created SVG footprint for ID: {component_id}\n       Path: {fp_svg_path}"
        )

    if arguments["3d"]:
        # ---------------- 3D MODEL ----------------
        easyeda_model = Easyeda3dModelImporter(
            easyeda_cp_cad_data=cad_data,
            download_raw_3d_model=True,
            api=api,
        ).output
        if easyeda_model is not None and not is_safe_cad_artifact_basename(
            easyeda_model.name
        ):
            logging.error("Unsafe CAD-derived 3D model artifact name")
            return False
        model_exporter = Exporter3dModelKicad(
            model_3d=easyeda_model,
        )
        output_dir = Path(f"{output}.3dshapes")
        if not model_exporter.output:
            logging.warning(f"No 3D model available for ID: {component_id}")
        elif not model_exporter.export(
            output_dir=str(output_dir), overwrite=arguments["overwrite"]
        ):
            logging.error(
                f"3D model for {component_id} already exists. Use --overwrite to replace"
            )
            return False
        else:
            model_name = model_exporter.output.name
            logging.info(
                f"Created 3D model for ID: {component_id}\n"
                f"       3D model name: {model_name}\n"
                f"       3D model path (wrl): {output_dir / f'{model_name}.wrl'}\n"
                f"       3D model path (step): {output_dir / f'{model_name}.step'}"
            )

    return True


def _verify_metadata_cad(
    result: MetadataResolution,
    *,
    require_symbol: bool,
    require_footprint: bool,
) -> tuple[str, Any, Any]:
    """Parse only requested artifacts and compare pins/pads when both exist."""

    if result.cad_data is None:
        if result.cad is not None and result.cad.verification_status == CAD_NOT_FOUND:
            return CAD_NOT_FOUND, None, None
        return PARTIAL, None, None

    symbol = None
    footprint = None
    if require_symbol:
        try:
            symbol = EasyedaSymbolImporter(
                easyeda_cp_cad_data=result.cad_data
            ).get_symbol()
        except (KeyError, TypeError, ValueError, IndexError):
            result.provider_errors["easyeda"] = "INVALID_RESPONSE"
            result.blocking_error = "INVALID_RESPONSE"
            return PARTIAL, None, None
    if require_footprint:
        try:
            footprint = EasyedaFootprintImporter(
                easyeda_cp_cad_data=result.cad_data
            ).get_footprint()
        except (KeyError, TypeError, ValueError, IndexError):
            result.provider_errors["easyeda"] = "INVALID_RESPONSE"
            result.blocking_error = "INVALID_RESPONSE"
            return PARTIAL, symbol, None

    if not (require_symbol and require_footprint):
        return VERIFIED, symbol, footprint
    if symbol is None or footprint is None:
        result.provider_errors["easyeda"] = "INVALID_RESPONSE"
        result.blocking_error = "INVALID_RESPONSE"
        return PARTIAL, symbol, footprint

    compatible, pin_numbers, pad_numbers = verify_symbol_footprint_pins(
        symbol, footprint
    )
    if not pin_numbers or not pad_numbers:
        result.provider_errors["cad_verification"] = (
            "INVALID_RESPONSE: empty symbol pin or plated pad set"
        )
        result.blocking_error = "INVALID_RESPONSE"
        return PARTIAL, symbol, footprint
    if not compatible:
        result.provider_errors["cad_verification"] = (
            "CAD_PIN_PAD_MISMATCH: pins={0}; pads={1}".format(
                ",".join(sorted(pin_numbers)), ",".join(sorted(pad_numbers))
            )
        )
        result.blocking_error = CAD_PIN_PAD_MISMATCH
        return CAD_PIN_PAD_MISMATCH, symbol, footprint
    return VERIFIED, symbol, footprint


def _update_cad_artifact_paths(
    result: MetadataResolution,
    arguments: dict[str, Any],
    symbol: Any,
    footprint: Any,
) -> None:
    if result.cad is None or not arguments.get("output"):
        return
    output = arguments["output"]
    if symbol is not None:
        result.cad.symbol_name = symbol.info.name
    if footprint is not None:
        result.cad.footprint_name = footprint.info.name
    if arguments["symbol"] and symbol is not None:
        result.cad.symbol_path = str(Path(f"{output}.kicad_sym"))
    if arguments["footprint"] and footprint is not None:
        result.cad.footprint_path = str(
            Path(f"{output}.pretty") / f"{footprint.info.name}.kicad_mod"
        )
    if arguments["3d"] and result.cad.model_3d:
        model_dir = Path(f"{output}.3dshapes")
        step_path = model_dir / f"{result.cad.model_3d}.step"
        wrl_path = model_dir / f"{result.cad.model_3d}.wrl"
        if step_path.is_file():
            # CadRecord has one path; STEP is the primary interchange artifact.
            result.cad.model_3d_path = str(step_path)
        elif wrl_path.is_file():
            result.cad.model_3d_path = str(wrl_path)


def _write_requested_manifests(merged: MergedPart, arguments: dict[str, Any]) -> bool:
    try:
        if arguments.get("manifest_json"):
            write_json_manifest(
                merged,
                arguments["manifest_json"],
                include_price=not arguments["no_price"],
                include_stock=not arguments["no_stock"],
            )
        if arguments.get("manifest_csv"):
            write_csv_manifest(
                merged,
                arguments["manifest_csv"],
                include_price=not arguments["no_price"],
                include_stock=not arguments["no_stock"],
            )
    except (OSError, TypeError, ValueError) as error:
        logging.error("Failed to write manifest: %s", type(error).__name__)
        arguments["_machine_error_code"] = "MANIFEST_WRITE_FAILED"
        return False
    return True


def _write_console_json(value: Any, *, stream: TextIO | None = None) -> None:
    """Write one credential-safe JSON line without partial console encoding."""

    target = sys.stdout if stream is None else stream
    safe_value = strip_secrets(value)
    serialized = json.dumps(
        safe_value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    encoding = getattr(target, "encoding", None)
    if encoding:
        try:
            (serialized + "\n").encode(encoding)
        except UnicodeEncodeError:
            serialized = json.dumps(
                safe_value,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
    # ``strip_secrets`` above is the enforced sink boundary, but CodeQL does
    # not model this project-specific recursive sanitizer.
    target.write(serialized + "\n")


def _show_metadata_conflicts(merged: MergedPart) -> None:
    diagnostics = merged.to_dict()["provider_diagnostics"]
    _write_console_json(
        {
            "conflicts": model_to_dict(merged.conflicts),
            "provider_errors": merged.provider_errors,
            "provider_diagnostics": diagnostics,
        }
    )


def _log_project_registration_plan(
    plan: ProjectRegistrationPlan,
    *,
    prefix: str,
) -> None:
    logging.info("%s project: %s", prefix, plan.context.project_file)
    for update in plan.updates:
        logging.info(
            "%s %s: %s -> %s (%s; target=%s)",
            prefix,
            update.root_name,
            update.entry.nickname,
            update.entry.uri,
            update.action,
            update.path,
        )


def _run_project_registration_dry_run(arguments: dict[str, Any]) -> int:
    plan = arguments.get("project_registration_plan")
    if not isinstance(plan, ProjectRegistrationPlan):
        logging.error("Project registration plan was not validated")
        return 1
    _log_project_registration_plan(plan, prefix="DRY-RUN")
    return 0


def _register_project_libraries(arguments: dict[str, Any]) -> bool:
    try:
        plan = plan_project_registration(
            arguments["project"],
            arguments["output"],
            require_artifacts=True,
        )
        result = apply_project_registration(plan)
    except ProjectRegistrationError as error:
        logging.error("%s", error)
        arguments["_machine_project_error"] = error.code
        arguments["_machine_error_code"] = error.code
        return False
    arguments["_machine_project_plan"] = plan
    arguments["_machine_project_result"] = result
    arguments["_machine_project_succeeded"] = True
    _log_project_registration_plan(plan, prefix="REGISTER")
    if result.changed_paths:
        logging.info(
            "Updated project library tables: %s",
            ", ".join(str(path) for path in result.changed_paths),
        )
    else:
        logging.info("Project libraries were already registered; no table changes")
    return True


def _log_metadata_diagnostics(merged: MergedPart, *, require_cad: bool) -> None:
    """Make safe internal diagnostics visible without requiring a manifest."""

    for provider, diagnostic in sorted(merged.provider_errors.items()):
        # Provider errors contain only service-defined codes/diagnostics; raw
        # HTTP errors, request URLs, and credential values never enter this map.
        context = merged.provider_diagnostics.get(provider)
        operation = (
            " operation={0}".format(context.operation)
            if context is not None and context.operation
            else ""
        )
        status = (
            " status={0}".format(context.status)
            if context is not None and context.status is not None
            else ""
        )
        setup_url = (
            sanitize_public_url(context.setup_url)
            if context is not None and context.setup_url
            else None
        )
        logging.warning(
            "Metadata provider %s: %s%s%s",
            provider,
            diagnostic,
            operation,
            status,
        )
        if setup_url is not None:
            logging.warning("Metadata provider %s setup: %s", provider, setup_url)

    if merged.cad_discovery is not None:
        logging.warning(
            "CAD source %s: %s",
            merged.cad_discovery.requested_source,
            merged.cad_discovery.status,
        )
        action = merged.cad_discovery.action_required
        if action is not None:
            logging.warning("CAD action required %s: %s", action.code, action.detail)
            setup_url = sanitize_public_url(action.setup_url)
            if setup_url is not None:
                logging.warning("CAD handoff: %s", setup_url)

    if merged.verification_status == CAD_NOT_FOUND:
        if require_cad:
            logging.error(
                "CAD_NOT_FOUND: --require-cad requires verified EasyEDA CAD data"
            )
        else:
            logging.warning("CAD_NOT_FOUND: verified EasyEDA CAD data is unavailable")


def _run_metadata_mode(arguments: dict[str, Any]) -> int:
    if arguments.get("cad_package"):
        return _run_cad_package_mode(arguments)
    if arguments.get("cad_candidates"):
        return _run_auto_cad_package_mode(arguments)

    resolved = _resolve_metadata_request(arguments)
    if resolved is None:
        return 1
    cad_api, result, verification_status, symbol, footprint = resolved
    return _finish_metadata_mode(
        arguments,
        cad_api,
        result,
        verification_status,
        symbol,
        footprint,
    )


def _resolve_metadata_request(
    arguments: dict[str, Any],
    *,
    discover_auto_handoff: bool = True,
) -> (
    tuple[
        EasyedaApi,
        MetadataResolution,
        str,
        EeSymbol | None,
        EeFootprint | None,
    ]
    | None
):
    # CAD and metadata caches intentionally have different control planes.
    cad_api = EasyedaApi(
        use_cache=arguments["use_cache"] or arguments["offline"],
        offline=arguments["offline"],
    )
    metadata_api = EasyedaApi(use_cache=False, offline=arguments["offline"])
    try:
        result = resolve_metadata(
            requested_mpn=arguments.get("mpn"),
            requested_manufacturer=arguments.get("manufacturer"),
            requested_lcsc_id=(
                arguments["lcsc_id"][0] if arguments["lcsc_id"] else None
            ),
            provider_names=arguments["provider_names"],
            cad_api=cad_api,
            cad_source=arguments["cad_source"],
            metadata_api=metadata_api,
            offline=arguments["offline"],
            refresh_metadata=arguments["refresh_metadata"],
            discover_auto_handoff=discover_auto_handoff,
        )
    except MetadataServiceError as error:
        logging.error("%s", error)
        arguments["_machine_error_code"] = error.code
        return None

    verification_status, symbol, footprint = _verify_metadata_cad(
        result,
        require_symbol=arguments["symbol"],
        require_footprint=arguments["footprint"],
    )
    if result.cad is not None:
        result.cad.verification_status = verification_status
        if arguments["3d"] and result.cad_data is not None and not result.cad.model_3d:
            try:
                model = Easyeda3dModelImporter(
                    easyeda_cp_cad_data=result.cad_data,
                    download_raw_3d_model=False,
                    api=cad_api,
                ).output
                if model is not None:
                    result.cad.model_3d = model.name
            except (KeyError, TypeError, ValueError, IndexError):
                # Missing 3D data is already a supported non-fatal upstream case.
                pass
    return cad_api, result, verification_status, symbol, footprint


def _finish_metadata_mode(
    arguments: dict[str, Any],
    cad_api: EasyedaApi,
    result: MetadataResolution,
    verification_status: str,
    symbol: EeSymbol | None,
    footprint: EeFootprint | None,
) -> int:
    merged = result.to_merged(verification_status)
    export_failed = False
    cad_export_succeeded = False

    can_export = (
        result.cad_data is not None
        and verification_status == VERIFIED
        and result.blocking_error is None
    )
    if can_export:
        default_datasheet = symbol.info.datasheet if symbol is not None else None
        try:
            native_fields = build_native_symbol_fields(
                merged,
                datasheet_choice=arguments.get("datasheet_link"),
                default_datasheet=default_datasheet,
            )
        except ValueError as error:
            logging.error("%s", error)
            result.provider_errors["datasheet"] = "DATASHEET_UNAVAILABLE"
            result.blocking_error = "DATASHEET_UNAVAILABLE"
            merged = result.to_merged(overall_status=PARTIAL)
        else:
            symbol_identity = {
                "manufacturer": native_fields.get("Manufacturer", ""),
                "mpn": native_fields.get("MPN", ""),
                "lcsc_id": native_fields.get("LCSC Part", ""),
            }
            explicit_datasheet = (
                native_fields.get("Datasheet")
                if arguments.get("datasheet_link") is not None
                else None
            )
            try:
                exported = _process_component(
                    (result.cad.lcsc_part_number or "") if result.cad else "",
                    arguments,
                    cad_api,
                    cad_data_override=result.cad_data,
                    symbol_metadata=build_symbol_fields(merged),
                    symbol_identity=symbol_identity,
                    datasheet_url=explicit_datasheet,
                )
            except (OSError, KeyError, TypeError, ValueError, IndexError) as error:
                logging.error("CAD export failed: %s", type(error).__name__)
                exported = False
            if not exported:
                export_failed = True
                result.provider_errors["export"] = "EXPORT_FAILED"
                result.blocking_error = "EXPORT_FAILED"
                arguments["_machine_error_code"] = "CAD_EXPORT_FAILED"
                merged = result.to_merged(overall_status=PARTIAL)
            else:
                _update_cad_artifact_paths(result, arguments, symbol, footprint)
                merged = result.to_merged(VERIFIED)
                cad_export_succeeded = True

    registration_failed = False
    if arguments.get("register_project_libraries"):
        if not cad_export_succeeded:
            logging.error(
                "Project libraries were not registered because CAD export did not succeed"
            )
            registration_failed = True
        elif not _register_project_libraries(arguments):
            registration_failed = True

    _log_metadata_diagnostics(merged, require_cad=arguments["require_cad"])
    arguments["_machine_merged"] = merged
    manifests_ok = _write_requested_manifests(merged, arguments)
    if arguments.get("show_conflicts"):
        _show_metadata_conflicts(merged)

    if (
        not manifests_ok
        or export_failed
        or registration_failed
        or result.blocking_error
    ):
        return 1
    if merged.verification_status == CAD_PIN_PAD_MISMATCH:
        return 1
    if merged.verification_status == CAD_NOT_FOUND and arguments["require_cad"]:
        return 1
    required_providers = {
        str(provider).lower()
        for provider in arguments.get("required_provider_names", ())
    }
    returned_providers = {
        record.provider.lower() for record in merged.distributor_records
    }
    missing_required = sorted(required_providers.difference(returned_providers))
    if missing_required:
        for provider in missing_required:
            code = merged.provider_errors.get(provider, "PROVIDER_RECORD_MISSING")
            logging.error(
                "Required metadata provider %s did not return a record: %s",
                provider,
                code,
            )
        return 1
    return 0


def _run_auto_cad_package_mode(arguments: dict[str, Any]) -> int:
    """Prefer verified EasyEDA CAD, then select only fully validated packages."""

    manufacturer = arguments.get("manufacturer")
    mpn = arguments.get("mpn")
    if not isinstance(manufacturer, str) or not isinstance(mpn, str):
        logging.error("Auto CAD package identity was not validated")
        return 1
    lock_path = Path(
        arguments.get("cad_source_lock")
        or "{0}.cad-source-lock.json".format(arguments["output"])
    )
    resolved = _resolve_metadata_request(arguments, discover_auto_handoff=False)
    if resolved is None:
        return 1
    cad_api, metadata_result, verification_status, symbol, footprint = resolved
    if (
        not lock_path.exists()
        and metadata_result.cad_data is not None
        and verification_status == VERIFIED
        and metadata_result.blocking_error is None
    ):
        return _finish_metadata_mode(
            arguments,
            cad_api,
            metadata_result,
            verification_status,
            symbol,
            footprint,
        )

    candidates = [
        CadPackageCandidate(
            source=source,
            archive_path=Path(path),
            evidence_path=(
                Path(arguments["cad_candidate_evidence_paths"][source])
                if source in arguments["cad_candidate_evidence_paths"]
                else None
            ),
        )
        for source, path in arguments["cad_candidates"].items()
    ]
    try:
        selection = select_auto_cad_package(
            candidates,
            manufacturer=manufacturer,
            mpn=mpn,
            source_lock_path=lock_path,
        )
    except CadPackageError as error:
        logging.error("%s", error)
        arguments["_machine_error_code"] = error.code
        if _write_auto_selection_failure(
            arguments,
            metadata_result,
            manufacturer,
            mpn,
            error,
        ):
            return 1
        return 1

    selected = selection.selected
    request = CadRequest(
        manufacturer=manufacturer,
        mpn=mpn,
        source=selected.candidate.source,
    )
    try:
        result = ingest_cad_package(
            selected.candidate.archive_path,
            package_format=selected.inspection.package.format_name,
            request=request,
            output_base=Path(arguments["output"]),
            overwrite=arguments["overwrite"],
            project_relative_model_path=_package_model_relative_path(arguments),
            evidence_path=selected.candidate.evidence_path,
            expected_package_hash=selection.source_lock.package_sha256,
        )
        if (
            result.package.provenance.package_hash
            != selection.source_lock.package_sha256
        ):
            raise CadPackageError(
                "CAD_SOURCE_LOCK_MISMATCH",
                "installed package hash changed after candidate validation",
            )
        write_source_lock(lock_path, selection.source_lock)
    except CadPackageError as error:
        logging.error("%s", error)
        arguments["_machine_error_code"] = error.code
        return 1

    logging.info(
        "Auto CAD selected %s package %s",
        request.source,
        selection.source_lock.package_sha256,
    )
    return _finish_ingested_package(
        arguments,
        request,
        result,
        metadata_result=metadata_result,
    )


def _write_auto_selection_failure(
    arguments: dict[str, Any],
    result: MetadataResolution,
    manufacturer: str,
    mpn: str,
    error: CadPackageError,
) -> bool:
    if error.code == CAD_SOURCE_CONFLICT:
        status = CAD_SOURCE_CONFLICT
    elif error.code.startswith("CAD_SOURCE_LOCK_"):
        status = CAD_SOURCE_LOCK_MISMATCH
    else:
        return False
    request = CadRequest(
        manufacturer=manufacturer,
        mpn=mpn,
        source="auto",
    )
    result.cad = None
    result.cad_data = None
    result.cad_discovery = CadDiscoveryResult(
        requested_source="auto",
        status=status,
        request=request,
        provenance=CadProvenance(
            retrieval_mode="validated-local-package-selection",
        ),
        action_required=CadActionRequired(
            code=status,
            detail=error.detail,
        ),
    )
    result.blocking_error = status
    merged = result.to_merged(overall_status=PARTIAL)
    arguments["_machine_merged"] = merged
    _log_metadata_diagnostics(merged, require_cad=arguments["require_cad"])
    return _write_requested_manifests(merged, arguments)


def _package_model_relative_path(arguments: dict[str, Any]) -> str | None:
    model_relative_path = arguments.get("project_relative_3d_path")
    if isinstance(model_relative_path, str):
        return model_relative_path
    relative_model_directory = relative_path_if_within(
        Path.cwd().resolve(),
        Path("{0}.3dshapes".format(arguments["output"])).resolve(),
    )
    return (
        relative_model_directory.as_posix()
        if relative_model_directory is not None
        else None
    )


def _run_cad_package_mode(arguments: dict[str, Any]) -> int:
    """Import one already downloaded package without provider/network access."""

    manufacturer = arguments.get("manufacturer")
    mpn = arguments.get("mpn")
    if not isinstance(manufacturer, str) or not isinstance(mpn, str):
        logging.error("Local CAD package identity was not validated")
        arguments["_machine_error_code"] = "CAD_IDENTITY_UNRESOLVED"
        return 1
    request = CadRequest(
        manufacturer=manufacturer,
        mpn=mpn,
        source=arguments["cad_source"],
    )
    try:
        result = ingest_cad_package(
            Path(arguments["cad_package"]),
            package_format=arguments["cad_package_format"],
            request=request,
            output_base=Path(arguments["output"]),
            overwrite=arguments["overwrite"],
            project_relative_model_path=_package_model_relative_path(arguments),
            evidence_path=(
                Path(arguments["cad_package_evidence"])
                if arguments.get("cad_package_evidence")
                else None
            ),
        )
    except CadPackageError as error:
        logging.error("%s", error)
        arguments["_machine_error_code"] = error.code
        return 1

    return _finish_ingested_package(arguments, request, result)


def _finish_ingested_package(
    arguments: dict[str, Any],
    request: CadRequest,
    result: CadPackageIngestResult,
    *,
    metadata_result: MetadataResolution | None = None,
) -> int:
    if metadata_result is not None:
        metadata_result.cad = result.cad
        metadata_result.cad_data = None
        metadata_result.cad_discovery = result.discovery
        metadata_result.blocking_error = None
        merged = metadata_result.to_merged(result.cad.verification_status)
    else:
        merged = MergedPart(
            identity=PartIdentity(
                manufacturer=request.manufacturer,
                mpn=request.mpn,
            ),
            cad=result.cad,
            cad_discovery=result.discovery,
            verification_status=result.cad.verification_status,
        )
    arguments["_machine_merged"] = merged
    if arguments.get("register_project_libraries") and not _register_project_libraries(
        arguments
    ):
        return 1

    _log_metadata_diagnostics(merged, require_cad=arguments["require_cad"])
    manifests_ok = _write_requested_manifests(merged, arguments)
    if arguments.get("show_conflicts"):
        _show_metadata_conflicts(merged)
    return 0 if manifests_ok else 1


def _configure_machine_logging() -> tuple[int, list[logging.Handler]]:
    """Route every log record to stderr for the duration of machine execution."""

    root_logger = logging.getLogger()
    previous_level = root_logger.level
    previous_handlers = list(root_logger.handlers)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_MachineLogFormatter(fmt="[{levelname}] {message}", style="{"))
    root_logger.handlers = [handler]
    return previous_level, previous_handlers


class _MachineLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_configured_secret_text(super().format(record))


def _restore_machine_logging(
    previous_level: int,
    previous_handlers: list[logging.Handler],
) -> None:
    root_logger = logging.getLogger()
    root_logger.handlers = previous_handlers
    root_logger.setLevel(previous_level)


def _main_machine_acquire(argv: list[str]) -> int:
    """Execute one non-interactive acquisition and emit JSON or JSON Lines."""

    request_id = uuid.uuid4().hex
    event_mode = "--json-events" in argv
    event_writer = MachineEventWriter(request_id) if event_mode else None
    if event_writer is not None:
        event_writer.emit("started", {"command": "acquire"})
    previous_level, previous_handlers = _configure_machine_logging()
    document: dict[str, Any]
    exit_code = 70
    try:
        parser = get_acquire_parser()
        if any(value in ("-h", "--help") for value in argv):
            if "--machine-json" in argv or event_mode:
                document = invalid_machine_result(
                    request_id,
                    code="HELP_UNAVAILABLE_IN_MACHINE_MODE",
                )
                exit_code = 2
            else:
                parser.print_help()
                return 0
        else:
            try:
                args = parser.parse_args(argv)
            except SystemExit:
                document = invalid_machine_result(request_id)
                exit_code = 2
            else:
                arguments = vars(args)
                logging.getLogger().setLevel(
                    logging.DEBUG if arguments["debug"] else logging.INFO
                )
                if not (arguments.get("machine_json") or arguments.get("json_events")):
                    logging.error("acquire requires --machine-json or --json-events")
                    document = invalid_machine_result(
                        request_id, code="MACHINE_OUTPUT_REQUIRED"
                    )
                    exit_code = 2
                elif not arguments["lcsc_id"] and not arguments.get("mpn"):
                    logging.error("at least one of --lcsc_id or --mpn is required")
                    document = invalid_machine_result(request_id)
                    exit_code = 2
                elif arguments.get(
                    "require_project_registration"
                ) and not arguments.get("register_project_libraries"):
                    logging.error(
                        "--require-project-registration requires "
                        "--register-project-libraries"
                    )
                    document = invalid_machine_result(
                        request_id,
                        code="PROJECT_REGISTRATION_NOT_REQUESTED",
                    )
                    exit_code = 2
                else:
                    required = list(
                        dict.fromkeys(
                            str(value).lower()
                            for value in arguments.get("require_provider", ())
                        )
                    )
                    selected = (
                        [
                            item.strip().lower()
                            for item in str(arguments["providers"]).split(",")
                            if item.strip()
                        ]
                        if arguments.get("providers")
                        else []
                    )
                    for provider in required:
                        if provider not in selected:
                            selected.append(provider)
                    if selected:
                        arguments["providers"] = ",".join(selected)
                    # Conflicts already appear in the result; a second stdout JSON
                    # document would violate the machine contract.
                    arguments["show_conflicts"] = False
                    if not valid_arguments(arguments):
                        document = invalid_machine_result(request_id)
                        exit_code = 2
                    else:
                        strict_selected = list(
                            arguments.get("required_provider_names", ())
                        )
                        arguments["machine_required_provider_names"] = list(
                            dict.fromkeys([*strict_selected, *required])
                        )
                        if arguments.get("dry_run"):
                            logging.error(
                                "acquire machine mode does not accept --dry-run"
                            )
                            document = invalid_machine_result(
                                request_id,
                                code="DRY_RUN_UNSUPPORTED",
                            )
                            exit_code = 2
                        else:
                            core_exit = _run_metadata_mode(arguments)
                            merged = arguments.get("_machine_merged")
                            document, exit_code = build_machine_result(
                                arguments,
                                merged if isinstance(merged, MergedPart) else None,
                                core_exit_code=core_exit,
                                request_id=request_id,
                            )
    except KeyboardInterrupt:
        logging.error("Machine acquisition interrupted")
        document = internal_machine_result(request_id, code="INTERRUPTED")
        exit_code = 70
    except Exception:
        logging.error("Unexpected machine acquisition failure")
        document = internal_machine_result(request_id)
        exit_code = 70
    finally:
        _restore_machine_logging(previous_level, previous_handlers)
    if event_writer is not None:
        emit_machine_result_events(event_writer, document)
    else:
        write_machine_json(document)
    return exit_code


def _main_headless(command: str, argv: list[str]) -> int:
    """Run one read-only discovery command and emit one bounded JSON result."""

    request_id = uuid.uuid4().hex
    previous_level, previous_handlers = _configure_machine_logging()
    document: dict[str, Any]
    exit_code = 70
    try:
        parser = get_headless_parser(command)
        if "--machine-json" in argv and any(
            value in ("-h", "--help") for value in argv
        ):
            raise HeadlessCommandError("HELP_UNAVAILABLE_IN_MACHINE_MODE", 2)
        try:
            arguments = vars(parser.parse_args(argv))
        except SystemExit as error:
            if error.code == 0:
                return 0
            document = error_result(
                command,
                request_id=request_id,
                code="INVALID_REQUEST",
                exit_code=2,
            )
            exit_code = 2
        else:
            if command == "capabilities":
                document = capabilities_result(request_id)
            elif command == "inspect-project":
                document = project_inspection_result(
                    _headless_path_argument(
                        arguments,
                        option_name="project",
                        positional_name="project_path",
                        missing_code="PROJECT_REQUIRED",
                    ),
                    request_id=request_id,
                )
            elif command == "plan-acquire":
                document = acquire_plan_result(arguments, request_id=request_id)
            elif command == "verify-artifacts":
                document = verify_artifacts_result(
                    _headless_path_argument(
                        arguments,
                        option_name="result",
                        positional_name="result_path",
                        missing_code="MACHINE_RESULT_REQUIRED",
                    ),
                    request_id=request_id,
                    project_root=arguments.get("project_root"),
                    output_root=arguments.get("output_root"),
                    cwd_root=arguments.get("cwd_root"),
                )
            else:
                raise RuntimeError("unsupported headless command")
            exit_code = int(document["exit_code"])
    except HeadlessCommandError as error:
        document = error_result(
            command,
            request_id=request_id,
            code=error.code,
            exit_code=error.exit_code,
        )
        exit_code = error.exit_code
    except KeyboardInterrupt:
        logging.error("Read-only command interrupted")
        document = error_result(
            command,
            request_id=request_id,
            code="INTERRUPTED",
            exit_code=70,
        )
        exit_code = 70
    except Exception:
        logging.error("Unexpected read-only command failure")
        document = error_result(
            command,
            request_id=request_id,
            code="INTERNAL_ERROR",
            exit_code=70,
        )
        exit_code = 70
    finally:
        _restore_machine_logging(previous_level, previous_handlers)
    write_machine_json(document)
    return exit_code


def _headless_path_argument(
    arguments: dict[str, Any],
    *,
    option_name: str,
    positional_name: str,
    missing_code: str,
) -> str:
    option = arguments.get(option_name)
    positional = arguments.get(positional_name)
    if option and positional:
        raise HeadlessCommandError("DUPLICATE_PATH_ARGUMENT", 2)
    selected = option or positional
    if not isinstance(selected, str) or not selected.strip():
        raise HeadlessCommandError(missing_code, 2)
    return selected


def main(argv: list[str] = sys.argv[1:]) -> int:
    if argv == ["--version"]:
        print(version_identity())
        return 0
    if argv and argv[0] == "acquire":
        return _main_machine_acquire(argv[1:])
    if argv and argv[0] in HEADLESS_COMMANDS:
        return _main_headless(argv[0], argv[1:])

    print(f"-- easyeda2kicad.py v{__version__} --")

    # cli interface
    parser = get_parser()
    try:
        args = parser.parse_args(argv)
        if not args.lcsc_id and not args.mpn:
            parser.error("at least one of --lcsc_id or --mpn is required")
    except SystemExit as err:
        return err.code if isinstance(err.code, int) else 1
    arguments = vars(args)

    log_level = logging.DEBUG if arguments["debug"] else logging.INFO
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(log_level)
        handler.setFormatter(
            logging.Formatter(fmt="[{levelname}] {message}", style="{")
        )
        root_logger.addHandler(handler)

    if not valid_arguments(arguments=arguments):
        return 1

    if arguments.get("dry_run"):
        return _run_project_registration_dry_run(arguments)

    if arguments["metadata_mode"]:
        return _run_metadata_mode(arguments)

    api = EasyedaApi(use_cache=arguments["use_cache"])
    had_errors = False

    for component_id in arguments["lcsc_id"]:
        if not _process_component(component_id, arguments, api):
            had_errors = True

    if (
        arguments.get("register_project_libraries")
        and not had_errors
        and not _register_project_libraries(arguments)
    ):
        had_errors = True

    return 1 if had_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
