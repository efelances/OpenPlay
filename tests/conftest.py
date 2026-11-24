"""Pytest configuration and shared isolated fixtures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Must be set before importing openplay modules
os.environ.setdefault("OPENPLAY_DATA_DIR", tempfile.mkdtemp(prefix="openplay_test_"))
os.environ.setdefault("OPENPLAY_DISABLE_TTS", "1")


@pytest.fixture()
def fresh_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Provide an isolated writable user data directory per test."""
    monkeypatch.setenv("OPENPLAY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENPLAY_DISABLE_TTS", "1")
    return tmp_path
