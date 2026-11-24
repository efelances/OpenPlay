"""Base interface for all accessibility input providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from openplay.core.models import InputSignal

SignalCallback = Callable[[InputSignal], None]


class InputProvider(ABC):
    """Abstract base class for modular input sources (camera, mic, switch, keyboard)."""

    name: str = "base"

    def __init__(self) -> None:
        self._running: bool = False
        self._callback: SignalCallback | None = None
        self._last_error: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if dependencies and hardware are ready."""

    @abstractmethod
    def status_code(self) -> str:
        """Language-neutral status code (e.g. ready, running, missing_deps, no_camera)."""

    def start(self, callback: SignalCallback) -> bool:
        if not self.is_available():
            return False
        self._callback = callback
        self._running = True
        return True

    def stop(self) -> None:
        self._running = False
        self._callback = None

    @property
    def is_running(self) -> bool:
        return self._running

    def emit(self, channel: str, value: float, timestamp: float = 0.0) -> None:
        if self._callback:
            self._callback(
                InputSignal(
                    source=self.name,
                    channel=channel,
                    value=float(value),
                    timestamp=timestamp,
                )
            )

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.is_available(),
            "running": self.is_running,
            "status_code": self.status_code(),
            "detail": self._last_error,
        }
