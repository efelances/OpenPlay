"""Rotating file logging and safe stdio handling for windowed executables."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from openplay.paths import get_data_dir


_CONFIGURED = False


def setup_logging(log_dir: Path | None = None) -> Path:
    """Configure rotating file logging and redirect missing stdout/stderr streams."""
    global _CONFIGURED
    target_dir = log_dir if log_dir is not None else (get_data_dir() / "logs")
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "openplay.log"
    stdio_file = target_dir / "stdio.log"

    if sys.stdout is None or sys.stderr is None:
        # Keep stdio redirected to a separate file so RotatingFileHandler never
        # hits WinError 32 on Windows when rolling over openplay.log.
        stream = open(stdio_file, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = stream  # type: ignore[assignment]
        if sys.stderr is None:
            sys.stderr = stream  # type: ignore[assignment]

    if not _CONFIGURED:
        root_logger = logging.getLogger("openplay")
        root_logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=1_048_576,
            backupCount=3,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
        _CONFIGURED = True

    return log_file
