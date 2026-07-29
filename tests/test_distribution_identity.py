from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from easyeda2kicad_digimou import (
    CLI_NAME,
    DISPLAY_NAME,
    DISTRIBUTION_NAME,
    __version__,
    version_identity,
)
from easyeda2kicad_digimou import __main__ as cli

ROOT = Path(__file__).parents[1]
README = ROOT / "README.md"


def _run(
    command: list[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed test commands and wheel paths
        command,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _venv_python(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def _pip(python: Path, *arguments: str, cwd: Path) -> None:
    _run(
        [str(python), "-m", "pip", "--disable-pip-version-check", *arguments],
        cwd=cwd,
    )


def _assert_fork_works(python: Path, cwd: Path) -> None:
    completed = _run(
        [str(python), "-m", "easyeda2kicad_digimou", "--version"],
        cwd=cwd,
    )
    assert completed.stdout.strip() == version_identity()
    assert completed.stderr == ""


def _assert_upstream_works(python: Path, cwd: Path) -> None:
    completed = _run(
        [
            str(python),
            "-c",
            "import easyeda2kicad; print(easyeda2kicad.__version__)",
        ],
        cwd=cwd,
    )
    assert completed.stdout.strip()
    _run([str(python), "-m", "easyeda2kicad", "--help"], cwd=cwd)


def _assert_module_missing(python: Path, module: str, cwd: Path) -> None:
    completed = _run(
        [
            str(python),
            "-c",
            (
                "import importlib.util,sys;"
                f"sys.exit(0 if importlib.util.find_spec({module!r}) is None else 1)"
            ),
        ],
        cwd=cwd,
        check=False,
    )
    assert completed.returncode == 0


def test_source_and_setup_use_only_the_distinct_install_identity() -> None:
    setup_text = (ROOT / "setup.py").read_text(encoding="utf-8")

    assert f'name="{DISTRIBUTION_NAME}"' in setup_text
    assert '"easyeda2kicad-digimou = easyeda2kicad_digimou.__main__:main"' in (
        setup_text
    )
    assert (ROOT / "easyeda2kicad_digimou" / "__init__.py").is_file()
    assert not (ROOT / "easyeda2kicad").exists()
    assert cli.get_parser().prog == CLI_NAME


def test_version_output_unambiguously_identifies_the_fork(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(["--version"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == (
        f"{CLI_NAME} {__version__} ({DISPLAY_NAME}, unofficial derivative)"
    )
    assert captured.err == ""


def test_readme_documents_only_the_distinct_install_identity() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "`easyeda2kicad-digimou`" in readme
    assert "`easyeda2kicad_digimou`" in readme
    assert "python -m easyeda2kicad_digimou" in readme
    assert "easyeda2kicad-digimou --version" in readme
    assert "python -m pip install easyeda2kicad" not in readme


@pytest.mark.skipif(
    not (
        os.environ.get("DIGIMOU_WHEEL")
        and os.environ.get("UPSTREAM_EASYEDA2KICAD_WHEEL")
    ),
    reason="set both wheel paths for explicit co-install/uninstall validation",
)
@pytest.mark.parametrize("fork_first", [True, False])
def test_upstream_and_fork_coinstall_and_uninstall_independently(
    tmp_path: Path,
    fork_first: bool,
) -> None:
    fork_wheel = Path(os.environ["DIGIMOU_WHEEL"]).resolve()
    upstream_wheel = Path(os.environ["UPSTREAM_EASYEDA2KICAD_WHEEL"]).resolve()
    assert fork_wheel.is_file()
    assert upstream_wheel.is_file()
    environment = tmp_path / ("fork-first" if fork_first else "upstream-first")
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = _venv_python(environment)
    first, second = (
        (fork_wheel, upstream_wheel) if fork_first else (upstream_wheel, fork_wheel)
    )

    _pip(python, "install", "--no-deps", str(first), cwd=tmp_path)
    _pip(python, "install", "--no-deps", str(second), cwd=tmp_path)
    _assert_fork_works(python, tmp_path)
    _assert_upstream_works(python, tmp_path)

    _pip(python, "uninstall", "-y", DISTRIBUTION_NAME, cwd=tmp_path)
    _assert_module_missing(python, "easyeda2kicad_digimou", tmp_path)
    _assert_upstream_works(python, tmp_path)

    _pip(python, "install", "--no-deps", str(fork_wheel), cwd=tmp_path)
    _pip(python, "uninstall", "-y", "easyeda2kicad", cwd=tmp_path)
    _assert_module_missing(python, "easyeda2kicad", tmp_path)
    _assert_fork_works(python, tmp_path)

    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    assert any(path.name.startswith(CLI_NAME) for path in scripts.iterdir())
    assert shutil.which(
        CLI_NAME,
        path=str(scripts),
    )
