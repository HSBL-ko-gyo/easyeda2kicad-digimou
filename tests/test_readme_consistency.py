from __future__ import annotations

# Global imports
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Set

import pytest

# Local imports
import tools.readme_consistency as monitor
from tools.readme_consistency import (
    Analysis,
    ConsistencyCheckError,
    evaluate_consistency,
    extract_public_cli_options,
    render_report,
)


def _evaluate(
    *,
    base_options: Optional[Set[str]] = None,
    head_options: Optional[Set[str]] = None,
    readme: str = "# Project\n",
    changed_paths: tuple[str, ...] = (),
    added_paths: tuple[str, ...] = (),
    subjects: tuple[str, ...] = (),
) -> Analysis:
    return evaluate_consistency(
        base_options=base_options or set(),
        head_options=head_options or set(),
        readme=readme,
        changed_paths=changed_paths,
        added_paths=added_paths,
        commit_subjects=subjects,
    )


def test_extract_public_cli_options_ignores_suppressed_aliases() -> None:
    source = """
parser.add_argument("--visible")
parser.add_argument("--hidden", help=argparse.SUPPRESS)
"""

    assert extract_public_cli_options(source) == {"--visible"}


def test_new_undocumented_cli_option_is_inconsistent() -> None:
    analysis = _evaluate(
        head_options={"--new-mode"},
        changed_paths=("easyeda2kicad_digimou/__main__.py", "README.md"),
        readme="# Project\nUnrelated README edit.\n",
    )

    assert analysis.inconsistent
    assert analysis.undocumented_options == ("--new-mode",)


def test_predocumented_new_cli_option_is_consistent() -> None:
    analysis = _evaluate(
        head_options={"--new-mode"},
        changed_paths=("easyeda2kicad_digimou/__main__.py",),
        readme="# Project\nUse `--new-mode` to enable the mode.\n",
        subjects=("feat: add the new mode",),
    )

    assert not analysis.inconsistent


def test_feature_commit_without_readme_change_is_inconsistent() -> None:
    analysis = _evaluate(
        changed_paths=("easyeda2kicad_digimou/metadata/service.py",),
        subjects=("Add distributor ranking",),
    )

    assert analysis.inconsistent
    assert analysis.generic_documentation_gap


def test_feature_commit_with_readme_change_is_consistent() -> None:
    analysis = _evaluate(
        changed_paths=("easyeda2kicad_digimou/metadata/service.py", "README.md"),
        subjects=("feat(metadata): add distributor ranking",),
    )

    assert not analysis.inconsistent


def test_fix_commit_requires_readme_review() -> None:
    analysis = _evaluate(
        changed_paths=("easyeda2kicad_digimou/metadata/service.py",),
        subjects=("fix: handle an empty response",),
    )

    assert analysis.inconsistent
    assert analysis.generic_documentation_gap


def test_both_current_and_legacy_package_roots_are_monitored() -> None:
    current = _evaluate(
        changed_paths=("easyeda2kicad_digimou/new_export.py",),
        added_paths=("easyeda2kicad_digimou/new_export.py",),
    )
    legacy = _evaluate(
        changed_paths=("easyeda2kicad/new_export.py",),
        added_paths=("easyeda2kicad/new_export.py",),
    )

    assert current.added_surface_files == ("easyeda2kicad_digimou/new_export.py",)
    assert legacy.added_surface_files == ("easyeda2kicad/new_export.py",)
    assert current.inconsistent
    assert legacy.inconsistent


def test_removed_option_still_in_readme_is_inconsistent() -> None:
    analysis = _evaluate(
        base_options={"--old-mode"},
        changed_paths=("easyeda2kicad_digimou/__main__.py",),
        readme="# Project\nThe `--old-mode` option is available.\n",
    )

    assert analysis.inconsistent
    assert analysis.removed_documented_options == ("--old-mode",)


def test_report_is_readable_and_actionable() -> None:
    analysis = _evaluate(
        head_options={"--new-mode"},
        changed_paths=("easyeda2kicad_digimou/__main__.py",),
    )

    report = render_report(analysis, "base", "head")

    assert "README consistency gap detected" in report
    assert "--new-mode" in report
    assert "Follow-up" in report


