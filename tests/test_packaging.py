"""Packaging, entry-point, and installed-runtime contracts."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"


def load_pyproject() -> dict:
    with PYPROJECT.open("rb") as source:
        return tomllib.load(source)


def test_project_metadata_and_entry_points_are_canonical() -> None:
    project = load_pyproject()["project"]

    assert project["name"] == "smart-expense-tracker"
    assert project["requires-python"] == ">=3.10"
    assert project["scripts"] == {
        "expense-tracker": "smart_expense_tracker.cli:main",
        "expense-tracker-storage": "smart_expense_tracker.storage_cli:main",
        "expense-tracker-telegram": "smart_expense_tracker.telegram_cli:main",
    }
    assert "python-telegram-bot>=22.8,<23.0" in project["dependencies"]


def test_all_flat_source_modules_are_declared_for_installation() -> None:
    configured = set(load_pyproject()["tool"]["setuptools"]["py-modules"])
    source = {path.stem for path in (PROJECT_ROOT / "src").glob("*.py")}

    assert configured == source


def test_installed_entry_points_use_the_project_namespace() -> None:
    configuration = load_pyproject()
    scripts = configuration["project"]["scripts"]

    assert all(
        target.startswith("smart_expense_tracker.")
        for target in scripts.values()
    )
    assert configuration["tool"]["setuptools"]["packages"] == [
        "smart_expense_tracker"
    ]


def test_importing_entry_modules_has_no_filesystem_side_effects(tmp_path) -> None:
    environment = {
        **os.environ,
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import main, telegram_bot"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "data").exists()


def test_direct_cli_creates_only_sqlite_workspace(tmp_path) -> None:
    environment = {
        **os.environ,
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import main; main.main()"],
        cwd=tmp_path,
        env=environment,
        input="0\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data" / "smart_expense_tracker.sqlite3").is_file()
    assert list((tmp_path / "data").glob("*.json")) == []


def test_console_entry_point_delegates_to_main(monkeypatch) -> None:
    import main

    monkeypatch.setattr("builtins.input", lambda _prompt="": "0")
    assert main.main() is None


def test_namespaced_entry_modules_delegate_to_existing_adapters() -> None:
    import main
    import smart_expense_tracker
    import sqlite_backup
    import telegram_bot
    from smart_expense_tracker.cli import main as cli_main
    from smart_expense_tracker.storage_cli import main as storage_main
    from smart_expense_tracker.telegram_cli import main as telegram_main

    assert smart_expense_tracker.__doc__
    assert cli_main is main.main
    assert storage_main is sqlite_backup.main
    assert telegram_main is telegram_bot.main


def test_ci_contains_quality_build_and_installed_smoke_gates() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "python -m pytest --cov" in workflow
    assert "python -m mypy" in workflow
    assert "python -m ruff check src tests" in workflow
    assert "python -m pip_audit --skip-editable" in workflow
    assert "python -m build" in workflow
    assert 'test -x "$wheel_venv/bin/expense-tracker-telegram"' in workflow
    assert "git diff-tree --check --root -r HEAD" in workflow


@pytest.mark.parametrize(
    "removed_module",
    [
        "account_storage",
        "category_storage",
        "json_storage",
        "sqlite_migration",
        "storage",
    ],
)
def test_removed_json_modules_are_not_packaged(removed_module: str) -> None:
    assert removed_module not in load_pyproject()["tool"]["setuptools"]["py-modules"]
