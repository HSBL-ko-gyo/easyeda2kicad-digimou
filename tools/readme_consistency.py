"""Detect user-facing feature changes that are not reflected in README.md."""

from __future__ import annotations

import argparse
import ast
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import AbstractSet, Optional, Sequence, Tuple


FEATURE_SUBJECT = re.compile(
    r"^(?:"
    r"feat(?:\([^)]*\))?!?:|"
    r"\[feature\]|"
    r"add(?:ed|s|ing)?\b|"
    r"implement(?:ed|s|ing)?\b|"
    r"introduce(?:d|s|ing)?\b|"
    r"support(?:ed|s|ing)?\b|"
    r"enable(?:d|s|ing)?\b|"
    r"expose(?:d|s|ing)?\b"
    r")",
    re.IGNORECASE,
)
README_PATH = "README.md"
DEFAULT_CLI_PATHS = (
    "easyeda2kicad_digimou/__main__.py",
    "easyeda2kicad/__main__.py",
)
DEFAULT_PACKAGE_ROOTS = ("easyeda2kicad_digimou", "easyeda2kicad")


class ConsistencyCheckError(RuntimeError):
    """Raised when the repository cannot be inspected reliably."""


@dataclass(frozen=True)
class Analysis:
    """A deterministic README consistency decision."""

    changed_paths: Tuple[str, ...]
    added_surface_files: Tuple[str, ...]
    feature_subjects: Tuple[str, ...]
    new_options: Tuple[str, ...]
    undocumented_options: Tuple[str, ...]
    removed_documented_options: Tuple[str, ...]
    readme_changed: bool
    generic_documentation_gap: bool

    @property
    def inconsistent(self) -> bool:
        """Return whether an actionable README mismatch was found."""

        return bool(
            self.undocumented_options
            or self.removed_documented_options
            or self.generic_documentation_gap
        )


def _is_suppressed_help(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "SUPPRESS"
        and isinstance(node.value, ast.Name)
        and node.value.id == "argparse"
    )


def extract_public_cli_options(source: str) -> AbstractSet[str]:
    """Extract long, non-hidden argparse options without importing the package."""

    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ConsistencyCheckError(f"Could not parse CLI source: {error}") from error

    options = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
        ):
            continue
        if any(
            keyword.arg == "help" and _is_suppressed_help(keyword.value)
            for keyword in node.keywords
        ):
            continue
        for argument in node.args:
            if (
                isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
                and argument.value.startswith("--")
            ):
                options.add(argument.value)
    return options


def _is_production_path(
    path: str, package_roots: Sequence[str] = DEFAULT_PACKAGE_ROOTS
) -> bool:
    return any(path.startswith(f"{root}/") for root in package_roots) and (
        path.endswith(".py") or "/schemas/" in path
    )


def _is_added_surface_file(
    path: str, package_roots: Sequence[str] = DEFAULT_PACKAGE_ROOTS
) -> bool:
    if not _is_production_path(path, package_roots):
        return False
    name = Path(path).name
    if name in {"__init__.py", "_version.py"} or name.startswith("_"):
        return False
    return path.endswith(".py") or path.endswith(".schema.json")


def evaluate_consistency(
    *,
    base_options: AbstractSet[str],
    head_options: AbstractSet[str],
    readme: str,
    changed_paths: Sequence[str],
    added_paths: Sequence[str],
    commit_subjects: Sequence[str],
    package_roots: Sequence[str] = DEFAULT_PACKAGE_ROOTS,
) -> Analysis:
    """Evaluate already-collected Git and source facts."""

    changed = tuple(sorted(set(changed_paths)))
    added_surface_files = tuple(
        sorted(
            path
            for path in set(added_paths)
            if _is_added_surface_file(path, package_roots)
        )
    )
    production_changed = any(
        _is_production_path(path, package_roots) for path in changed
    )
    feature_subjects = tuple(
        subject
        for subject in commit_subjects
        if production_changed and FEATURE_SUBJECT.match(subject.strip())
    )
    new_options = tuple(sorted(head_options - base_options))
    undocumented_options = tuple(
        option for option in new_options if option not in readme
    )
    removed_documented_options = tuple(
        sorted(option for option in base_options - head_options if option in readme)
    )
    readme_changed = README_PATH in changed

    generic_feature_signal = bool(added_surface_files or feature_subjects)
    newly_exposed_surface_is_documented = bool(new_options) and not undocumented_options
    generic_documentation_gap = (
        generic_feature_signal
        and not readme_changed
        and not newly_exposed_surface_is_documented
    )

    return Analysis(
        changed_paths=changed,
        added_surface_files=added_surface_files,
        feature_subjects=feature_subjects,
        new_options=new_options,
        undocumented_options=undocumented_options,
        removed_documented_options=removed_documented_options,
        readme_changed=readme_changed,
        generic_documentation_gap=generic_documentation_gap,
    )


