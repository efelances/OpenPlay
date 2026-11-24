"""Windows global F12 emergency-stop hotkey monitor."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable

logger = logging.getLogger(__name__)

_VK_F12 = 0x7B


class GlobalHotkeyMonitor:
    """Polls global F12 key state so emergency stop works even inside fullscreen games."""

    def __init__(self, on_emergency: Callable[[], None], poll_interval: float = 0.05) -> None:
        self._on_emergency = on_emergency
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if sys.platform != "win32":
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _poll_loop(self) -> None:
        import ctypes

        user32 = ctypes.windll.user32
        was_down = False
        while not self._stop_event.is_set():
            try:
                is_down = bool(user32.GetAsyncKeyState(_VK_F12) & 0x8000)
                if is_down and not was_down:
                    logger.info("Global F12 emergency stop triggered")
                    self._on_emergency()
                was_down = is_down
            except Exception as exc:
                logger.debug("Hotkey poll error: %s", exc)
            self._stop_event.wait(self._poll_interval)
