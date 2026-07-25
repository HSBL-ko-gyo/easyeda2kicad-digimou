from __future__ import annotations

# Global imports
import argparse
import ctypes
import json
import logging
import re
import sys
import unicodedata
from pathlib import Path, PurePath
from typing import Any, TextIO

# Local imports
from ._version import __version__
from .cad import CAD_PACKAGE_FORMATS, CadPackageError, ingest_cad_package
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
from .metadata.cache import strip_secrets
from .metadata.manifest import write_csv_manifest, write_json_manifest
from .metadata.merge import (
    CAD_NOT_FOUND,
    CAD_PIN_PAD_MISMATCH,
    PARTIAL,
    VERIFIED,
)
from .metadata.models import (
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
        description=(
            "A Python script that convert any electronic components from LCSC or"
            " EasyEDA to a Kicad library"
        )
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


def is_metadata_mode(arguments: dict[str, Any]) -> bool:
    """Return whether any additive metadata behavior was explicitly requested."""
    return bool(
        arguments.get("mpn")
        or arguments.get("manufacturer")
        or arguments.get("providers") is not None
        or arguments.get("cad_source", "easyeda") != "easyeda"
        or arguments.get("cad_package")
        or arguments.get("cad_package_format", "auto") != "auto"
        or arguments.get("datasheet_link") is not None
        or arguments.get("manifest_json")
        or arguments.get("manifest_csv")
        or arguments.get("require_cad")
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


def _manifest_collides_with_selected_cad_output(arguments: dict[str, Any]) -> bool:
    """Return whether a manifest file would occupy a selected output ancestor."""

    output = arguments.get("output")
    if not output:
        return False

    selected_outputs: list[tuple[str, Path, bool]] = []
    imports_package = bool(arguments.get("cad_package"))
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
    for option_name in ("manifest_json", "manifest_csv"):
        manifest = arguments.get(option_name)
        if not manifest:
            continue
        resolved_manifest = Path(manifest).resolve()
        for description, resolved_output, output_is_file in resolved_outputs:
            if _same_or_descendant(resolved_output, resolved_manifest) or (
                output_is_file
                and _same_or_descendant(resolved_manifest, resolved_output)
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
    elif arguments.get("cad_package_format", "auto") != "auto":
        logging.error("--cad-package-format requires --cad-package")
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

    if not any(
        [
            arguments["symbol"],
            arguments["footprint"],
            arguments["3d"],
            arguments["svg"],
            arguments.get("manifest_json"),
            arguments.get("manifest_csv"),
            arguments.get("require_cad"),
            arguments.get("show_conflicts"),
            arguments.get("cad_package"),
        ]
    ):
        logging.error(
            "Missing action arguments\n"
            "  easyeda2kicad --lcsc_id=C2040 --footprint\n"
            "  easyeda2kicad --lcsc_id=C2040 --symbol\n"
            "  easyeda2kicad --lcsc_id=C2040 --svg"
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
            " using --project-relative option\nFor example: easyeda2kicad"
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

    if arguments["project_relative"]:
        project_root = Path.cwd().resolve()
        model_directory = Path(f"{arguments['output']}.3dshapes").resolve()
        relative_model_directory = relative_path_if_within(
            project_root, model_directory
        )
        if relative_model_directory is None:
            logging.error(
                "--project-relative output must remain within the current project directory"
            )
            return False
        arguments["project_relative_3d_path"] = relative_model_directory.as_posix()

    if metadata_mode and _manifest_collides_with_selected_cad_output(arguments):
        return False

    if create_default_folder:
        base_folder.mkdir(parents=True, exist_ok=True)
    elif not base_folder.is_dir():
        logging.error(f"Can't find the folder : {base_folder}")
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
    _write_console_json(
        {
            "conflicts": model_to_dict(merged.conflicts),
            "provider_errors": merged.provider_errors,
            "provider_diagnostics": model_to_dict(merged.provider_diagnostics),
        }
    )


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
        logging.warning(
            "Metadata provider %s: %s%s%s",
            provider,
            diagnostic,
            operation,
            status,
        )

    if merged.cad_discovery is not None:
        logging.warning(
            "CAD source %s: %s",
            merged.cad_discovery.requested_source,
            merged.cad_discovery.status,
        )

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
        )
    except MetadataServiceError as error:
        logging.error("%s", error)
        return 1

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

    merged = result.to_merged(verification_status)
    export_failed = False

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
                merged = result.to_merged(overall_status=PARTIAL)
            else:
                _update_cad_artifact_paths(result, arguments, symbol, footprint)
                merged = result.to_merged(VERIFIED)

    _log_metadata_diagnostics(merged, require_cad=arguments["require_cad"])
    manifests_ok = _write_requested_manifests(merged, arguments)
    if arguments.get("show_conflicts"):
        _show_metadata_conflicts(merged)

    if not manifests_ok or export_failed or result.blocking_error:
        return 1
    if merged.verification_status == CAD_PIN_PAD_MISMATCH:
        return 1
    if merged.verification_status == CAD_NOT_FOUND and arguments["require_cad"]:
        return 1
    return 0


def _run_cad_package_mode(arguments: dict[str, Any]) -> int:
    """Import one already downloaded package without provider/network access."""

    manufacturer = arguments.get("manufacturer")
    mpn = arguments.get("mpn")
    if not isinstance(manufacturer, str) or not isinstance(mpn, str):
        logging.error("Local CAD package identity was not validated")
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
        )
    except CadPackageError as error:
        logging.error("%s", error)
        return 1

    merged = MergedPart(
        identity=PartIdentity(
            manufacturer=request.manufacturer,
            mpn=request.mpn,
        ),
        cad=result.cad,
        cad_discovery=result.discovery,
        verification_status=result.cad.verification_status,
    )
    _log_metadata_diagnostics(merged, require_cad=arguments["require_cad"])
    manifests_ok = _write_requested_manifests(merged, arguments)
    if arguments.get("show_conflicts"):
        _show_metadata_conflicts(merged)
    return 0 if manifests_ok else 1


def main(argv: list[str] = sys.argv[1:]) -> int:
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

    if arguments["metadata_mode"]:
        return _run_metadata_mode(arguments)

    api = EasyedaApi(use_cache=arguments["use_cache"])
    had_errors = False

    for component_id in arguments["lcsc_id"]:
        if not _process_component(component_id, arguments, api):
            had_errors = True

    return 1 if had_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