def _run_git(repository: Path, *arguments: str) -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise ConsistencyCheckError("git executable was not found on PATH")
    try:
        completed = subprocess.run(  # noqa: S603 - fixed executable, no shell
            [git_executable, *arguments],
            cwd=repository,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = str(error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            detail = error.stderr.strip()
        raise ConsistencyCheckError(
            f"git {' '.join(arguments)} failed: {detail}"
        ) from error
    return completed.stdout


def _git_paths(
    repository: Path, base: str, head: str, *, added_only: bool = False
) -> Tuple[str, ...]:
    arguments = ["diff", "--name-only", "-z"]
    if added_only:
        arguments.append("--diff-filter=A")
    arguments.extend([base, head, "--"])
    output = _run_git(repository, *arguments)
    return tuple(path for path in output.split("\0") if path)


def _git_file(repository: Path, revision: str, path: str) -> str:
    return _run_git(repository, "show", f"{revision}:{path}")


def _find_cli_source(
    repository: Path, revision: str, candidates: Sequence[str]
) -> Tuple[str, str]:
    errors = []
    for path in candidates:
        try:
            return path, _git_file(repository, revision, path)
        except ConsistencyCheckError as error:
            errors.append(str(error))
    raise ConsistencyCheckError(
        f"No supported CLI entry point exists at {revision}: "
        + ", ".join(candidates)
        + f" ({'; '.join(errors)})"
    )


def inspect_repository(repository: Path, base: str, head: str) -> Analysis:
    """Collect facts from a Git range and evaluate README consistency."""

    root_text = _run_git(repository, "rev-parse", "--show-toplevel").strip()
    root = Path(root_text)
    _run_git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
    _run_git(root, "rev-parse", "--verify", f"{head}^{{commit}}")

    changed_paths = _git_paths(root, base, head)
    added_paths = _git_paths(root, base, head, added_only=True)
    subjects = tuple(
        subject
        for subject in _run_git(
            root, "log", "--format=%s", f"{base}..{head}"
        ).splitlines()
        if subject
    )
    readme = _git_file(root, head, README_PATH)
    cli_path, head_source = _find_cli_source(root, head, DEFAULT_CLI_PATHS)
    head_options = extract_public_cli_options(head_source)
    base_candidates = (cli_path,) + tuple(
        path for path in DEFAULT_CLI_PATHS if path != cli_path
    )
    try:
        _, base_source = _find_cli_source(root, base, base_candidates)
    except ConsistencyCheckError:
        base_source = ""
    base_options = extract_public_cli_options(base_source) if base_source else set()
    package_roots = tuple(
        dict.fromkeys(
            path.split("/", maxsplit=1)[0] for path in (cli_path,) + DEFAULT_CLI_PATHS
        )
    )

    return evaluate_consistency(
        base_options=base_options,
        head_options=head_options,
        readme=readme,
        changed_paths=changed_paths,
        added_paths=added_paths,
        commit_subjects=subjects,
        package_roots=package_roots,
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def render_report(analysis: Analysis, base: str, head: str) -> str:
    """Render a concise Markdown report suitable for a GitHub issue."""

    status = (
        "README consistency gap detected"
        if analysis.inconsistent
        else "README consistency check: OK"
    )
    lines = [
        f"# {status}",
        "",
        f"- Revision range: `{base}..{head}`",
        f"- README.md changed: `{_yes_no(analysis.readme_changed)}`",
    ]

    if analysis.new_options:
        lines.append(
            "- New public CLI options: "
            + ", ".join(f"`{option}`" for option in analysis.new_options)
        )
    if analysis.added_surface_files:
        lines.append(
            "- New user-facing files: "
            + ", ".join(f"`{path}`" for path in analysis.added_surface_files)
        )
    if analysis.feature_subjects:
        lines.extend(
            ["", "## Feature signals", ""]
            + [f"- `{subject}`" for subject in analysis.feature_subjects]
        )

    if analysis.inconsistent:
        lines.extend(["", "## Why this was flagged", ""])
        if analysis.undocumented_options:
            lines.append(
                "- Public CLI options absent from README.md: "
                + ", ".join(f"`{option}`" for option in analysis.undocumented_options)
            )
        if analysis.removed_documented_options:
            lines.append(
                "- Removed CLI options still present in README.md: "
                + ", ".join(
                    f"`{option}`" for option in analysis.removed_documented_options
                )
            )
        if analysis.generic_documentation_gap:
            lines.append(
                "- A feature signal changed production code without a README.md update."
            )
        lines.extend(
            [
                "",
                "## Follow-up",
                "",
                "Update README.md so the user workflow and limitations match the "
                "implementation. If this is an internal-only change, record that "
                "reason here and close the issue.",
                "",
                "_This issue was created automatically by the README consistency "
                "monitor._",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "No new public interface detected in this revision range is missing "
                "from README.md.",
            ]
        )

    production_paths = [
        path for path in analysis.changed_paths if _is_production_path(path)
    ]
    if production_paths:
        lines.extend(["", "## Production files in scope", ""])
        lines.extend(f"- `{path}`" for path in production_paths[:30])
        if len(production_paths) > 30:
            lines.append(f"- and {len(production_paths) - 30} more files")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base Git revision")
    parser.add_argument("--head", required=True, help="Head Git revision")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository to inspect (default: current directory)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional path for the Markdown report",
    )
    return parser


def main(arguments: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        analysis = inspect_repository(args.repo, args.base, args.head)
        report = render_report(analysis, args.base, args.head)
    except ConsistencyCheckError as error:
        print(f"README consistency check failed to run: {error}", file=sys.stderr)
        return 2

    if args.report is not None:
        args.report.write_text(report, encoding="utf-8")
    print(report, end="")
    return 1 if analysis.inconsistent else 0


if __name__ == "__main__":
    raise SystemExit(main())
