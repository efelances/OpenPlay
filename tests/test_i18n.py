"""Localization completeness and placeholder consistency tests."""

from __future__ import annotations

import re

from openplay.core.models import SUPPORTED_LANGUAGES
from openplay.core.profile_manager import create_builtin_profiles
from openplay.i18n import load_all
from openplay.paths import PACKAGE_DIR, WEB_DIR

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def _extract_placeholders(value) -> set[str]:
    if isinstance(value, str):
        return set(_PLACEHOLDER_RE.findall(value))
    if isinstance(value, list):
        out: set[str] = set()
        for item in value:
            out |= _extract_placeholders(item)
        return out
    return set()


def test_all_locales_have_matching_keys_and_placeholders():
    locales = load_all(force_reload=True)
    assert set(locales.keys()) == set(SUPPORTED_LANGUAGES)

    en_keys = set(locales["en"].keys())
    for lang, data in locales.items():
        assert set(data.keys()) == en_keys, f"Key mismatch in {lang}.json"
        for key, val in data.items():
            if isinstance(val, str):
                assert val.strip() != "", f"Empty string for {lang}:{key}"
            elif isinstance(val, list):
                assert len(val) > 0, f"Empty list for {lang}:{key}"
                assert all(isinstance(x, str) and x.strip() != "" for x in val), f"Empty list item in {lang}:{key}"
            else:
                raise AssertionError(f"Unsupported locale value type for {lang}:{key}: {type(val)}")

            en_ph = _extract_placeholders(locales["en"][key])
            cur_ph = _extract_placeholders(val)
            assert cur_ph == en_ph, f"Placeholder mismatch for {lang}:{key}: {cur_ph} != {en_ph}"


def test_html_and_js_keys_exist_in_en_locale():
    en = load_all(force_reload=True)["en"]
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    html_keys = re.findall(r'data-i18n(?:-(?:aria|alt|title))?="([^"]+)"', html)
    assert html_keys, "Expected data-i18n keys in index.html"
    for key in html_keys:
        assert key in en, f"Missing HTML i18n key in en.json: {key}"

    js_keys = re.findall(r'\bt\(\s*["\']([a-z0-9_.]+)["\']', js)
    assert js_keys, "Expected static t() calls in app.js"
    for key in js_keys:
        assert key in en, f"Missing JS i18n key in en.json: {key}"


def test_builtin_profiles_rules_scans_and_wizard_keys_exist():
    en = load_all(force_reload=True)["en"]
    for prof in create_builtin_profiles():
        for suffix in ("name", "desc", "target"):
            k = f"profile.{prof.id}.{suffix}"
            assert k in en, f"Missing profile key: {k}"
        for suffix in ("summary", "hints"):
            k = f"wizard.result.{prof.id}.{suffix}"
            assert k in en, f"Missing wizard result key: {k}"
        for rule in prof.rules:
            k = f"rule.{rule.id}"
            assert k in en, f"Missing rule key: {k}"
        for action in prof.switch_scan.actions:
            k = f"scan.{action.id}"
            assert k in en, f"Missing scan key: {k}"


def test_python_announce_and_status_keys_exist():
    en = load_all(force_reload=True)["en"]
    for py_file in PACKAGE_DIR.rglob("*.py"):
        src = py_file.read_text(encoding="utf-8")
        for key in re.findall(r'"(announce\.[a-z_]+)"', src):
            assert key in en, f"Missing announce key {key} referenced in {py_file}"

    for code in ("ready", "running", "missing_deps", "no_camera", "model_missing", "model_downloading", "error"):
        assert f"input.status.{code}" in en
    for code in ("ready", "windows_only", "missing_driver"):
        assert f"output.status.{code}" in en
    for diag_id in (
        "python",
        "data_dir_writable",
        "web_assets",
        "locales",
        "face_deps",
        "face_model_load",
        "camera",
        "microphone",
        "tts_voices",
        "send_input",
        "vgamepad",
    ):
        assert f"diag.{diag_id}" in en
