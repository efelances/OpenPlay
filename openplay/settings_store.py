"""Atomic persistent JSON settings store."""

from __future__ import annotations

import ctypes
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from openplay.core.models import AccessibilitySettings

logger = logging.getLogger(__name__)


def detect_windows_language() -> str:
    """Detect Windows UI language on first launch; fallback to English."""
    if sys.platform != "win32":
        return "en"
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        primary = lang_id & 0x3FF
        return {
            0x1F: "tr",
            0x07: "de",
            0x0A: "es",
            0x09: "en",
        }.get(primary, "en")
    except Exception:
        return "en"


class SettingsStore:
    """Loads and atomically saves user settings, calibration, and rule overrides."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def default_state(self) -> dict[str, Any]:
        settings = AccessibilitySettings(language=detect_windows_language())
        return {
            "settings": settings.model_dump(),
            "active_profile_id": "hybrid_head_eye_action",
            "calibration": {},
            "overrides": {},
        }

    def load(self) -> dict[str, Any]:
        default = self.default_state()
        if not self.path.exists():
            return default
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return default
            settings = AccessibilitySettings.model_validate(raw.get("settings") or {})
            # Safety: never auto-arm live game input injection on startup
            settings.safe_test_mode = True
            active_profile_id = raw.get("active_profile_id")
            if not isinstance(active_profile_id, str) or not active_profile_id:
                active_profile_id = default["active_profile_id"]
            calibration_raw = raw.get("calibration") or {}
            calibration: dict[str, float] = {}
            if isinstance(calibration_raw, dict):
                for k, v in calibration_raw.items():
                    if isinstance(k, str) and isinstance(v, (int, float)):
                        calibration[k] = float(v)
            overrides_raw = raw.get("overrides") or {}
            overrides: dict[str, dict[str, dict[str, Any]]] = {}
            if isinstance(overrides_raw, dict):
                for pid, rules in overrides_raw.items():
                    if isinstance(pid, str) and isinstance(rules, dict):
                        overrides[pid] = {
                            rid: dict(vals)
                            for rid, vals in rules.items()
                            if isinstance(rid, str) and isinstance(vals, dict)
                        }
            return {
                "settings": settings.model_dump(),
                "active_profile_id": active_profile_id,
                "calibration": calibration,
                "overrides": overrides,
            }
        except Exception as exc:
            logger.warning("Failed to load settings from %s, using defaults: %s", self.path, exc)
            return default

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".json.tmp")
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self.path)
