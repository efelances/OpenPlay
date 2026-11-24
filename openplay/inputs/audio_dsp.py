"""Pure NumPy microphone DSP: band-pass filtering, ambient calibration, noise gate, and AGC."""

from __future__ import annotations

import time
from typing import Any

try:
    import numpy as np  # type: ignore
except Exception:
    np = None


class AudioDSPProcessor:
    """Cleans noisy/quiet microphone audio using pure NumPy DSP."""

    def __init__(
        self,
        samplerate: float = 16000.0,
        gain: float = 4.0,
        noise_suppression: bool = True,
        auto_gain: bool = True,
        noise_floor: float = 0.0,
    ) -> None:
        self.samplerate = float(samplerate)
        self.gain = float(gain)
        self.noise_suppression = bool(noise_suppression)
        self.auto_gain = bool(auto_gain)
        self.noise_floor = float(noise_floor)

        self._peak_rms: float = 0.12
        self._agc_mult: float = 1.0
        self._cal_end_ts: float = 0.0
        self._cal_samples: list[float] = []
        self._cal_active: bool = False

    def start_noise_calibration(self, duration_sec: float = 1.5, now: float | None = None) -> None:
        ts = time.monotonic() if now is None else float(now)
        self._cal_samples = []
        self._cal_active = True
        self._cal_end_ts = ts + max(0.2, float(duration_sec))

    def process_block(self, samples: Any, now: float | None = None) -> tuple[float, bool]:
        """Process one audio frame block and return (normalized_level [0..1], calibration_finished)."""
        if np is None:
            return 0.0, False

        x = np.asarray(samples, dtype=np.float32).reshape(-1)
        if x.size == 0:
            return 0.0, False

        # DC offset removal
        x = x - float(np.mean(x))
        n = int(x.size)

        if self.noise_suppression and n >= 16:
            win = np.hanning(n).astype(np.float32)
            win_rms = float(np.sqrt(np.mean(win * win)))
            if win_rms > 1e-6:
                xw = x * (win / win_rms)
            else:
                xw = x
            spec = np.fft.rfft(xw)
            freqs = np.fft.rfftfreq(n, d=1.0 / max(1000.0, self.samplerate))

            w = np.full(spec.shape, 2.0, dtype=np.float32)
            w[0] = 0.0
            if n % 2 == 0 and w.size > 1:
                w[-1] = 1.0

            mask = (freqs >= 140.0) & (freqs <= 4200.0)
            power = float(np.sum(w[mask] * (np.abs(spec[mask]) ** 2)))
            rms = float(np.sqrt(max(0.0, power / (n * n))))
        else:
            rms = float(np.sqrt(np.mean(x * x)))

        ts = time.monotonic() if now is None else float(now)
        if self._cal_active:
            self._cal_samples.append(rms)
            if ts >= self._cal_end_ts:
                p85 = float(np.percentile(self._cal_samples, 85)) if self._cal_samples else 0.005
                self.noise_floor = max(0.002, min(0.5, p85 * 1.35))
                self._cal_active = False
                return 0.0, True
            return 0.0, False

        if self.noise_suppression:
            if self.noise_floor <= 0.0:
                self.noise_floor = min(rms, 0.05)
            elif rms < self.noise_floor:
                self.noise_floor += (rms - self.noise_floor) * 0.08
            elif rms < self.noise_floor * 1.45:
                self.noise_floor += (rms - self.noise_floor) * 0.004
            gate = self.noise_floor * 1.25
        else:
            gate = 0.0

        clean_rms = max(0.0, rms - gate)

        if self.auto_gain:
            if clean_rms > 0.012:
                self._peak_rms += (clean_rms - self._peak_rms) * 0.08
            else:
                self._peak_rms += (0.12 - self._peak_rms) * 0.001
            self._agc_mult = max(0.75, min(3.2, 0.18 / max(0.025, self._peak_rms)))
        else:
            self._agc_mult = 1.0

        level = max(0.0, min(1.0, clean_rms * self.gain * self._agc_mult))
        return float(level), False

    def get_telemetry(self) -> dict[str, Any]:
        return {
            "samplerate": int(self.samplerate),
            "noise_floor": round(self.noise_floor, 4),
            "calibrating_noise": self._cal_active,
            "effective_gain": round(self.gain * self._agc_mult, 2),
        }
