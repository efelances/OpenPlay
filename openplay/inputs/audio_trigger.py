"""Non-verbal acoustic / breath / sound-level trigger using microphone input."""

from __future__ import annotations

import time

from openplay.inputs.base import InputProvider, SignalCallback

try:
    import numpy as np  # type: ignore
    import sounddevice as sd  # type: ignore

    _HAS_AUDIO_DEPS = True
except Exception:
    np = None
    sd = None
    _HAS_AUDIO_DEPS = False


class AudioTriggerProvider(InputProvider):
    """Detects sound bursts, puffs, or clucks without requiring spoken words."""

    name = "audio_trigger"

    def __init__(self, gain: float = 4.0) -> None:
        super().__init__()
        self.gain = gain
        self._stream = None

    def is_available(self) -> bool:
        return _HAS_AUDIO_DEPS

    def status_code(self) -> str:
        if not _HAS_AUDIO_DEPS:
            return "missing_deps"
        if self._last_error:
            return "error"
        return "running" if self._running else "ready"

    def start(self, callback: SignalCallback) -> bool:
        if not super().start(callback):
            return False
        self._last_error = ""
        try:
            self._stream = sd.InputStream(
                channels=1,
                samplerate=16000,
                blocksize=512,
                callback=self._audio_callback,
            )
            self._stream.start()
            return True
        except Exception as exc:
            self._last_error = str(exc)
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
        if not self._running or np is None:
            return
        rms = float(np.sqrt(np.mean(indata**2)))
        level = max(0.0, min(1.0, rms * self.gain))
        now = time.monotonic()
        self.emit("audio_level", level, now)
        self.emit("audio_trigger", level, now)
        self.emit("audio_loud", level, now)
        self.emit("switch_audio", 1.0 if level >= 0.55 else 0.0, now)