def test_report_never_publishes_raw_subjects_or_paths() -> None:
    hostile_subject = "feat: notify @maintainers `code`\nsecret-value"
    hostile_path = "easyeda2kicad_digimou/@maintainers`secret`.py"
    analysis = _evaluate(
        changed_paths=(hostile_path,),
        added_paths=(hostile_path,),
        subjects=(hostile_subject,),
    )

    report = render_report(analysis, "base`@team", "head\nsecret")

    assert hostile_subject not in report
    assert hostile_path not in report
    assert "@maintainers" not in report
    assert "base`@team" not in report
    assert "head\nsecret" not in report
    assert "Changed production files: 1" in report


def test_report_bounds_and_omits_unsafe_option_text() -> None:
    unsafe_option = "--unsafe`@team"
    unsafe_analysis = _evaluate(
        head_options={unsafe_option},
        changed_paths=("easyeda2kicad_digimou/__main__.py",),
    )

    unsafe_report = render_report(unsafe_analysis, "base", "head")

    assert unsafe_option not in unsafe_report
    assert "[unsafe option omitted]" in unsafe_report

    bounded_analysis = _evaluate(
        head_options={f"--option-{index}" for index in range(60)},
        changed_paths=("easyeda2kicad_digimou/__main__.py",),
    )
    bounded_report = render_report(bounded_analysis, "base", "head")
    assert "and 20 more" in bounded_report
    assert len(bounded_report) < 10000


def test_workflow_is_default_branch_only_and_can_create_issues() -> None:
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "readme-consistency.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "github.ref_type == 'branch'" in workflow
    assert "github.event.repository.default_branch" in workflow
    assert 'git rev-parse --verify "${base_sha}^{commit}"' in workflow
    assert "issues: write" in workflow
    assert "readme-consistency:" in workflow
    assert "report.slice(0, 49000)" in workflow
    assert "github.paginate" not in workflow
    assert "per_page: 100" in workflow


def test_inspection_fails_closed_above_changed_path_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def run_git(_repository: Path, *arguments: str) -> str:
        if arguments == ("rev-parse", "--show-toplevel"):
            return str(tmp_path)
        return "verified"

    monkeypatch.setattr(monitor, "_run_git", run_git)
    monkeypatch.setattr(
        monitor,
        "_git_paths",
        lambda *_args, **_kwargs: tuple(
            f"easyeda2kicad_digimou/generated_{index}.py"
            for index in range(monitor.MAX_CHANGED_PATHS + 1)
        ),
    )

    with pytest.raises(
        ConsistencyCheckError,
        match="safe changed-path inspection limit",
    ):
        monitor.inspect_repository(tmp_path, "base", "head")


def test_git_path_reader_stops_and_reaps_at_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path_count = monitor.MAX_CHANGED_PATHS + 5_000
    output = b"".join(
        f"easyeda2kicad_digimou/generated_{index}.py\0".encode()
        for index in range(path_count)
    )

    class ChunkedOutput:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload
            self.position = 0
            self.closed = False

        def read(self, size: int) -> bytes:
            end = min(self.position + min(size, 4096), len(self.payload))
            chunk = self.payload[self.position : end]
            self.position = end
            return chunk

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self, stdout: ChunkedOutput) -> None:
            self.stdout = stdout
            self.returncode: Optional[int] = None
            self.terminated = False
            self.waited = False

        def poll(self) -> Optional[int]:
            return self.returncode

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        def wait(self, timeout: Optional[float] = None) -> int:
            del timeout
            self.waited = True
            if self.returncode is None:
                self.returncode = 0
            return self.returncode

        def kill(self) -> None:
            self.terminate()

    stdout = ChunkedOutput(output)
    process = FakeProcess(stdout)

    monkeypatch.setattr(shutil, "which", lambda _name: "git")
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)

    with pytest.raises(
        ConsistencyCheckError,
        match="safe changed-path inspection limit",
    ):
        monitor._git_paths(tmp_path, "base", "head")

    assert process.terminated
    assert process.waited
    assert stdout.closed
    assert stdout.position < len(output)
