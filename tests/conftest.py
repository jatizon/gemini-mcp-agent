"""Shared fixtures for gemini-agent-mcp tests."""

from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a fake project directory with sample files for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "import os\n\ndef main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()\n"
    )
    (tmp_path / "src" / "utils.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"
    )
    (tmp_path / "README.md").write_text("# Test Project\n\nA test project.\n")
    (tmp_path / "config.json").write_text('{"key": "value"}\n')
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\xff\xfe")
    return tmp_path
