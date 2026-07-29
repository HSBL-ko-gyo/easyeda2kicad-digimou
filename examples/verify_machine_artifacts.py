"""Minimal independent verifier for machine-result v1 artifact hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Mapping, Optional, Sequence


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(value: Any) -> Optional[PurePosixPath]:
    if not isinstance(value, str) or "\\" in value:
        return None
    path = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        path.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        return None
    return path


def _bases(values: Sequence[str]) -> Dict[str, Path]:
    output: Dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if (
            not separator
            or name not in ("project", "output", "cwd")
            or not raw_path
            or name in output
        ):
            raise ValueError("--base requires one project|output|cwd=PATH per base")
        output[name] = Path(raw_path).expanduser().resolve()
    return output


def verify(result: Mapping[str, Any], bases: Mapping[str, Path]) -> Dict[str, int]:
    artifacts = result.get("artifacts")
    if (
        result.get("schema_version") != "1"
        or result.get("command") != "acquire"
        or not isinstance(artifacts, list)
    ):
        raise ValueError("input is not an acquire machine-result v1 document")
    verified = 0
    failed = 0
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise ValueError("artifact entry is invalid")
        relative = _relative(artifact.get("path"))
        base_name = artifact.get("path_base")
        expected = artifact.get("sha256")
        base = bases.get(base_name) if isinstance(base_name, str) else None
        if (
            relative is None
            or base is None
            or not isinstance(expected, str)
            or len(expected) != 64
        ):
            failed += 1
            continue
        candidate = base.joinpath(*relative.parts).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            failed += 1
            continue
        if (
            base.is_symlink()
            or any(
                base.joinpath(*relative.parts[:index]).is_symlink()
                for index in range(1, len(relative.parts) + 1)
            )
            or not candidate.is_file()
            or _sha256(candidate) != expected
        ):
            failed += 1
            continue
        verified += 1
    return {"total": len(artifacts), "verified": verified, "failed": failed}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result")
    parser.add_argument("--base", action="append", default=[], required=True)
    args = parser.parse_args(argv)
    try:
        result = json.loads(Path(args.result).read_text(encoding="utf-8"))
        if not isinstance(result, Mapping):
            raise ValueError("result root must be an object")
        summary = verify(result, _bases(args.base))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        print(json.dumps({"status": "INVALID_INPUT"}, separators=(",", ":")))
        return 2
    print(
        json.dumps(
            {
                "status": "VERIFIED" if summary["failed"] == 0 else "FAILED",
                "summary": summary,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
