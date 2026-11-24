"""Low-light frame enhancement and dropped-frame smoothing for budget webcams."""

from __future__ import annotations

from typing import Any

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:
    cv2 = None
    np = None

_ANALOG_CHANNELS = frozenset({"head_yaw", "head_pitch", "gaze_x", "gaze_y"})
_LUT_CACHE: dict[float, Any] = {}


def assess_brightness(bgr_frame: Any) -> float:
    """Return subsampled mean brightness in [0.0, 255.0]."""
    if bgr_frame is None or np is None:
        return 0.0
    try:
        arr = np.asarray(bgr_frame)
        if arr.size == 0:
            return 0.0
        sub = arr[::4, ::4]
        return float(np.mean(sub))
    except Exception:
        return 0.0


def light_quality_code(brightness: float) -> str:
    """Return language-neutral lighting quality code."""
    if brightness < 55.0:
        return "very_dark"
    if brightness < 95.0:
        return "low"
    if brightness > 225.0:
        return "overexposed"
    return "good"


def _get_gamma_lut(gamma: float) -> Any:
    key = round(gamma, 2)
    lut = _LUT_CACHE.get(key)
    if lut is None and np is not None:
        lut = np.clip(((np.arange(256, dtype=np.float32) / 255.0) ** key) * 255.0, 0, 255).astype(np.uint8)
        _LUT_CACHE[key] = lut
    return lut


def enhance_low_light_frame(bgr_frame: Any, enabled: bool = True) -> tuple[Any, float, bool]:
    """Brighten and denoise dark webcam frames using adaptive gamma, CLAHE, and optional blur."""
    brightness = assess_brightness(bgr_frame)
    if not enabled or brightness >= 115.0 or cv2 is None or np is None:
        return bgr_frame, brightness, False

    arr = np.asarray(bgr_frame)
    if arr.size == 0:
        return bgr_frame, brightness, False

    gamma = max(0.45, min(1.0, 0.45 + (brightness / 115.0) * 0.55))
    lut = _get_gamma_lut(gamma)
    gained = cv2.LUT(arr, lut)

    ycrcb = cv2.cvtColor(gained, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    y_eq = clahe.apply(y)
    enhanced = cv2.cvtColor(cv2.merge((y_eq, cr, cb)), cv2.COLOR_YCrCb2BGR)

    if brightness < 75.0:
        enhanced = cv2.GaussianBlur(enhanced, (3, 3), 0)

    return enhanced, brightness, True


class SignalHoldTracker:
    """Smooths brief face-tracking dropouts without leaving digital triggers stuck."""

    def __init__(self, grace_sec: float = 0.25, decay: float = 0.85) -> None:
        self.grace_sec = grace_sec
        self.decay = decay
        self._last_seen: float | None = None
        self._last_signals: dict[str, float] = {}
        self._zeroed: bool = False

    def on_detected(self, signals: dict[str, float], now: float) -> dict[str, float]:
        self._last_signals = dict(signals)
        self._last_seen = now
        self._zeroed = False
        return dict(signals)

    def on_missed(self, now: float) -> tuple[dict[str, float], bool]:
        if self._last_seen is None:
            return {}, False

        if now - self._last_seen <= self.grace_sec:
            held: dict[str, float] = {}
            for k, v in self._last_signals.items():
                if k in _ANALOG_CHANNELS:
                    held[k] = v * self.decay
                else:
                    held[k] = 0.0
            self._last_signals = dict(held)
            return held, True

        if not self._zeroed:
            self._zeroed = True
            zeros = {k: 0.0 for k in self._last_signals}
            self._last_signals.clear()
            return zeros, False

        return {}, False
