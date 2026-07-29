from __future__ import annotations

# Global imports
from pathlib import Path
from typing import Optional, Set

# Local imports
from tools.readme_consistency import (
    Analysis,
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


def test_fix_commit_does_not_trigger_feature_heuristic() -> None:
    analysis = _evaluate(
        changed_paths=("easyeda2kicad_digimou/metadata/service.py",),
        subjects=("fix: handle an empty response",),
    )

    assert not analysis.inconsistent


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


def test_workflow_is_default_branch_only_and_can_create_issues() -> None:
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "readme-consistency.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "github.event.repository.default_branch" in workflow
    assert "issues: write" in workflow
    assert "readme-consistency:" in workflow
