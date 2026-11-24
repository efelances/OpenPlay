"""Base interface for virtual game output adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from openplay.core.models import OutputCommand


class OutputAdapter(ABC):
    """Abstract base class for sending virtual game inputs to the OS."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this output adapter can run on the current OS."""

    @abstractmethod
    def status_code(self) -> str:
        """Language-neutral adapter status code."""

    @abstractmethod
    def send(self, command: OutputCommand) -> bool:
        """Apply a single OutputCommand. Returns True if handled."""

    def detail(self) -> str:
        return ""

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.is_available(),
            "status_code": self.status_code(),
            "detail": self.detail(),
        }
