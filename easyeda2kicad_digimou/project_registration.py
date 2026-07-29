"""Fail-closed project-local KiCad library table registration."""

from __future__ import annotations

# Global imports
import codecs
import hashlib
import os
import posixpath
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# Local imports
from easyeda2kicad_digimou.cad.errors import CadPackageError
from easyeda2kicad_digimou.cad.kicad import FormSpan, ParsedDocument, parse_document


class ProjectRegistrationError(RuntimeError):
    """A typed project-registration failure without table payload contents."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__("{0}: {1}".format(code, detail))


@dataclass(frozen=True)
class ProjectContext:
    project_file: Path
    project_root: Path


@dataclass(frozen=True)
class LibraryEntry:
    nickname: str
    uri: str


@dataclass(frozen=True)
class LibraryTableUpdate:
    path: Path
    root_name: str
    entry: LibraryEntry
    action: str
    expected_sha256: Optional[str]
    content: bytes


@dataclass(frozen=True)
class ProjectRegistrationPlan:
    context: ProjectContext
    output_base: Path
    updates: Tuple[LibraryTableUpdate, ...]

    @property
    def changed_paths(self) -> Tuple[Path, ...]:
        return tuple(
            update.path for update in self.updates if update.action != "unchanged"
        )


@dataclass(frozen=True)
class ProjectRegistrationResult:
    changed_paths: Tuple[Path, ...]


@dataclass(frozen=True)
class ProjectLibraryTableInspection:
    path: Path
    root_name: str
    exists: bool
    sha256: Optional[str]
    entries: Tuple[LibraryEntry, ...]


@dataclass(frozen=True)
class ProjectInspection:
    context: ProjectContext
    tables: Tuple[ProjectLibraryTableInspection, ...]


def resolve_project(project: str | Path) -> ProjectContext:
    """Resolve an explicit project file or an unambiguous project directory."""

    requested = Path(project).expanduser()
    if not requested.exists():
        raise ProjectRegistrationError(
            "PROJECT_NOT_FOUND",
            "the requested KiCad project path does not exist",
        )
    if requested.is_file():
        if requested.suffix.casefold() != ".kicad_pro":
            raise ProjectRegistrationError(
                "PROJECT_FILE_INVALID",
                "--project file must use the .kicad_pro extension",
            )
        project_file = requested.resolve()
    elif requested.is_dir():
        candidates = sorted(
            (
                candidate.resolve()
                for candidate in requested.iterdir()
                if candidate.is_file() and candidate.suffix.casefold() == ".kicad_pro"
            ),
            key=lambda candidate: candidate.name.casefold(),
        )
        if not candidates:
            raise ProjectRegistrationError(
                "PROJECT_NOT_FOUND",
                "project directory contains no .kicad_pro file",
            )
        if len(candidates) != 1:
            raise ProjectRegistrationError(
                "PROJECT_AMBIGUOUS",
                "project directory contains multiple .kicad_pro files",
            )
        project_file = candidates[0]
    else:
        raise ProjectRegistrationError(
            "PROJECT_PATH_INVALID",
            "the requested project path is not a regular file or directory",
        )
    return ProjectContext(
        project_file=project_file,
        project_root=project_file.parent,
    )


def inspect_project(project: str | Path) -> ProjectInspection:
    """Inspect project-local library tables without preparing or writing changes."""

    context = resolve_project(project)
    tables = (
        _inspect_table(context.project_root / "sym-lib-table", "sym_lib_table"),
        _inspect_table(context.project_root / "fp-lib-table", "fp_lib_table"),
    )
    return ProjectInspection(context=context, tables=tables)


def project_relative_path(context: ProjectContext, path: str | Path) -> str:
    """Return one portable project-relative path or fail when it escapes."""

    resolved = Path(path).expanduser().resolve()
    try:
        relative = resolved.relative_to(context.project_root)
    except ValueError:
        raise ProjectRegistrationError(
            "PROJECT_OUTPUT_OUTSIDE_ROOT",
            "library output must remain within the selected project directory",
        ) from None
    return relative.as_posix()


def plan_project_registration(
    project: str | Path,
    output_base: str | Path,
    *,
    require_artifacts: bool,
) -> ProjectRegistrationPlan:
    """Validate project tables and prepare changes without writing anything."""

    context = resolve_project(project)
    resolved_output = Path(output_base).expanduser().resolve()
    nickname = _safe_nickname(resolved_output.name)
    symbol_path = Path("{0}.kicad_sym".format(resolved_output))
    footprint_path = Path("{0}.pretty".format(resolved_output))
    symbol_relative = project_relative_path(context, symbol_path)
    footprint_relative = project_relative_path(context, footprint_path)

    if require_artifacts:
        _validate_generated_artifacts(symbol_path, footprint_path)

    updates = (
        _plan_table_update(
            context.project_root / "sym-lib-table",
            "sym_lib_table",
            LibraryEntry(
                nickname=nickname,
                uri="${{KIPRJMOD}}/{0}".format(symbol_relative),
            ),
        ),
        _plan_table_update(
            context.project_root / "fp-lib-table",
            "fp_lib_table",
            LibraryEntry(
                nickname=nickname,
                uri="${{KIPRJMOD}}/{0}".format(footprint_relative),
            ),
        ),
    )
    return ProjectRegistrationPlan(
        context=context,
        output_base=resolved_output,
        updates=updates,
    )


def apply_project_registration(
    plan: ProjectRegistrationPlan,
) -> ProjectRegistrationResult:
    """Apply all changed tables with pre-commit hash checks and rollback."""

    changes = [update for update in plan.updates if update.action != "unchanged"]
    if not changes:
        return ProjectRegistrationResult(changed_paths=())

    staged: List[Tuple[Path, LibraryTableUpdate]] = []
    try:
        for update in changes:
            staged.append((_write_temp_sibling(update.path, update.content), update))
        for _staged_path, update in staged:
            if _file_sha256(update.path) != update.expected_sha256:
                raise ProjectRegistrationError(
                    "PROJECT_TABLE_CONCURRENT_MODIFICATION",
                    "a project library table changed before registration commit",
                )
        _commit_staged_tables(staged)
    finally:
        for staged_path, _update in staged:
            _unlink_if_present(staged_path)
    return ProjectRegistrationResult(
        changed_paths=tuple(update.path for update in changes)
    )


def _plan_table_update(
    path: Path,
    root_name: str,
    entry: LibraryEntry,
) -> LibraryTableUpdate:
    if path.is_symlink():
        raise ProjectRegistrationError(
            "PROJECT_TABLE_LINK_REJECTED",
            "project library tables must not be symbolic links",
        )
    if not path.exists():
        content = _new_table(root_name, entry).encode("utf-8")
        return LibraryTableUpdate(
            path=path,
            root_name=root_name,
            entry=entry,
            action="create",
            expected_sha256=None,
            content=content,
        )
    if not path.is_file():
        raise ProjectRegistrationError(
            "PROJECT_TABLE_INVALID",
            "project library table path is not a regular file",
        )
    try:
        original = path.read_bytes()
    except OSError:
        raise ProjectRegistrationError(
            "PROJECT_TABLE_READ_FAILED",
            "project library table could not be read",
        ) from None
    text, has_bom = _decode_table(original)
    document = _parse_table(text, root_name)
    _validate_table_version(document)
    existing_entries = _library_entries(document.forms)
    _validate_existing_entries(existing_entries)
    matching = _classify_entry(existing_entries, entry)
    if matching == "unchanged":
        return LibraryTableUpdate(
            path=path,
            root_name=root_name,
            entry=entry,
            action="unchanged",
            expected_sha256=_sha256_bytes(original),
            content=original,
        )
    newline = "\r\n" if "\r\n" in text else "\n"
    insertion = newline + _format_entry(entry)
    updated_text = (
        text[: document.root_end - 1].rstrip(" \t\r\n")
        + insertion
        + newline
        + ")"
        + text[document.root_end :]
    )
    encoded = updated_text.encode("utf-8")
    if has_bom:
        encoded = codecs.BOM_UTF8 + encoded
    return LibraryTableUpdate(
        path=path,
        root_name=root_name,
        entry=entry,
        action="update",
        expected_sha256=_sha256_bytes(original),
        content=encoded,
    )


def _inspect_table(path: Path, root_name: str) -> ProjectLibraryTableInspection:
    if path.is_symlink():
        raise ProjectRegistrationError(
            "PROJECT_TABLE_LINK_REJECTED",
            "project library tables must not be symbolic links",
        )
    if not path.exists():
        return ProjectLibraryTableInspection(
            path=path,
            root_name=root_name,
            exists=False,
            sha256=None,
            entries=(),
        )
    if not path.is_file():
        raise ProjectRegistrationError(
            "PROJECT_TABLE_INVALID",
            "project library table path is not a regular file",
        )
    try:
        original = path.read_bytes()
    except OSError:
        raise ProjectRegistrationError(
            "PROJECT_TABLE_READ_FAILED",
            "project library table could not be read",
        ) from None
    text, _has_bom = _decode_table(original)
    document = _parse_table(text, root_name)
    _validate_table_version(document)
    entries = tuple(_library_entries(document.forms))
    _validate_existing_entries(entries)
    return ProjectLibraryTableInspection(
        path=path,
        root_name=root_name,
        exists=True,
        sha256=_sha256_bytes(original),
        entries=entries,
    )


def _parse_table(text: str, root_name: str) -> ParsedDocument:
    try:
        return parse_document(text, root_name)
    except CadPackageError:
        raise ProjectRegistrationError(
            "PROJECT_TABLE_MALFORMED",
            "project library table is not a valid {0} S-expression".format(root_name),
        ) from None


def _library_entries(forms: Sequence[FormSpan]) -> List[LibraryEntry]:
    entries: List[LibraryEntry] = []
    for form in forms:
        if form.head != "lib":
            continue
        try:
            document = parse_document(form.text, "lib")
        except CadPackageError:
            raise ProjectRegistrationError(
                "PROJECT_TABLE_MALFORMED",
                "project library table contains a malformed lib entry",
            ) from None
        names = [
            _single_quoted_field(child, "name")
            for child in document.forms
            if child.head == "name"
        ]
        uris = [
            _single_quoted_field(child, "uri")
            for child in document.forms
            if child.head == "uri"
        ]
        if len(names) != 1 or len(uris) != 1:
            raise ProjectRegistrationError(
                "PROJECT_TABLE_MALFORMED",
                "each project lib entry must contain one name and one URI",
            )
        entries.append(LibraryEntry(nickname=names[0], uri=uris[0]))
    return entries


def _validate_table_version(document: ParsedDocument) -> None:
    versions = [form for form in document.forms if form.head == "version"]
    if len(versions) != 1:
        raise ProjectRegistrationError(
            "PROJECT_TABLE_MALFORMED",
            "project library table must contain exactly one version field",
        )
    version_text = versions[0].text
    match = re.fullmatch(r"\(\s*version\s+([0-9]+)\s*\)", version_text, re.IGNORECASE)
    if match is None:
        raise ProjectRegistrationError(
            "PROJECT_TABLE_MALFORMED",
            "project library table version must be an integer",
        )


def _single_quoted_field(form: FormSpan, expected_head: str) -> str:
    text = form.text
    cursor = 1
    cursor = _skip_space(text, cursor)
    head_start = cursor
    while cursor < len(text) and text[cursor] not in " \t\r\n()":
        cursor += 1
    if text[head_start:cursor].casefold() != expected_head.casefold():
        raise ProjectRegistrationError(
            "PROJECT_TABLE_MALFORMED",
            "project lib entry contains an invalid field",
        )
    cursor = _skip_space(text, cursor)
    if cursor >= len(text) or text[cursor] != '"':
        raise ProjectRegistrationError(
            "PROJECT_TABLE_MALFORMED",
            "project lib name and URI fields must be quoted strings",
        )
    value, cursor = _read_quoted(text, cursor)
    cursor = _skip_space(text, cursor)
    if cursor != len(text) - 1 or text[cursor] != ")":
        raise ProjectRegistrationError(
            "PROJECT_TABLE_MALFORMED",
            "project lib name and URI fields must contain one string",
        )
    return value


def _validate_existing_entries(entries: Sequence[LibraryEntry]) -> None:
    for index, left in enumerate(entries):
        for right in entries[index + 1 :]:
            same_name = _normalize_nickname(left.nickname) == _normalize_nickname(
                right.nickname
            )
            same_uri = _normalize_uri(left.uri) == _normalize_uri(right.uri)
            if same_name or same_uri:
                raise ProjectRegistrationError(
                    "PROJECT_LIBRARY_COLLISION",
                    "existing project library entries contain a nickname or URI collision",
                )


def _classify_entry(
    existing_entries: Sequence[LibraryEntry],
    requested: LibraryEntry,
) -> str:
    requested_name = _normalize_nickname(requested.nickname)
    requested_uri = _normalize_uri(requested.uri)
    for existing in existing_entries:
        same_name = _normalize_nickname(existing.nickname) == requested_name
        same_uri = _normalize_uri(existing.uri) == requested_uri
        if same_name and same_uri:
            return "unchanged"
        if same_name:
            raise ProjectRegistrationError(
                "PROJECT_LIBRARY_NICKNAME_CONFLICT",
                "library nickname is already registered with another URI",
            )
        if same_uri:
            raise ProjectRegistrationError(
                "PROJECT_LIBRARY_URI_CONFLICT",
                "library URI is already registered with another nickname",
            )
    return "update"


def _validate_generated_artifacts(symbol_path: Path, footprint_path: Path) -> None:
    if (
        symbol_path.is_symlink()
        or not symbol_path.is_file()
        or symbol_path.stat().st_size == 0
    ):
        raise ProjectRegistrationError(
            "PROJECT_SYMBOL_LIBRARY_MISSING",
            "generated symbol library is missing or invalid",
        )
    if footprint_path.is_symlink() or not footprint_path.is_dir():
        raise ProjectRegistrationError(
            "PROJECT_FOOTPRINT_LIBRARY_MISSING",
            "generated footprint library is missing or invalid",
        )
    if not any(
        path.is_file() and not path.is_symlink()
        for path in footprint_path.glob("*.kicad_mod")
    ):
        raise ProjectRegistrationError(
            "PROJECT_FOOTPRINT_LIBRARY_EMPTY",
            "generated footprint library contains no native KiCad footprint",
        )


def _commit_staged_tables(
    staged: Sequence[Tuple[Path, LibraryTableUpdate]],
) -> None:
    installed: List[Tuple[Path, Optional[Path]]] = []
    pending_backup: Optional[Path] = None
    try:
        for staged_path, update in staged:
            target = update.path
            current_content = _read_table_for_commit(update)
            if current_content is not None:
                pending_backup = _write_temp_sibling(
                    target,
                    current_content,
                    suffix=".bak",
                )
                if _file_sha256(target) != update.expected_sha256:
                    raise ProjectRegistrationError(
                        "PROJECT_TABLE_CONCURRENT_MODIFICATION",
                        "a project library table changed immediately before registration",
                    )
            os.replace(staged_path, target)
            installed.append((target, pending_backup))
            pending_backup = None
    except (OSError, ProjectRegistrationError) as error:
        rollback_failed = False
        for target, backup in reversed(installed):
            try:
                if backup is None:
                    _unlink_if_present(target)
                else:
                    os.replace(backup, target)
            except OSError:
                rollback_failed = True
        if pending_backup is not None:
            try:
                _unlink_if_present(pending_backup)
            except OSError:
                rollback_failed = True
        if rollback_failed:
            raise ProjectRegistrationError(
                "PROJECT_REGISTRATION_ROLLBACK_FAILED",
                "project table update failed and rollback was incomplete",
            ) from None
        if isinstance(error, ProjectRegistrationError):
            raise
        raise ProjectRegistrationError(
            "PROJECT_REGISTRATION_WRITE_FAILED",
            "project table update failed and was rolled back",
        ) from None
    for _target, backup in installed:
        if backup is not None:
            try:
                _unlink_if_present(backup)
            except OSError:
                raise ProjectRegistrationError(
                    "PROJECT_REGISTRATION_CLEANUP_FAILED",
                    "project tables were updated but a recovery file could not be removed",
                ) from None


def _write_temp_sibling(
    target: Path,
    content: bytes,
    *,
    suffix: str = ".tmp",
) -> Path:
    descriptor: Optional[int] = None
    temporary: Optional[str] = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".{0}.".format(target.name),
            suffix=suffix,
            dir=target.parent,
        )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return Path(temporary)
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            _unlink_if_present(Path(temporary))
        raise ProjectRegistrationError(
            "PROJECT_REGISTRATION_WRITE_FAILED",
            "temporary project table could not be written",
        ) from None


def _read_table_for_commit(update: LibraryTableUpdate) -> Optional[bytes]:
    path = update.path
    if not path.exists():
        current: Optional[bytes] = None
    elif path.is_symlink() or not path.is_file():
        raise ProjectRegistrationError(
            "PROJECT_TABLE_INVALID",
            "project library table path changed to an unsafe filesystem type",
        )
    else:
        try:
            current = path.read_bytes()
        except OSError:
            raise ProjectRegistrationError(
                "PROJECT_TABLE_READ_FAILED",
                "project library table could not be re-read",
            ) from None
    current_hash = _sha256_bytes(current) if current is not None else None
    if current_hash != update.expected_sha256:
        raise ProjectRegistrationError(
            "PROJECT_TABLE_CONCURRENT_MODIFICATION",
            "a project library table changed before registration commit",
        )
    return current


def _new_table(root_name: str, entry: LibraryEntry) -> str:
    return "({0}\n  (version 7)\n{1}\n)\n".format(
        root_name,
        _format_entry(entry),
    )


def _format_entry(entry: LibraryEntry) -> str:
    return (
        '  (lib (name "{0}")(type "KiCad")(uri "{1}")(options "")(descr ""))'
    ).format(_escape(entry.nickname), _escape(entry.uri))


def _decode_table(content: bytes) -> Tuple[str, bool]:
    has_bom = content.startswith(codecs.BOM_UTF8)
    payload = content[len(codecs.BOM_UTF8) :] if has_bom else content
    try:
        return payload.decode("utf-8"), has_bom
    except UnicodeDecodeError:
        raise ProjectRegistrationError(
            "PROJECT_TABLE_ENCODING_INVALID",
            "project library tables must be UTF-8",
        ) from None


def _safe_nickname(value: str) -> str:
    nickname = value.strip()
    if (
        not nickname
        or nickname in (".", "..")
        or any(ord(character) < 32 or ord(character) == 127 for character in nickname)
    ):
        raise ProjectRegistrationError(
            "PROJECT_LIBRARY_NICKNAME_INVALID",
            "output stem cannot be used as a KiCad library nickname",
        )
    return nickname


def _normalize_nickname(value: str) -> str:
    return value.strip().casefold()


def _normalize_uri(value: str) -> str:
    normalized = posixpath.normpath(value.strip().replace("\\", "/"))
    return normalized.casefold() if os.name == "nt" else normalized


def _read_quoted(text: str, start: int) -> Tuple[str, int]:
    raw: List[str] = []
    cursor = start + 1
    escaped = False
    while cursor < len(text):
        character = text[cursor]
        if escaped:
            raw.append({"n": "\n", "r": "\r", "t": "\t"}.get(character, character))
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            return "".join(raw), cursor + 1
        else:
            raw.append(character)
        cursor += 1
    raise ProjectRegistrationError(
        "PROJECT_TABLE_MALFORMED",
        "project library table contains an unterminated string",
    )


def _skip_space(text: str, start: int) -> int:
    cursor = start
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return cursor


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def _file_sha256(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ProjectRegistrationError(
            "PROJECT_TABLE_INVALID",
            "project library table path changed to an unsafe filesystem type",
        )
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        raise ProjectRegistrationError(
            "PROJECT_TABLE_READ_FAILED",
            "project library table could not be re-read",
        ) from None


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _unlink_if_present(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except TypeError:  # pragma: no cover - Python 3.7 compatibility
        if path.exists():
            path.unlink()


__all__ = [
    "LibraryEntry",
    "LibraryTableUpdate",
    "ProjectContext",
    "ProjectInspection",
    "ProjectLibraryTableInspection",
    "ProjectRegistrationError",
    "ProjectRegistrationPlan",
    "ProjectRegistrationResult",
    "apply_project_registration",
    "inspect_project",
    "plan_project_registration",
    "project_relative_path",
    "resolve_project",
]
