"""Packaging and installed-entry contracts."""

import importlib
import os
from pathlib import Path
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib

import account_storage
import category_storage
import main
import storage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def load_pyproject() -> dict:
    with PYPROJECT.open("rb") as pyproject_file:
        return tomllib.load(pyproject_file)


def test_project_metadata_declares_release_and_dependencies() -> None:
    project = load_pyproject()["project"]

    assert project["name"] == "smart-expense-tracker"
    assert project["version"] == "1.4.0"
    assert project["requires-python"] == ">=3.10"
    assert project["dependencies"] == ["openpyxl>=3.1,<4.0"]
    assert project["optional-dependencies"]["dev"] == [
        "build>=1.2,<2.0",
        "pytest>=8.0,<9.0",
        "tomli>=2.0,<3.0; python_version < '3.11'",
    ]


def test_console_script_points_to_existing_main_callable() -> None:
    target = load_pyproject()["project"]["scripts"]["expense-tracker"]
    module_name, attribute_name = target.split(":", maxsplit=1)

    entry_callable = getattr(importlib.import_module(module_name), attribute_name)

    assert entry_callable is main.main
    assert callable(entry_callable)


def test_console_entry_runs_existing_orchestration_and_exits(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: "0")

    main.main()
    output = capsys.readouterr().out

    assert "Smart Expense Tracker" in output
    assert "See you later !" in output


def test_importing_entry_module_does_not_start_cli(tmp_path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert not (tmp_path / "data").exists()


def test_all_flat_source_modules_are_declared_for_installation() -> None:
    configured_modules = set(load_pyproject()["tool"]["setuptools"]["py-modules"])
    source_modules = {
        path.stem for path in (PROJECT_ROOT / "src").glob("*.py")
    }

    assert configured_modules == source_modules


def test_default_runtime_paths_use_one_current_workspace(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    paths = [
        storage.DATA_FILE,
        account_storage.ACCOUNTS_FILE,
        account_storage.ACCOUNT_STATE_FILE,
        category_storage.CATEGORIES_FILE,
        category_storage.CATEGORY_STATE_FILE,
    ]

    assert [path.parent.resolve() for path in paths] == [
        tmp_path / "data"
    ] * len(paths)
    assert [path.name for path in paths] == [
        "transactions.json",
        "accounts.json",
        "accounts_state.json",
        "categories.json",
        "categories_state.json",
    ]
    assert not (tmp_path / "data").exists()
