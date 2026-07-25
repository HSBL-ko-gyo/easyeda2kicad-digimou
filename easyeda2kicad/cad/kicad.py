"""Minimal, fail-closed handling of native KiCad package artifacts."""

from __future__ import annotations

# Global imports
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

# Local imports
from easyeda2kicad.metadata.models import (
    CadRequest,
    normalize_manufacturer,
    normalize_mpn,
)

from .errors import CadPackageError

_QUOTED = r'"((?:\\.|[^"\\])*)"'
_PROPERTY_RE = re.compile(
    r"\(\s*property\s+" + _QUOTED + r"\s+" + _QUOTED,
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\(\s*number\s+" + _QUOTED, re.IGNORECASE)
_PAD_RE = re.compile(
    r"\(\s*pad\s+" + _QUOTED + r"\s+([^\s()]+)",
    re.IGNORECASE,
)
_MODEL_RE = re.compile(r"(\(\s*model\s+)" + _QUOTED, re.IGNORECASE)
_VERSION_RE = re.compile(r"\(\s*version\s+([0-9]+)\s*\)", re.IGNORECASE)

_MANUFACTURER_KEYS = frozenset(("manufacturer", "manufacturername", "mfr", "mfrname"))
_MPN_KEYS = frozenset(
    ("mpn", "manufacturerpartnumber", "manufacturerpartno", "mfrpartnumber")
)


@dataclass(frozen=True)
class FormSpan:
    head: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    root_head: str
    root_end: int
    forms: Tuple[FormSpan, ...]


@dataclass(frozen=True)
class SymbolSelection:
    name: str
    block: str
    properties: Dict[str, str]
    pin_numbers: Set[str]
    footprint_name: Optional[str]
    source_library: str


@dataclass(frozen=True)
class FootprintSelection:
    name: str
    text: str
    properties: Dict[str, str]
    pad_numbers: Set[str]


def select_exact_symbol(source_text: str, request: CadRequest) -> SymbolSelection:
    document = parse_document(source_text, "kicad_symbol_lib")
    candidates: List[SymbolSelection] = []
    mismatched_identity = False
    for form in document.forms:
        if form.head != "symbol":
            continue
        name = _form_quoted_name(form.text, "CAD_SYMBOL_INVALID")
        properties = extract_properties(form.text)
        manufacturer = _identity_property(properties, _MANUFACTURER_KEYS)
        mpn = _identity_property(properties, _MPN_KEYS)
        if manufacturer is None or mpn is None:
            continue
        if normalize_manufacturer(manufacturer) != normalize_manufacturer(
            request.manufacturer
        ) or normalize_mpn(mpn) != normalize_mpn(request.mpn):
            mismatched_identity = True
            continue
        pins = {_unescape(value).strip() for value in _NUMBER_RE.findall(form.text)}
        pins.discard("")
        if not pins:
            raise CadPackageError(
                "CAD_SYMBOL_INVALID", "selected symbol has no numbered pins"
            )
        footprint = _property_value(properties, "footprint")
        candidates.append(
            SymbolSelection(
                name=name,
                block=form.text,
                properties=properties,
                pin_numbers=pins,
                footprint_name=(
                    footprint.rsplit(":", 1)[-1].strip() if footprint else None
                ),
                source_library=_library_with_one_symbol(document, form),
            )
        )
    if len(candidates) > 1:
        raise CadPackageError(
            "CAD_SYMBOL_AMBIGUOUS",
            "multiple symbols prove the requested manufacturer and MPN",
        )
    if not candidates:
        code = (
            "CAD_IDENTITY_MISMATCH" if mismatched_identity else "CAD_IDENTITY_UNPROVEN"
        )
        detail = (
            "package symbol identity conflicts with the requested manufacturer or MPN"
            if mismatched_identity
            else "package symbol does not prove manufacturer and exact MPN"
        )
        raise CadPackageError(code, detail)
    return candidates[0]


def select_footprint(
    candidates: Sequence[Tuple[Path, str]],
    request: CadRequest,
    expected_name: Optional[str],
) -> FootprintSelection:
    parsed: List[FootprintSelection] = []
    identity_mismatch = False
    for path, text in candidates:
        try:
            document = parse_document(text, "footprint")
        except CadPackageError as error:
            raise CadPackageError(error.code, error.detail, path.name) from None
        name = _form_quoted_name(
            document.text[document.text.find("(") : document.root_end],
            "CAD_FOOTPRINT_INVALID",
        )
        if expected_name and name != expected_name:
            continue
        properties = extract_properties(document.text)
        manufacturer = _identity_property(properties, _MANUFACTURER_KEYS)
        mpn = _identity_property(properties, _MPN_KEYS)
        if manufacturer and (
            normalize_manufacturer(manufacturer)
            != normalize_manufacturer(request.manufacturer)
        ):
            identity_mismatch = True
            continue
        if mpn and normalize_mpn(mpn) != normalize_mpn(request.mpn):
            identity_mismatch = True
            continue
        pads = {
            _unescape(number).strip()
            for number, pad_type in _PAD_RE.findall(document.text)
            if pad_type.casefold() != "np_thru_hole"
        }
        pads.discard("")
        if not pads:
            raise CadPackageError(
                "CAD_FOOTPRINT_INVALID",
                "selected footprint has no numbered electrical pads",
                path.name,
            )
        parsed.append(
            FootprintSelection(
                name=name,
                text=document.text,
                properties=properties,
                pad_numbers=pads,
            )
        )
    if len(parsed) > 1:
        raise CadPackageError(
            "CAD_FOOTPRINT_AMBIGUOUS",
            "multiple footprints match the selected symbol",
        )
    if not parsed:
        if identity_mismatch:
            raise CadPackageError(
                "CAD_IDENTITY_MISMATCH",
                "footprint identity conflicts with the requested part",
            )
        raise CadPackageError(
            "CAD_FOOTPRINT_UNRESOLVED",
            "package does not contain one uniquely matching footprint",
        )
    return parsed[0]


def verify_pin_pad_identity(
    symbol: SymbolSelection,
    footprint: FootprintSelection,
) -> None:
    if symbol.pin_numbers != footprint.pad_numbers:
        raise CadPackageError(
            "CAD_PIN_PAD_MISMATCH",
            "symbol pins and electrical footprint pads do not match",
        )


def rewrite_footprint_model(text: str, portable_model_path: str) -> str:
    document = parse_document(text, "footprint")
    matches = list(_MODEL_RE.finditer(document.text))
    escaped_path = _escape(portable_model_path)
    if len(matches) > 1:
        raise CadPackageError(
            "CAD_3D_LINK_AMBIGUOUS",
            "footprint contains multiple 3D model links",
        )
    if matches:
        match = matches[0]
        value_start, value_end = match.span(2)
        return document.text[:value_start] + escaped_path + document.text[value_end:]
    insertion = (
        '\n  (model "{0}"\n'
        "    (offset (xyz 0 0 0))\n"
        "    (scale (xyz 1 1 1))\n"
        "    (rotate (xyz 0 0 0))\n"
        "  )\n".format(escaped_path)
    )
    return (
        document.text[: document.root_end - 1].rstrip()
        + insertion
        + ")"
        + document.text[document.root_end :]
    )


def rewrite_symbol_footprint(
    selection: SymbolSelection,
    request: CadRequest,
    library_nickname: str,
    footprint_name: str,
) -> SymbolSelection:
    """Retarget one selected symbol to its installed project-library footprint."""

    document = parse_document(selection.block, "symbol")
    matches: List[Tuple[FormSpan, re.Match[str]]] = []
    for form in document.forms:
        if form.head != "property":
            continue
        match = _PROPERTY_RE.search(form.text)
        if match is None or _unescape(match.group(1)).strip().casefold() != "footprint":
            continue
        matches.append((form, match))
    if len(matches) != 1:
        raise CadPackageError(
            "CAD_SYMBOL_FOOTPRINT_PROPERTY_INVALID",
            "selected symbol must contain exactly one Footprint property",
        )

    property_form, property_match = matches[0]
    value_start, value_end = property_match.span(2)
    installed_reference = "{0}:{1}".format(library_nickname, footprint_name)
    rewritten_property = (
        property_form.text[:value_start]
        + _escape(installed_reference)
        + property_form.text[value_end:]
    )
    rewritten_block = (
        selection.block[: property_form.start]
        + rewritten_property
        + selection.block[property_form.end :]
    )

    source = parse_document(selection.source_library, "kicad_symbol_lib")
    selected_forms = [
        form
        for form in source.forms
        if form.head == "symbol"
        and _form_quoted_name(form.text, "CAD_SYMBOL_INVALID") == selection.name
    ]
    if len(selected_forms) != 1:
        raise CadPackageError(
            "CAD_SYMBOL_AMBIGUOUS",
            "selected symbol cannot be retargeted uniquely",
        )
    selected_form = selected_forms[0]
    rewritten_library = (
        selection.source_library[: selected_form.start]
        + rewritten_block
        + selection.source_library[selected_form.end :]
    )
    rewritten = select_exact_symbol(rewritten_library, request)
    if rewritten.footprint_name != footprint_name:
        raise CadPackageError(
            "CAD_SYMBOL_FOOTPRINT_PROPERTY_INVALID",
            "rewritten symbol does not reference the selected footprint",
        )
    return rewritten


def merge_symbol_library(
    existing_text: Optional[str],
    selection: SymbolSelection,
    request: CadRequest,
    *,
    overwrite: bool,
) -> str:
    if existing_text is None:
        return selection.source_library

    target = parse_document(existing_text, "kicad_symbol_lib")
    source = parse_document(selection.source_library, "kicad_symbol_lib")
    target_version = _library_version(target)
    source_version = _library_version(source)
    if target_version < source_version:
        raise CadPackageError(
            "CAD_SYMBOL_VERSION_CONFLICT",
            "target symbol library is older than the package symbol format",
        )

    same_name: Optional[FormSpan] = None
    for form in target.forms:
        if form.head != "symbol":
            continue
        name = _form_quoted_name(form.text, "CAD_SYMBOL_INVALID")
        properties = extract_properties(form.text)
        existing_manufacturer = _identity_property(properties, _MANUFACTURER_KEYS)
        existing_mpn = _identity_property(properties, _MPN_KEYS)
        if existing_mpn and normalize_mpn(existing_mpn) == normalize_mpn(request.mpn):
            if name != selection.name:
                raise CadPackageError(
                    "CAD_SYMBOL_IDENTITY_COLLISION",
                    "target library already maps this MPN to another symbol",
                )
        if name != selection.name:
            continue
        if existing_manufacturer and (
            normalize_manufacturer(existing_manufacturer)
            != normalize_manufacturer(request.manufacturer)
        ):
            raise CadPackageError(
                "CAD_IDENTITY_MISMATCH",
                "existing symbol has a conflicting non-empty Manufacturer",
            )
        if existing_mpn and normalize_mpn(existing_mpn) != normalize_mpn(request.mpn):
            raise CadPackageError(
                "CAD_IDENTITY_MISMATCH",
                "existing symbol has a conflicting non-empty MPN",
            )
        same_name = form

    if same_name is not None:
        if _canonical_text(same_name.text) == _canonical_text(selection.block):
            return existing_text
        if not overwrite:
            raise CadPackageError(
                "CAD_SYMBOL_EXISTS",
                "symbol already exists; use --overwrite after identity review",
            )
        return (
            existing_text[: same_name.start]
            + selection.block
            + existing_text[same_name.end :]
        )

    insertion = "\n\n" + textwrap.indent(selection.block.strip(), "  ") + "\n"
    return (
        existing_text[: target.root_end - 1].rstrip()
        + insertion
        + ")"
        + existing_text[target.root_end :]
    )


def validate_model(path: Path, data: bytes) -> None:
    suffix = path.suffix.casefold()
    if suffix in (".step", ".stp"):
        stripped = data.strip()
        if not stripped.startswith(b"ISO-10303-21;") or not stripped.endswith(
            b"END-ISO-10303-21;"
        ):
            raise CadPackageError(
                "CAD_3D_INVALID", "STEP model has an invalid exchange-file envelope"
            )
        return
    if suffix == ".wrl":
        if not data.lstrip().startswith((b"#VRML V2.0", b"#VRML V1.0")):
            raise CadPackageError("CAD_3D_INVALID", "WRL model has an invalid header")
        return
    raise CadPackageError("CAD_3D_INVALID", "unsupported 3D model format")


def extract_properties(text: str) -> Dict[str, str]:
    properties: Dict[str, str] = {}
    for raw_name, raw_value in _PROPERTY_RE.findall(text):
        name = _unescape(raw_name)
        properties.setdefault(name, _unescape(raw_value))
    return properties


def parse_document(text: str, expected_root: str) -> ParsedDocument:
    if not isinstance(text, str) or not text.strip():
        raise CadPackageError("CAD_KICAD_MALFORMED", "KiCad artifact is empty")
    root_start = _skip_trivia(text, 0)
    if root_start >= len(text) or text[root_start] != "(":
        raise CadPackageError(
            "CAD_KICAD_MALFORMED", "KiCad artifact has no root S-expression"
        )
    root_head, head_end = _list_head(text, root_start)
    if root_head.casefold() != expected_root.casefold():
        raise CadPackageError(
            "CAD_KICAD_MALFORMED",
            "unexpected KiCad root expression",
        )
    root_end = _scan_list_end(text, root_start)
    if _skip_trivia(text, root_end) != len(text):
        raise CadPackageError(
            "CAD_KICAD_MALFORMED",
            "unexpected data follows the KiCad root expression",
        )

    forms: List[FormSpan] = []
    cursor = head_end
    while cursor < root_end - 1:
        cursor = _skip_trivia(text, cursor)
        if cursor >= root_end - 1:
            break
        if text[cursor] != "(":
            cursor += 1
            continue
        end = _scan_list_end(text, cursor)
        head, _unused = _list_head(text, cursor)
        forms.append(
            FormSpan(
                head=head.casefold(),
                start=cursor,
                end=end,
                text=text[cursor:end],
            )
        )
        cursor = end
    return ParsedDocument(
        text=text,
        root_head=root_head,
        root_end=root_end,
        forms=tuple(forms),
    )


def _library_with_one_symbol(
    document: ParsedDocument,
    selected: FormSpan,
) -> str:
    retained = [
        form.text
        for form in document.forms
        if form.head != "symbol" or form == selected
    ]
    body = "\n".join(textwrap.indent(form.strip(), "  ") for form in retained)
    return "({0}\n{1}\n)\n".format(document.root_head, body)


def _library_version(document: ParsedDocument) -> int:
    for form in document.forms:
        if form.head != "version":
            continue
        match = _VERSION_RE.fullmatch(form.text.strip())
        if match:
            return int(match.group(1))
    raise CadPackageError(
        "CAD_SYMBOL_INVALID", "symbol library has no numeric format version"
    )


def _property_value(properties: Dict[str, str], name: str) -> Optional[str]:
    requested = _property_key(name)
    for key, value in properties.items():
        if _property_key(key) == requested and value.strip():
            return value.strip()
    return None


def _identity_property(
    properties: Dict[str, str],
    accepted_keys: Set[str] | frozenset[str],
) -> Optional[str]:
    for key, value in properties.items():
        if _property_key(key) in accepted_keys and value.strip():
            return value.strip()
    return None


def _property_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _form_quoted_name(form: str, code: str) -> str:
    start = form.find("(")
    _head, cursor = _list_head(form, start)
    cursor = _skip_trivia(form, cursor)
    if cursor >= len(form) or form[cursor] != '"':
        raise CadPackageError(code, "KiCad expression has no quoted name")
    value, _end = _read_quoted(form, cursor)
    if not value.strip():
        raise CadPackageError(code, "KiCad expression name is empty")
    return value


def _list_head(text: str, start: int) -> Tuple[str, int]:
    cursor = start + 1
    cursor = _skip_trivia(text, cursor)
    head_start = cursor
    while cursor < len(text) and text[cursor] not in " \t\r\n()":
        cursor += 1
    if cursor == head_start:
        raise CadPackageError("CAD_KICAD_MALFORMED", "S-expression has no list head")
    return text[head_start:cursor], cursor


def _scan_list_end(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    in_comment = False
    for cursor in range(start, len(text)):
        character = text[cursor]
        if in_comment:
            if character in "\r\n":
                in_comment = False
            continue
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == ";":
            in_comment = True
        elif character == '"':
            in_string = True
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return cursor + 1
            if depth < 0:
                break
    raise CadPackageError("CAD_KICAD_MALFORMED", "unbalanced KiCad S-expression")


def _skip_trivia(text: str, start: int) -> int:
    cursor = start
    while cursor < len(text):
        if text[cursor].isspace():
            cursor += 1
            continue
        if text[cursor] == ";":
            newline = text.find("\n", cursor)
            return len(text) if newline < 0 else _skip_trivia(text, newline + 1)
        break
    return cursor


def _read_quoted(text: str, start: int) -> Tuple[str, int]:
    cursor = start + 1
    raw: List[str] = []
    escaped = False
    while cursor < len(text):
        character = text[cursor]
        if escaped:
            raw.append("\\")
            raw.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            return _unescape("".join(raw)), cursor + 1
        else:
            raw.append(character)
        cursor += 1
    raise CadPackageError("CAD_KICAD_MALFORMED", "unterminated KiCad string")


def _unescape(value: str) -> str:
    result: List[str] = []
    cursor = 0
    replacements = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
    while cursor < len(value):
        if value[cursor] == "\\" and cursor + 1 < len(value):
            cursor += 1
            result.append(replacements.get(value[cursor], value[cursor]))
        else:
            result.append(value[cursor])
        cursor += 1
    return "".join(result)


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def _canonical_text(value: str) -> str:
    return "\n".join(
        line.strip() for line in value.replace("\r\n", "\n").strip().splitlines()
    )


__all__ = [
    "FootprintSelection",
    "SymbolSelection",
    "extract_properties",
    "merge_symbol_library",
    "parse_document",
    "rewrite_footprint_model",
    "rewrite_symbol_footprint",
    "select_exact_symbol",
    "select_footprint",
    "validate_model",
    "verify_pin_pad_identity",
]
