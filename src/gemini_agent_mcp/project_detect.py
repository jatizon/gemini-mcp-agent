"""Auto-detect project language, test runner, linter, and structure."""

from __future__ import annotations

import json
from pathlib import Path


def detect_project(root: Path) -> dict:
    """Detect project type and available commands."""
    info = {
        "language": None,
        "package_manager": None,
        "test_cmd": None,
        "lint_cmd": None,
        "typecheck_cmd": None,
        "source_dirs": [],
        "test_dirs": [],
        "root_files": sorted(f.name for f in root.iterdir() if f.is_file())[:30],
    }

    if (root / "pyproject.toml").exists():
        info["language"] = "python"
        _detect_python(root, info)
    elif (root / "setup.py").exists():
        info["language"] = "python"
        info["package_manager"] = "pip"
        info["test_cmd"] = "pytest"
    elif (root / "package.json").exists():
        info["language"] = "javascript"
        _detect_node(root, info)
    elif (root / "Cargo.toml").exists():
        info["language"] = "rust"
        info["package_manager"] = "cargo"
        info["test_cmd"] = "cargo test"
        info["lint_cmd"] = "cargo clippy"
    elif (root / "go.mod").exists():
        info["language"] = "go"
        info["package_manager"] = "go"
        info["test_cmd"] = "go test ./..."
        info["lint_cmd"] = "golangci-lint run"
    elif (root / "Makefile").exists():
        info["language"] = "unknown"
        info["test_cmd"] = "make test"

    for d in ["src", "lib", "app", "pkg", "internal", "cmd"]:
        if (root / d).is_dir():
            info["source_dirs"].append(d)
    for d in ["tests", "test", "spec", "__tests__", "e2e"]:
        if (root / d).is_dir():
            info["test_dirs"].append(d)

    return info


def _detect_python(root: Path, info: dict) -> None:
    toml_text = (root / "pyproject.toml").read_text(errors="replace")

    if "uv.lock" in [f.name for f in root.iterdir() if f.is_file()]:
        info["package_manager"] = "uv"
    elif "poetry.lock" in [f.name for f in root.iterdir() if f.is_file()]:
        info["package_manager"] = "poetry"
    elif "Pipfile.lock" in [f.name for f in root.iterdir() if f.is_file()]:
        info["package_manager"] = "pipenv"
    else:
        info["package_manager"] = "pip"

    if "pytest" in toml_text:
        info["test_cmd"] = "pytest"
    if "ruff" in toml_text:
        info["lint_cmd"] = "ruff check ."
    elif "flake8" in toml_text:
        info["lint_cmd"] = "flake8 ."
    if "mypy" in toml_text:
        info["typecheck_cmd"] = "mypy ."
    elif "pyright" in toml_text:
        info["typecheck_cmd"] = "pyright"


def _detect_node(root: Path, info: dict) -> None:
    try:
        pkg = json.loads((root / "package.json").read_text())
    except (json.JSONDecodeError, OSError):
        return

    if (root / "pnpm-lock.yaml").exists():
        info["package_manager"] = "pnpm"
    elif (root / "yarn.lock").exists():
        info["package_manager"] = "yarn"
    elif (root / "bun.lockb").exists():
        info["package_manager"] = "bun"
    else:
        info["package_manager"] = "npm"

    scripts = pkg.get("scripts", {})
    if "test" in scripts:
        info["test_cmd"] = f"{info['package_manager']} test"
    if "lint" in scripts:
        info["lint_cmd"] = f"{info['package_manager']} run lint"
    if "typecheck" in scripts:
        info["typecheck_cmd"] = f"{info['package_manager']} run typecheck"
    elif "tsc" in scripts.get("build", ""):
        info["typecheck_cmd"] = "tsc --noEmit"

    if (root / "tsconfig.json").exists():
        info["language"] = "typescript"
