"""Runtime coordinator for inputs, mapping engine, outputs, settings, and WebSockets."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import HTTPException, WebSocket

from openplay import __version__
from openplay.core.mapping_engine import MappingEngine
from openplay.core.models import (
    AccessibilitySettings,
    ActionMode,
    InputSignal,
    OutputCommand,
    OutputType,
)
from openplay.core.profile_manager import ProfileManager
from openplay.core.tts import NativeTTS
from openplay.core.wizard import WizardAnswers, recommend_setup
from openplay.i18n import t
from openplay.inputs.audio_trigger import AudioTriggerProvider
from openplay.inputs.base import InputProvider
from openplay.inputs.face_tracker import FaceTrackerProvider
from openplay.inputs.keyboard_assist import KeyboardAssistProvider
from openplay.outputs.base import OutputAdapter
from openplay.outputs.virtual_gamepad import VirtualGamepadAdapter
from openplay.outputs.windows_input import WindowsInputAdapter
from openplay.paths import get_data_dir
from openplay.settings_store import SettingsStore


class AccessRuntime:
    """Coordinates inputs, mapping engine, outputs, persistent settings, and WebSocket broadcasts."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = get_data_dir(data_dir)
        self.store = SettingsStore(self.data_dir / "settings.json")
        stored = self.store.load()

        self.settings = AccessibilitySettings.model_validate(stored["settings"])
        self.profile_manager = ProfileManager(stored.get("overrides"))

        active_id = stored.get("active_profile_id")
        default_profile = self.profile_manager.get(active_id) or self.profile_manager.list_profiles()[0]

        self.tts = NativeTTS()
        self.tts.enabled = self.settings.tts_enabled

        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set[WebSocket] = set()
        self._recent_outputs: deque[dict[str, Any]] = deque(maxlen=25)
        self._latest_signals: dict[str, float] = {}
        self._signals_dirty = False
        self._last_telemetry_ts = 0.0
        self._target_mouse_x = 0.0
        self._target_mouse_y = 0.0
        self._cur_mouse_x = 0.0
        self._cur_mouse_y = 0.0
        self._last_mouse_ts = 0.0
        self._mouse_pixels_per_sec = 900.0

        self.engine = MappingEngine(
            profile=default_profile,
            on_announcement=self._on_announcement,
        )
        self.engine.set_calibration_offsets(stored.get("calibration") or {})

        self.keyboard_assist = KeyboardAssistProvider()
        self.face_tracker = FaceTrackerProvider(
            camera_index=self.settings.camera_index,
            data_dir=self.data_dir,
        )
        self.face_tracker.swap_eyes = self.settings.swap_eyes
        self.face_tracker.low_light_mode = self.settings.low_light_camera_mode
        self.audio_trigger = AudioTriggerProvider(gain=self.settings.mic_gain)
        self.audio_trigger.device_index = self.settings.mic_device_index
        self.audio_trigger.apply_config(
            gain=self.settings.mic_gain,
            noise_suppression=self.settings.mic_noise_suppression,
            auto_gain=self.settings.mic_auto_gain,
            noise_floor=self.settings.mic_noise_floor,
        )
        self.audio_trigger.on_noise_calibrated = self._on_mic_noise_calibrated

        self.inputs: dict[str, InputProvider] = {
            "face_tracker": self.face_tracker,
            "audio_trigger": self.audio_trigger,
            "keyboard_assist": self.keyboard_assist,
        }
        self._win_adapter = WindowsInputAdapter()
        self.outputs: list[OutputAdapter] = [
            self._win_adapter,
            VirtualGamepadAdapter(),
        ]

        # Always keep keyboard/switch assist active
        self.keyboard_assist.start(self.handle_signal)

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def shutdown(self) -> None:
        self.emergency_stop()
        for provider in self.inputs.values():
            provider.stop()
        self.tts.stop()

    def _save_state(self) -> None:
        with self._lock:
            payload = {
                "settings": self.settings.model_dump(),
                "active_profile_id": self.engine.profile.id,
                "calibration": self.engine.get_calibration_offsets(),
                "overrides": self.profile_manager.get_overrides(),
            }
        self.store.save(payload)

    def handle_signal(self, signal: InputSignal) -> None:
        with self._lock:
            self._latest_signals[signal.channel] = round(signal.value, 3)
            self._signals_dirty = True
            commands = self.engine.process_signal(signal)
        self._dispatch_outputs(commands)

    def flush_signals(self) -> None:
        """Broadcast batched latest signal values at ~15 Hz and telemetry every ~0.5s."""
        now = time.monotonic()
        with self._lock:
            dirty = self._signals_dirty
            self._signals_dirty = False
            values = dict(self._latest_signals) if dirty else None
            send_telem = (
                (self.face_tracker.is_running or self.audio_trigger.is_running)
                and (now - self._last_telemetry_ts >= 0.5)
            )
            if send_telem:
                self._last_telemetry_ts = now

        if values is not None:
            self._broadcast_threadsafe({"type": "signals", "values": values})
        if send_telem:
            self._broadcast_threadsafe(
                {
                    "type": "telemetry",
                    "telemetry": {
                        "camera": self.face_tracker.get_telemetry(),
                        "microphone": self.audio_trigger.get_telemetry(),
                    },
                }
            )

    def _reset_mouse_pump_locked(self) -> None:
        self._target_mouse_x = 0.0
        self._target_mouse_y = 0.0
        self._cur_mouse_x = 0.0
        self._cur_mouse_y = 0.0
        self._win_adapter.reset_mouse_remainder()

    def step_mouse(self, dt: float) -> None:
        """High-frequency (100 Hz) smooth mouse movement pump."""
        now = time.monotonic()
        with self._lock:
            if self.settings.safe_test_mode:
                self._reset_mouse_pump_locked()
                return
            if now - self._last_mouse_ts > 0.30:
                self._target_mouse_x = 0.0
                self._target_mouse_y = 0.0

            blend = min(1.0, dt * 18.0)
            self._cur_mouse_x += (self._target_mouse_x - self._cur_mouse_x) * blend
            self._cur_mouse_y += (self._target_mouse_y - self._cur_mouse_y) * blend
            if abs(self._cur_mouse_x) < 1e-3:
                self._cur_mouse_x = 0.0
            if abs(self._cur_mouse_y) < 1e-3:
                self._cur_mouse_y = 0.0
            vx = self._cur_mouse_x
            vy = self._cur_mouse_y

        if vx != 0.0 or vy != 0.0:
            self._win_adapter.send_mouse_delta_float(
                vx * self._mouse_pixels_per_sec * dt,
                vy * self._mouse_pixels_per_sec * dt,
            )

    def tick(self) -> None:
        with self._lock:
            prev_idx = self.engine.get_scanner_snapshot()["current_index"]
            commands = self.engine.tick()
            scanner = self.engine.get_scanner_snapshot()
        if commands:
            self._dispatch_outputs(commands)
        if scanner["enabled"] and scanner["current_index"] != prev_idx:
            self._broadcast_threadsafe({"type": "scanner", "scanner": scanner})

    def switch_profile(self, profile_id: str, apply_metadata: bool = True) -> dict[str, Any]:
        profile = self.profile_manager.get(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")
        with self._lock:
            release_cmds = self.engine.set_profile(profile)
            self._reset_mouse_pump_locked()
            if apply_metadata:
                if profile.metadata.get("recommended_high_contrast"):
                    self.settings.high_contrast = True
                if profile.metadata.get("recommended_tts"):
                    self.settings.tts_enabled = True
                    self.tts.enabled = True
        self._dispatch_outputs(release_cmds)
        self._save_state()
        snapshot = self.get_state_snapshot()
        self._broadcast_threadsafe({"type": "state", "state": snapshot})
        return snapshot

    def update_settings(self, new_settings: AccessibilitySettings) -> dict[str, Any]:
        prev_safe = self.settings.safe_test_mode
        restart_cam = False
        restart_mic = False
        with self._lock:
            cam_changed = (
                new_settings.camera_index != self.settings.camera_index
                or new_settings.low_light_camera_mode != self.settings.low_light_camera_mode
            )
            mic_changed = new_settings.mic_device_index != self.settings.mic_device_index
            self.settings = new_settings
            self.tts.enabled = new_settings.tts_enabled
            self.face_tracker.swap_eyes = new_settings.swap_eyes
            self.face_tracker.camera_index = new_settings.camera_index
            self.face_tracker.low_light_mode = new_settings.low_light_camera_mode
            self.audio_trigger.device_index = new_settings.mic_device_index
            self.audio_trigger.apply_config(
                gain=new_settings.mic_gain,
                noise_suppression=new_settings.mic_noise_suppression,
                auto_gain=new_settings.mic_auto_gain,
                noise_floor=new_settings.mic_noise_floor,
            )
            if new_settings.safe_test_mode:
                self._reset_mouse_pump_locked()
            restart_cam = cam_changed and self.face_tracker.is_running
            restart_mic = mic_changed and self.audio_trigger.is_running

        if restart_cam:
            self.face_tracker.stop()
            self.face_tracker.start(self.handle_signal)
        if restart_mic:
            self.audio_trigger.stop()
            self.audio_trigger.start(self.handle_signal)

        self._save_state()
        if prev_safe != new_settings.safe_test_mode:
            self.announce_key("announce.live_off" if new_settings.safe_test_mode else "announce.live_on")
        snapshot = self.get_state_snapshot()
        self._broadcast_threadsafe({"type": "state", "state": snapshot})
        return snapshot

    def list_devices(self) -> dict[str, Any]:
        return {
            "cameras": self.face_tracker.list_cameras(),
            "microphones": self.audio_trigger.list_microphones(),
        }

    def calibrate_mic_noise(self) -> dict[str, Any]:
        if self.audio_trigger.is_available() and not self.audio_trigger.is_running:
            self.audio_trigger.start(self.handle_signal)
        self.audio_trigger.start_noise_calibration(duration_sec=1.5)
        self.announce_key("announce.mic_calibrating")
        snapshot = self.get_state_snapshot()
        self._broadcast_threadsafe({"type": "state", "state": snapshot})
        return snapshot

    def _on_mic_noise_calibrated(self, floor: float) -> None:
        with self._lock:
            self.settings.mic_noise_floor = round(max(0.0, min(0.5, float(floor))), 4)
        self._save_state()
        self.announce_key("announce.mic_calibrated")
        snapshot = self.get_state_snapshot()
        self._broadcast_threadsafe({"type": "state", "state": snapshot})

    def toggle_input(self, name: str) -> dict[str, Any]:
        provider = self.inputs.get(name)
        if provider is None:
            raise HTTPException(status_code=404, detail="Input provider not found")
        name_key = f"input.{provider.name}.name"
        if provider.is_running:
            provider.stop()
            self.announce_key("announce.input_stopped", name_key=name_key)
        else:
            ok = provider.start(self.handle_signal)
            if ok:
                self.announce_key("announce.input_started", name_key=name_key)
            else:
                self.announce_key("announce.input_failed", name_key=name_key)
        snapshot = self.get_state_snapshot()
        self._broadcast_threadsafe({"type": "state", "state": snapshot})
        return snapshot

    def calibrate(self, channels: list[str], reset: bool = False) -> dict[str, Any]:
        with self._lock:
            if reset:
                self.engine.reset_calibration()
            else:
                for ch in channels:
                    self.engine.calibrate_channel(ch)
        self._save_state()
        self.announce_key("announce.calibration_reset" if reset else "announce.calibrated")
        snapshot = self.get_state_snapshot()
        self._broadcast_threadsafe({"type": "state", "state": snapshot})
        return snapshot

    def update_tuning(
        self,
        sensitivity: float | None = None,
        deadzone: float | None = None,
        smoothing: float | None = None,
        threshold: float | None = None,
        channel_thresholds: dict[str, float] | None = None,
        invert_x: bool | None = None,
        invert_y: bool | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            pid = self.engine.profile.id
            for rule in self.engine.profile.rules:
                fields: dict[str, Any] = {}
                if rule.mode == ActionMode.ANALOG:
                    if sensitivity is not None:
                        fields["sensitivity"] = max(0.2, min(4.0, sensitivity))
                    if deadzone is not None:
                        fields["deadzone"] = max(0.02, min(0.5, deadzone))
                    if smoothing is not None:
                        fields["smoothing"] = max(0.05, min(0.85, smoothing))
                    if invert_x is not None and rule.target == "mouse_x":
                        fields["invert"] = bool(invert_x)
                    if invert_y is not None and rule.target == "mouse_y":
                        fields["invert"] = bool(invert_y)
                else:
                    if channel_thresholds is not None:
                        ch_val = channel_thresholds.get(rule.channel)
                        if ch_val is None and rule.channel in {"audio_trigger", "audio_loud"}:
                            ch_val = channel_thresholds.get("audio_level")
                        if ch_val is not None:
                            fields["threshold"] = max(0.15, min(0.95, float(ch_val)))
                    elif threshold is not None:
                        fields["threshold"] = max(0.15, min(0.95, threshold))
                if fields:
                    self.profile_manager.set_rule_override(pid, rule.id, **fields)
            if self.engine.profile.switch_scan.enabled:
                scan_fields: dict[str, Any] = {}
                if channel_thresholds is not None:
                    face_th = channel_thresholds.get("switch_face")
                    if face_th is None:
                        face_th = channel_thresholds.get("mouth_open")
                    if face_th is not None:
                        scan_fields["face_threshold"] = max(0.15, min(0.95, float(face_th)))

                    audio_th = channel_thresholds.get("switch_audio")
                    if audio_th is None:
                        audio_th = channel_thresholds.get("audio_level")
                    if audio_th is not None:
                        scan_fields["audio_threshold"] = max(0.15, min(0.95, float(audio_th)))
                elif threshold is not None:
                    clamped = max(0.15, min(0.95, float(threshold)))
                    scan_fields["face_threshold"] = clamped
                    scan_fields["audio_threshold"] = clamped
                if scan_fields:
                    self.profile_manager.set_switch_scan_override(pid, **scan_fields)
        self._save_state()
        snapshot = self.get_state_snapshot()
        self._broadcast_threadsafe({"type": "state", "state": snapshot})
        return snapshot

    def apply_wizard(self, answers: WizardAnswers) -> dict[str, Any]:
        rec = recommend_setup(answers)
        with self._lock:
            merged = self.settings.model_copy(
                update={
                    "high_contrast": rec.recommended_flags["high_contrast"],
                    "large_text": rec.recommended_flags["large_text"],
                    "tts_enabled": rec.recommended_flags["tts_enabled"],
                    "onboarding_done": True,
                }
            )
            self.settings = merged
            self.tts.enabled = merged.tts_enabled
        self.switch_profile(rec.profile_id, apply_metadata=False)
        for inp_name in rec.recommended_inputs:
            provider = self.inputs.get(inp_name)
            if provider and provider.is_available() and not provider.is_running:
                provider.start(self.handle_signal)
        snapshot = self.get_state_snapshot()
        self._broadcast_threadsafe({"type": "state", "state": snapshot})
        return snapshot

    def emergency_stop(self) -> dict[str, Any]:
        with self._lock:
            release_cmds = self.engine.release_all()
            self.settings.safe_test_mode = True
            self._reset_mouse_pump_locked()
        self._dispatch_outputs(release_cmds, force_real=True)
        self._save_state()
        self.announce_key("announce.emergency")
        snapshot = self.get_state_snapshot()
        self._broadcast_threadsafe({"type": "state", "state": snapshot})
        return snapshot

    def get_state_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "version": __version__,
                "active_profile": self.engine.profile.model_dump(),
                "profiles": [p.model_dump() for p in self.profile_manager.list_profiles()],
                "inputs": [p.info() for p in self.inputs.values()],
                "outputs": [o.info() for o in self.outputs],
                "settings": self.settings.model_dump(),
                "voice_languages": sorted(self.tts.available_languages()),
                "scanner": self.engine.get_scanner_snapshot(),
                "active_toggles": self.engine.get_active_toggles(),
                "latest_signals": dict(self._latest_signals),
                "recent_outputs": list(self._recent_outputs),
                "telemetry": {
                    "camera": self.face_tracker.get_telemetry(),
                    "microphone": self.audio_trigger.get_telemetry(),
                },
            }

    def _dispatch_outputs(self, commands: list[OutputCommand], force_real: bool = False) -> None:
        if not commands:
            return
        for cmd in commands:
            if cmd.output_type == OutputType.MOUSE_AXIS:
                if not force_real and not self.settings.safe_test_mode:
                    with self._lock:
                        if cmd.target == "mouse_x":
                            self._target_mouse_x = cmd.value
                        elif cmd.target == "mouse_y":
                            self._target_mouse_y = cmd.value
                        self._last_mouse_ts = time.monotonic()
                continue

            sent_to = "safe_test_mode"
            if force_real or not self.settings.safe_test_mode:
                for adapter in self.outputs:
                    if adapter.is_available() and adapter.send(cmd):
                        sent_to = adapter.name
                        break

            # Do not flood UI logs/WS with high-frequency continuous axis updates
            if cmd.output_type == OutputType.GAMEPAD_AXIS:
                continue

            entry = {
                "output_type": cmd.output_type.value,
                "target": cmd.target,
                "value": cmd.value,
                "label": cmd.label,
                "adapter": sent_to,
            }
            self._recent_outputs.appendleft(entry)
            self._broadcast_threadsafe(
                {
                    "type": "output",
                    "output": entry,
                    "active_toggles": self.engine.get_active_toggles(),
                    "scanner": self.engine.get_scanner_snapshot(),
                }
            )

    def announce_key(self, key: str, **params: Any) -> None:
        self._on_announcement(key, params)

    def _on_announcement(self, key: str, params: dict[str, Any]) -> None:
        lang = self.settings.language
        text = t(lang, key, **params)
        if self.settings.tts_enabled:
            self.tts.speak(lang, text)
        self._broadcast_threadsafe({"type": "announcement", "text": text})

    def _broadcast_threadsafe(self, payload: dict[str, Any]) -> None:
        if self._loop and self._loop.is_running() and self._clients:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), self._loop)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def register_ws(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        await ws.send_json({"type": "state", "state": self.get_state_snapshot()})

    def unregister_ws(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
