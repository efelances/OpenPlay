"""Always-available keyboard, single-switch, and simulator input provider."""

from __future__ import annotations

import time

from openplay.core.models import InputSignal
from openplay.inputs.base import InputProvider


class KeyboardAssistProvider(InputProvider):
    """Receives accessible switch/assist/simulated signals from UI or hotkeys."""

    name = "keyboard_assist"

    def is_available(self) -> bool:
        return True

    def status_code(self) -> str:
        return "running" if self._running else "ready"

    def trigger_channel(self, channel: str, value: float, source_override: str | None = None) -> None:
        """Inject a normalized signal (used for switch buttons, one-hand assists, or testing)."""
        if not self._callback:
            return
        self._callback(
            InputSignal(
                source=source_override or self.name,
                channel=channel,
                value=float(value),
                timestamp=time.monotonic(),
            )
        )
