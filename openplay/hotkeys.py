"""Windows global F12 emergency-stop and accessibility assist hotkey monitor."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable

logger = logging.getLogger(__name__)

_VK_F12 = 0x7B

ASSIST_HOTKEYS: dict[int, str] = {
    0x75: "assist_toggle_walk",
    0x76: "assist_toggle_sprint",
    0x77: "assist_macro_1",
}

ASSIST_SHORTCUTS: dict[str, str] = {
    "assist_toggle_walk": "F6",
    "assist_toggle_sprint": "F7",
    "assist_macro_1": "F8",
}


class GlobalHotkeyMonitor:
    """Polls global F12 emergency stop and F6-F8 assist hotkeys even inside fullscreen games."""

    def __init__(
        self,
        on_emergency: Callable[[], None],
        on_channel: Callable[[str, float], None] | None = None,
        poll_interval: float = 0.05,
    ) -> None:
        self._on_emergency = on_emergency
        self._on_channel = on_channel
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

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        was_down = False
        assist_down: dict[int, bool] = {vk: False for vk in ASSIST_HOTKEYS}
        while not self._stop_event.is_set():
            try:
                is_down = bool(user32.GetAsyncKeyState(_VK_F12) & 0x8000)
                if is_down and not was_down:
                    logger.info("Global F12 emergency stop triggered")
                    self._on_emergency()
                was_down = is_down

                if self._on_channel is not None:
                    for vk, channel in ASSIST_HOTKEYS.items():
                        pressed = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                        prev = assist_down[vk]
                        if pressed and not prev:
                            self._on_channel(channel, 1.0)
                        elif not pressed and prev:
                            self._on_channel(channel, 0.0)
                        assist_down[vk] = pressed
            except Exception as exc:
                logger.debug("Hotkey poll error: %s", exc)
            self._stop_event.wait(self._poll_interval)
