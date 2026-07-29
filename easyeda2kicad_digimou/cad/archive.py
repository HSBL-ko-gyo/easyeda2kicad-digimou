"""Defensive ZIP inspection and extraction for untrusted CAD packages."""

from __future__ import annotations

# Global imports
import os
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, IO, List, Set

# Local imports
from .errors import CadPackageError

_NESTED_ARCHIVE_SUFFIXES = (
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".gz",
    ".bz2",
    ".xz",
)
_WINDOWS_DEVICE_RE = re.compile(r"(?i)^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$")


@dataclass(frozen=True)
class ArchiveLimits:
    max_entries: int = 4096
    max_total_size: int = 512 * 1024 * 1024
    max_file_size: int = 256 * 1024 * 1024
    max_compression_ratio: int = 200


DEFAULT_ARCHIVE_LIMITS = ArchiveLimits()


def extract_zip_safely(
    archive_path: Path,
    destination: Path,
    *,
    limits: ArchiveLimits = DEFAULT_ARCHIVE_LIMITS,
) -> List[Path]:
    """Inspect every entry, then stream regular files into an empty directory."""

    if not archive_path.is_file():
        raise CadPackageError("CAD_PACKAGE_NOT_FOUND", "package path is not a file")
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise CadPackageError(
            "CAD_EXTRACTION_TARGET_NOT_EMPTY",
            "package extraction target must be empty",
        )

    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        raise CadPackageError(
            "CAD_ARCHIVE_INVALID", "package is not a valid ZIP archive"
        ) from None

    extracted: List[Path] = []
    with archive:
        entries = archive.infolist()
        if len(entries) > limits.max_entries:
            raise CadPackageError(
                "CAD_ARCHIVE_TOO_MANY_ENTRIES",
                "archive exceeds the 4096-entry limit",
            )

        seen_exact: Set[str] = set()
        seen_casefolded: Set[str] = set()
        declared_total = 0
        validated: List[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        for info in entries:
            relative = _safe_member_path(info.filename)
            canonical = relative.as_posix().rstrip("/")
            casefolded = canonical.casefold()
            if canonical in seen_exact:
                raise CadPackageError(
                    "CAD_ARCHIVE_DUPLICATE_PATH",
                    "archive contains a duplicate path",
                    canonical,
                )
            if casefolded in seen_casefolded:
                raise CadPackageError(
                    "CAD_ARCHIVE_CASE_COLLISION",
                    "archive paths collide on case-insensitive filesystems",
                    canonical,
                )
            seen_exact.add(canonical)
            seen_casefolded.add(casefolded)

            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise CadPackageError(
                    "CAD_ARCHIVE_LINK_REJECTED",
                    "symbolic links are not permitted",
                    canonical,
                )
            file_type = stat.S_IFMT(mode)
            if file_type and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise CadPackageError(
                    "CAD_ARCHIVE_SPECIAL_FILE_REJECTED",
                    "special filesystem entries are not permitted",
                    canonical,
                )
            if info.flag_bits & 0x1:
                raise CadPackageError(
                    "CAD_ARCHIVE_ENCRYPTED",
                    "encrypted archive entries are not supported",
                    canonical,
                )
            if not info.is_dir() and _is_nested_archive(canonical):
                raise CadPackageError(
                    "CAD_NESTED_ARCHIVE_REJECTED",
                    "nested archives are not permitted",
                    canonical,
                )
            if info.file_size > limits.max_file_size:
                raise CadPackageError(
                    "CAD_ARCHIVE_FILE_TOO_LARGE",
                    "archive entry exceeds the 256 MiB limit",
                    canonical,
                )
            declared_total += info.file_size
            if declared_total > limits.max_total_size:
                raise CadPackageError(
                    "CAD_ARCHIVE_TOO_LARGE",
                    "expanded archive exceeds the 512 MiB limit",
                )
            if info.file_size:
                if info.compress_size == 0:
                    raise CadPackageError(
                        "CAD_ARCHIVE_RATIO_EXCEEDED",
                        "archive entry exceeds the 200:1 compression-ratio limit",
                        canonical,
                    )
                if info.file_size > info.compress_size * limits.max_compression_ratio:
                    raise CadPackageError(
                        "CAD_ARCHIVE_RATIO_EXCEEDED",
                        "archive entry exceeds the 200:1 compression-ratio limit",
                        canonical,
                    )
            validated.append((info, relative))

        actual_total = 0
        for info, relative in validated:
            target = destination.joinpath(*relative.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open(info, "r") as source, target.open("xb") as output:
                    written = _copy_limited(
                        source,
                        output,
                        limits.max_file_size,
                        limits.max_total_size - actual_total,
                    )
            except CadPackageError:
                raise
            except (OSError, RuntimeError, zipfile.BadZipFile):
                raise CadPackageError(
                    "CAD_ARCHIVE_INVALID",
                    "archive entry could not be extracted safely",
                    relative.as_posix(),
                ) from None
            if written != info.file_size:
                raise CadPackageError(
                    "CAD_ARCHIVE_SIZE_MISMATCH",
                    "archive entry size differs from its directory record",
                    relative.as_posix(),
                )
            actual_total += written
            extracted.append(target)

    return extracted


def _safe_member_path(name: str) -> PurePosixPath:
    if (
        not isinstance(name, str)
        or not name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise CadPackageError("CAD_ARCHIVE_UNSAFE_PATH", "invalid archive path")
    portable = name.replace("\\", "/")
    path = PurePosixPath(portable)
    windows_path = PureWindowsPath(portable)
    if (
        path.is_absolute()
        or windows_path.drive
        or portable.startswith("//")
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise CadPackageError(
            "CAD_ARCHIVE_UNSAFE_PATH",
            "absolute, drive, UNC, and parent paths are not permitted",
        )
    for part in path.parts:
        if (
            part.endswith((" ", "."))
            or ":" in part
            or _WINDOWS_DEVICE_RE.fullmatch(part)
        ):
            raise CadPackageError(
                "CAD_ARCHIVE_UNSAFE_PATH",
                "archive path is not portable across supported filesystems",
            )
    return path


def _copy_limited(
    source: IO[bytes],
    output: BinaryIO,
    max_file_size: int,
    remaining_total: int,
) -> int:
    written = 0
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            break
        written += len(chunk)
        if written > max_file_size or written > remaining_total:
            raise CadPackageError(
                "CAD_ARCHIVE_TOO_LARGE",
                "expanded archive exceeded its declared safety limit",
            )
        output.write(chunk)
    output.flush()
    os.fsync(output.fileno())
    return written


def _is_nested_archive(path: str) -> bool:
    lowered = path.casefold()
    return any(lowered.endswith(suffix) for suffix in _NESTED_ARCHIVE_SUFFIXES)


__all__ = [
    "ArchiveLimits",
    "DEFAULT_ARCHIVE_LIMITS",
    "extract_zip_safely",
]
