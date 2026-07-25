from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from easyeda2kicad.cad.archive import ArchiveLimits, extract_zip_safely
from easyeda2kicad.cad.errors import CadPackageError


def _zip_with_entries(
    path: Path,
    entries: list[tuple[str, bytes]],
    *,
    compression: int = zipfile.ZIP_STORED,
) -> Path:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return path


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../escape.kicad_sym",
        "/absolute/model.step",
        r"C:\absolute\model.step",
        r"\\server\share\model.step",
        "folder/../../escape.kicad_mod",
        "folder/NUL.txt",
        "folder/trailing. ",
        "folder/control\x1b.kicad_mod",
        "folder/newline\nmodel.step",
    ],
)
def test_archive_rejects_unsafe_paths_without_writing(
    tmp_path: Path, unsafe_name: str
) -> None:
    package = _zip_with_entries(tmp_path / "unsafe.zip", [(unsafe_name, b"x")])
    destination = tmp_path / "extracted"

    with pytest.raises(CadPackageError, match="CAD_ARCHIVE_UNSAFE_PATH"):
        extract_zip_safely(package, destination)

    assert list(destination.rglob("*")) == []


def test_archive_rejects_symlinks(tmp_path: Path) -> None:
    package = tmp_path / "link.zip"
    link = zipfile.ZipInfo("model.wrl")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(link, b"target")

    with pytest.raises(CadPackageError, match="CAD_ARCHIVE_LINK_REJECTED"):
        extract_zip_safely(package, tmp_path / "extracted")


def test_archive_rejects_duplicate_and_case_colliding_paths(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.zip"
    with pytest.warns(UserWarning, match="Duplicate name"):
        _zip_with_entries(duplicate, [("part.txt", b"a"), ("part.txt", b"b")])
    with pytest.raises(CadPackageError, match="CAD_ARCHIVE_DUPLICATE_PATH"):
        extract_zip_safely(duplicate, tmp_path / "duplicate-output")

    collision = _zip_with_entries(
        tmp_path / "collision.zip",
        [("Part.kicad_sym", b"a"), ("part.kicad_sym", b"b")],
    )
    with pytest.raises(CadPackageError, match="CAD_ARCHIVE_CASE_COLLISION"):
        extract_zip_safely(collision, tmp_path / "collision-output")


def test_archive_rejects_nested_archives(tmp_path: Path) -> None:
    package = _zip_with_entries(tmp_path / "nested.zip", [("payload/data.7z", b"x")])

    with pytest.raises(CadPackageError, match="CAD_NESTED_ARCHIVE_REJECTED"):
        extract_zip_safely(package, tmp_path / "extracted")


def test_archive_rejects_entry_count_file_total_and_ratio_limits(
    tmp_path: Path,
) -> None:
    entries = _zip_with_entries(
        tmp_path / "entries.zip", [("a.txt", b"a"), ("b.txt", b"b")]
    )
    with pytest.raises(CadPackageError, match="CAD_ARCHIVE_TOO_MANY_ENTRIES"):
        extract_zip_safely(
            entries,
            tmp_path / "entries-output",
            limits=ArchiveLimits(max_entries=1),
        )

    large_file = _zip_with_entries(tmp_path / "file.zip", [("a.txt", b"12345")])
    with pytest.raises(CadPackageError, match="CAD_ARCHIVE_FILE_TOO_LARGE"):
        extract_zip_safely(
            large_file,
            tmp_path / "file-output",
            limits=ArchiveLimits(max_file_size=4),
        )

    large_total = _zip_with_entries(
        tmp_path / "total.zip", [("a.txt", b"123"), ("b.txt", b"456")]
    )
    with pytest.raises(CadPackageError, match="CAD_ARCHIVE_TOO_LARGE"):
        extract_zip_safely(
            large_total,
            tmp_path / "total-output",
            limits=ArchiveLimits(max_total_size=5),
        )

    high_ratio = _zip_with_entries(
        tmp_path / "ratio.zip",
        [("a.txt", b"0" * 20_000)],
        compression=zipfile.ZIP_DEFLATED,
    )
    with pytest.raises(CadPackageError, match="CAD_ARCHIVE_RATIO_EXCEEDED"):
        extract_zip_safely(high_ratio, tmp_path / "ratio-output")


def test_valid_archive_streams_regular_files(tmp_path: Path) -> None:
    package = _zip_with_entries(
        tmp_path / "valid.zip",
        [("root/readme.txt", b"fixture"), ("root/model.wrl", b"#VRML V2.0 utf8")],
    )

    files = extract_zip_safely(package, tmp_path / "extracted")

    assert [path.relative_to(tmp_path / "extracted").as_posix() for path in files] == [
        "root/readme.txt",
        "root/model.wrl",
    ]
    assert files[0].read_bytes() == b"fixture"
