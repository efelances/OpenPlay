"""Centralized localization loader and formatter."""

from __future__ import annotations

import json
from typing import Any

from openplay.core.models import SUPPORTED_LANGUAGES, normalize_language
from openplay.paths import LOCALES_DIR

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "tr": "Türkçe",
    "de": "Deutsch",
    "es": "Español",
}

_CACHE: dict[str, dict[str, Any]] = {}


def load_all(force_reload: bool = False) -> dict[str, dict[str, Any]]:
    """Load and cache all locale JSON dictionaries."""
    if _CACHE and not force_reload:
        return _CACHE

    loaded: dict[str, dict[str, Any]] = {}
    for lang in SUPPORTED_LANGUAGES:
        path = LOCALES_DIR / f"{lang}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                loaded[lang] = data
    _CACHE.clear()
    _CACHE.update(loaded)
    return _CACHE


def get_dict(lang: str | None) -> dict[str, Any]:
    """Return locale dictionary merged on top of English fallback."""
    all_locales = load_all()
    code = normalize_language(lang)
    en_dict = dict(all_locales.get("en", {}))
    if code == "en" or code not in all_locales:
        return en_dict
    merged = dict(en_dict)
    merged.update(all_locales[code])
    return merged


def t(lang: str | None, key: str, **params: Any) -> str:
    """Translate a key into the requested language and interpolate parameters."""
    d = get_dict(lang)
    raw = d.get(key)
    if raw is None:
        return key
    text = raw if isinstance(raw, str) else str(raw)
    if not params:
        return text

    resolved: dict[str, Any] = {}
    for k, v in params.items():
        if k.endswith("_key") and isinstance(v, str):
            resolved[k[:-4]] = t(lang, v)
        else:
            resolved[k] = v

    try:
        return text.format(**resolved)
    except (KeyError, ValueError):
        return text
