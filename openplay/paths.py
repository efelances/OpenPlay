"""Filesystem paths for source and frozen (PyInstaller) execution."""

from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN: bool = getattr(sys, "frozen", False)
BUNDLE_ROOT: Path = Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parent.parent
PACKAGE_DIR: Path = BUNDLE_ROOT / "openplay"
WEB_DIR: Path = PACKAGE_DIR / "web"
LOCALES_DIR: Path = PACKAGE_DIR / "locales"
BUNDLED_MODEL: Path = PACKAGE_DIR / "models" / "face_landmarker.task"


def get_data_dir(override: Path | None = None) -> Path:
    """Return writable user data directory and ensure it exists."""
    if override is not None:
        base = Path(override)
    else:
        env_dir = os.environ.get("OPENPLAY_DATA_DIR")
        if env_dir:
            base = Path(env_dir)
        else:
            appdata = os.environ.get("APPDATA")
            root = Path(appdata) if appdata else Path.home()
            base = root / "OpenPlayAccess"
    base.mkdir(parents=True, exist_ok=True)
    return base


DATA_DIR: Path = get_data_dir()
USER_MODEL: Path = DATA_DIR / "models" / "face_landmarker.task"
LOG_DIR: Path = DATA_DIR / "logs"
