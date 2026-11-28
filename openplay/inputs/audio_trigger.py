"""Non-verbal acoustic / breath / sound-level trigger using microphone input."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from openplay.inputs.audio_dsp import AudioDSPProcessor
from openplay.inputs.base import InputProvider, SignalCallback

try:
    import sounddevice as sd  # type: ignore

    _HAS_AUDIO_DEPS = True
except Exception:
    sd = None
    _HAS_AUDIO_DEPS = False


class AudioTriggerProvider(InputProvider):
    """Detects sound bursts, puffs, or clucks without requiring spoken words."""

    name = "audio_trigger"

    def __init__(self, gain: float = 4.0) -> None:
        super().__init__()
        self.device_index: int | None = None
        self.gain: float = gain
        self.noise_suppression: bool = True
        self.auto_gain: bool = True
        self.noise_floor: float = 0.0
        self.on_noise_calibrated: Callable[[float], None] | None = None
        self._active_device_name: str = ""
        self._stream = None
        self._dsp = AudioDSPProcessor(
            samplerate=16000.0,
            gain=gain,
            noise_suppression=True,
            auto_gain=True,
            noise_floor=0.0,
        )

    def is_available(self) -> bool:
        return _HAS_AUDIO_DEPS

    def status_code(self) -> str:
        if not _HAS_AUDIO_DEPS:
            return "missing_deps"
        if self._last_error:
            return "error"
        return "running" if self._running else "ready"

    def apply_config(
        self,
        gain: float | None = None,
        noise_suppression: bool | None = None,
        auto_gain: bool | None = None,
        noise_floor: float | None = None,
    ) -> None:
        """Update live DSP tuning parameters without restarting the audio stream."""
        if gain is not None:
            self.gain = float(gain)
            self._dsp.gain = self.gain
        if noise_suppression is not None:
            self.noise_suppression = bool(noise_suppression)
            self._dsp.noise_suppression = self.noise_suppression
        if auto_gain is not None:
            self.auto_gain = bool(auto_gain)
            self._dsp.auto_gain = self.auto_gain
        if noise_floor is not None:
            self.noise_floor = float(noise_floor)
            self._dsp.noise_floor = self.noise_floor

    def start_noise_calibration(self, duration_sec: float = 1.5) -> None:
        self._dsp.start_noise_calibration(duration_sec=duration_sec)

    def list_microphones(self) -> list[dict[str, Any]]:
        """List available microphone input devices, preferring the default host API."""
        if sd is None:
            return []
        try:
            devs = sd.query_devices()
        except Exception:
            return []

        default_hostapi = None
        try:
            ha = sd.default.hostapi
            if isinstance(ha, int) and ha >= 0:
                default_hostapi = ha
        except Exception:
            default_hostapi = None

        preferred: list[dict[str, Any]] = []
        all_inputs: list[dict[str, Any]] = []
        for idx, d in enumerate(devs):
            if int(d.get("max_input_channels", 0) or 0) <= 0:
                continue
            item = {
                "index": idx,
                "name": str(d.get("name") or f"Microphone {idx}"),
                "default_samplerate": int(d.get("default_samplerate") or 44100),
            }
            all_inputs.append(item)
            if default_hostapi is None or d.get("hostapi") == default_hostapi:
                preferred.append(item)

        return preferred or all_inputs

    def get_telemetry(self) -> dict[str, Any]:
        info = self._dsp.get_telemetry()
        info["device_index"] = self.device_index
        info["device_name"] = self._active_device_name
        return info

    def start(self, callback: SignalCallback) -> bool:
        if not super().start(callback):
            return False
        self._last_error = ""

        dev_default_sr = 0
        dev_name = ""
        try:
            if self.device_index is not None:
                dev_info = sd.query_devices(self.device_index, kind="input")
            else:
                dev_info = sd.query_devices(kind="input")
            if isinstance(dev_info, dict):
                dev_default_sr = int(dev_info.get("default_samplerate") or 0)
                dev_name = str(dev_info.get("name") or "")
        except Exception:
            dev_default_sr = 0

        candidates: list[int] = []
        for sr in (dev_default_sr, 48000, 44100, 16000):
            if sr > 0 and sr not in candidates:
                candidates.append(sr)

        self.apply_config(
            gain=self.gain,
            noise_suppression=self.noise_suppression,
            auto_gain=self.auto_gain,
            noise_floor=self.noise_floor,
        )

        last_exc: Exception | None = None
        for sr in candidates:
            blocksize = max(256, int(sr * 0.032))
            stream = None
            try:
                self._dsp.samplerate = float(sr)
                stream = sd.InputStream(
                    device=self.device_index,
                    channels=1,
                    samplerate=sr,
                    blocksize=blocksize,
                    callback=self._audio_callback,
                )
                stream.start()
                self._stream = stream
                self._active_device_name = dev_name
                return True
            except Exception as exc:
                last_exc = exc
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass

        self._last_error = str(last_exc) if last_exc else "Could not open microphone"
        self._running = False
        return False

    def stop(self) -> None:
        super().stop()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _audio_callback(self, indata, _frames, _time_info, _status) -> None:
        if not self._running:
            return
        now = time.monotonic()
        self._dsp.gain = self.gain
        self._dsp.noise_suppression = self.noise_suppression
        self._dsp.auto_gain = self.auto_gain

        level, finished = self._dsp.process_block(indata, now=now)
        if finished:
            self.noise_floor = self._dsp.noise_floor
            cb = self.on_noise_calibrated
            if cb is not None:
                threading.Thread(target=cb, args=(self.noise_floor,), daemon=True).start()

        self.emit("audio_level", level, now)
        self.emit("audio_trigger", level, now)
        self.emit("audio_loud", level, now)
        self.emit("switch_audio", level, now)
