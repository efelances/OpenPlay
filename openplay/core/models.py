"""Core data models for OpenPlay Access."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SupportedLanguage = Literal["en", "tr", "de", "es"]
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "tr", "de", "es")


def normalize_language(value: str | None) -> str:
    """Normalize locale strings like 'tr-TR' or 'en_US' to supported two-letter codes."""
    if not value:
        return "en"
    short = value.strip().replace("_", "-").split("-")[0].lower()
    return short if short in SUPPORTED_LANGUAGES else "en"


class ActionMode(str, Enum):
    """How a digital trigger maps to a game output."""

    PRESS = "press"        # Active while signal >= threshold
    TOGGLE = "toggle"      # Flips on/off on each rising edge (great for holding W/Shift)
    PULSE = "pulse"        # Fires a short tap on rising edge
    MACRO = "macro"        # Fires a sequence of targets on rising edge
    ANALOG = "analog"      # Maps continuous signal [-1, 1] to mouse or stick axis


class OutputType(str, Enum):
    """Supported virtual output channels."""

    KEYBOARD = "keyboard"
    MOUSE_BUTTON = "mouse_button"
    MOUSE_AXIS = "mouse_axis"
    GAMEPAD_BUTTON = "gamepad_button"
    GAMEPAD_AXIS = "gamepad_axis"


class InputSignal(BaseModel):
    """Normalized signal emitted by any InputProvider."""

    source: str = Field(..., description="Provider name, e.g. face_tracker, audio_trigger, switch")
    channel: str = Field(..., description="Signal channel, e.g. head_yaw, mouth_open, audio_level")
    value: float = Field(..., description="Normalized value: [-1.0, 1.0] for axes, [0.0, 1.0] for triggers")
    timestamp: float = Field(default=0.0)


class OutputCommand(BaseModel):
    """Normalized command sent to OutputAdapters."""

    output_type: OutputType
    target: str = Field(..., description="Key/button/axis identifier, e.g. 'w', 'space', 'left', 'lx'")
    value: float = Field(default=0.0, description="1.0=pressed, 0.0=released, or [-1.0, 1.0] for analog")
    label: str = Field(default="", description="Human-readable label or key")


class MappingRule(BaseModel):
    """Maps a single input channel to a game output with accessibility tuning."""

    id: str
    name: str
    source: str
    channel: str
    mode: ActionMode = ActionMode.PRESS
    output_type: OutputType = OutputType.KEYBOARD
    target: str = "space"
    macro_targets: list[str] = Field(default_factory=list)
    threshold: float = Field(default=0.55, ge=0.05, le=0.99)
    deadzone: float = Field(default=0.12, ge=0.0, le=0.6)
    sensitivity: float = Field(default=1.0, ge=0.1, le=5.0)
    smoothing: float = Field(default=0.35, ge=0.0, le=0.95)
    invert: bool = False
    cooldown_ms: int = Field(default=250, ge=0, le=5000)
    pulse_ms: int = Field(default=120, ge=20, le=2000)
    enabled: bool = True
    announce_tts: bool = True


class ScanAction(BaseModel):
    """Single action item in Switch Scanning mode for severe motor disabilities."""

    id: str
    label: str
    output_type: OutputType = OutputType.KEYBOARD
    target: str
    mode: ActionMode = ActionMode.PULSE
    pulse_ms: int = 180


class SwitchScanConfig(BaseModel):
    """Configuration for single-switch scanning mode."""

    enabled: bool = False
    trigger_channel: str = "switch_1"
    interval_ms: int = Field(default=1400, ge=400, le=6000)
    announce_items: bool = True
    actions: list[ScanAction] = Field(default_factory=list)


class AccessibilitySettings(BaseModel):
    """UI and sensory accessibility preferences."""

    high_contrast: bool = False
    large_text: bool = False
    tts_enabled: bool = True
    audio_cues: bool = True
    language: str = "en"
    onboarding_done: bool = False
    swap_eyes: bool = False
    safe_test_mode: bool = True  # Always forced True on startup for safety
    camera_index: int = Field(default=0, ge=0, le=16)
    low_light_camera_mode: bool = True
    mic_device_index: int | None = None
    mic_gain: float = Field(default=4.0, ge=1.0, le=15.0)
    mic_noise_suppression: bool = True
    mic_auto_gain: bool = True
    mic_noise_floor: float = Field(default=0.0, ge=0.0, le=0.5)

    @field_validator("language", mode="before")
    @classmethod
    def _validate_language(cls, v: Any) -> str:
        return normalize_language(str(v) if v is not None else "en")


class Profile(BaseModel):
    """Complete accessibility profile for a user or game."""

    id: str
    name: str
    description: str
    target_group: str
    active_inputs: list[str] = Field(default_factory=list)
    rules: list[MappingRule] = Field(default_factory=list)
    switch_scan: SwitchScanConfig = Field(default_factory=SwitchScanConfig)
    metadata: dict[str, Any] = Field(default_factory=dict)
