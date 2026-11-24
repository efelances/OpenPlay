"""Native Windows SAPI5 + OneCore TTS worker (pywin32)."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
from typing import Any

from openplay.core.models import normalize_language

logger = logging.getLogger(__name__)

_VOICE_CATEGORIES = (
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices",
)

_PRIMARY_LANG_MAP: dict[int, str] = {
    0x1F: "tr",
    0x09: "en",
    0x07: "de",
    0x0A: "es",
}


def _parse_voice_lang(raw_lang: str) -> str | None:
    if not raw_lang:
        return None
    first = raw_lang.split(";")[0].strip()
    try:
        lang_id = int(first, 16)
    except ValueError:
        return None
    return _PRIMARY_LANG_MAP.get(lang_id & 0x3FF)


class NativeTTS:
    """Thread-safe Windows SAPI speech synthesizer supporting OneCore and Desktop voices."""

    def __init__(self) -> None:
        self._disabled = os.environ.get("OPENPLAY_DISABLE_TTS") == "1" or sys.platform != "win32"
        self._enabled = True
        self._queue: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._ready = threading.Event()
        self._voices: dict[str, Any] = {}
        self._langs: set[str] = set()

        if self._disabled:
            self._ready.set()
            return

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    def available_languages(self, timeout: float = 3.0) -> set[str]:
        self._ready.wait(timeout=timeout)
        return set(self._langs)

    def speak(self, lang: str, text: str) -> None:
        if self._disabled or not self._enabled or not text:
            return
        code = normalize_language(lang)
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._queue.put((code, text))

    def stop(self) -> None:
        if self._disabled:
            return
        self._queue.put(None)

    def _worker(self) -> None:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore

        pythoncom.CoInitialize()
        voice = None
        try:
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Rate = 1
            for cat_path in _VOICE_CATEGORIES:
                try:
                    category = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
                    category.SetId(cat_path, False)
                    for token in category.EnumerateTokens():
                        try:
                            lang_attr = token.GetAttribute("Language")
                        except Exception:
                            lang_attr = ""
                        code = _parse_voice_lang(lang_attr)
                        if code and code not in self._voices:
                            self._voices[code] = token
                            self._langs.add(code)
                except Exception as exc:
                    logger.debug("Voice category scan failed (%s): %s", cat_path, exc)
        except Exception as exc:
            logger.warning("Failed to initialize Windows SAPI TTS: %s", exc)
            voice = None
        finally:
            self._ready.set()

        current_lang: str | None = None
        while True:
            item = self._queue.get()
            if item is None:
                break
            lang, text = item
            if voice is None or not self._enabled:
                continue
            try:
                if lang != current_lang:
                    token = self._voices.get(lang) or self._voices.get("en")
                    if token is not None:
                        voice.Voice = token
                    current_lang = lang
                # 3 = SVSFlagsAsync (1) | SVSFPurgeBeforeSpeak (2)
                voice.Speak(text, 3)
            except Exception as exc:
                logger.debug("TTS speak error: %s", exc)

        pythoncom.CoUninitialize()
