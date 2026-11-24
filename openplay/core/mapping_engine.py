"""Core mapping, calibration, toggle, macro, and single-switch scanning engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from openplay.core.models import (
    ActionMode,
    InputSignal,
    MappingRule,
    OutputCommand,
    Profile,
    ScanAction,
)

SWITCH_CHANNELS = frozenset({"switch_1", "switch_face", "switch_audio"})
AnnouncementCallback = Callable[[str, dict[str, Any]], None]


@dataclass
class _RuleRuntimeState:
    smoothed_value: float = 0.0
    is_triggered: bool = False
    toggle_active: bool = False
    last_trigger_ts: float = 0.0
    active_pulse_until: float = 0.0
    last_out: float = 0.0
    prev_raw: float = 0.0


@dataclass
class SwitchScannerState:
    current_index: int = 0
    last_step_ts: float | None = None
    active_toggles: dict[str, bool] = field(default_factory=dict)


class MappingEngine:
    """Transforms normalized InputSignals into OutputCommands using active Profile rules."""

    def __init__(
        self,
        profile: Profile,
        on_announcement: AnnouncementCallback | None = None,
    ) -> None:
        self.profile = profile
        self.on_announcement = on_announcement
        self._rule_states: dict[str, _RuleRuntimeState] = {}
        self._scanner = SwitchScannerState()
        self._calibration_offsets: dict[str, float] = {}
        self._latest_signals: dict[str, float] = {}
        self._active_outputs: dict[str, OutputCommand] = {}

    def set_profile(self, profile: Profile) -> list[OutputCommand]:
        """Switch active profile and release any currently held outputs safely."""
        release_cmds = self.release_all()
        self.profile = profile
        self._rule_states.clear()
        self._scanner = SwitchScannerState()
        self._announce("announce.profile_changed", name_key=f"profile.{profile.id}.name")
        return release_cmds

    def calibrate_channel(self, channel: str, neutral_value: float | None = None) -> float:
        """Set neutral zero-point offset for a channel without emitting announcements."""
        offset = neutral_value if neutral_value is not None else self._latest_signals.get(channel, 0.0)
        self._calibration_offsets[channel] = offset
        return offset

    def reset_calibration(self) -> None:
        """Clear all calibration offsets without emitting announcements."""
        self._calibration_offsets.clear()

    def get_calibration_offsets(self) -> dict[str, float]:
        return dict(self._calibration_offsets)

    def set_calibration_offsets(self, offsets: dict[str, float]) -> None:
        self._calibration_offsets = {str(k): float(v) for k, v in offsets.items()}

    def release_all(self) -> list[OutputCommand]:
        """Release all currently active keys/buttons/axes."""
        commands: list[OutputCommand] = []
        for key, cmd in list(self._active_outputs.items()):
            commands.append(
                OutputCommand(
                    output_type=cmd.output_type,
                    target=cmd.target,
                    value=0.0,
                    label=f"released:{cmd.target}",
                )
            )
            del self._active_outputs[key]
        for state in self._rule_states.values():
            state.is_triggered = False
            state.toggle_active = False
            state.active_pulse_until = 0.0
            state.last_out = 0.0
        self._scanner.active_toggles.clear()
        return commands

    def process_signal(self, signal: InputSignal, now: float | None = None) -> list[OutputCommand]:
        """Process a single incoming signal and return resulting output commands."""
        ts = now if now is not None else time.monotonic()
        self._latest_signals[signal.channel] = signal.value

        calibrated = signal.value - self._calibration_offsets.get(signal.channel, 0.0)
        commands: list[OutputCommand] = []

        # 1. Check single-switch scanning trigger if enabled
        scan = self.profile.switch_scan
        if scan.enabled and (signal.channel in SWITCH_CHANNELS or signal.channel == scan.trigger_channel):
            commands.extend(self._handle_switch_trigger(signal.channel, calibrated, ts))

        # 2. Evaluate matching mapping rules
        for rule in self.profile.rules:
            if not rule.enabled:
                continue
            if rule.channel != signal.channel:
                continue
            if rule.source != "*" and rule.source != signal.source:
                continue
            commands.extend(self._evaluate_rule(rule, calibrated, ts))

        return commands

    def tick(self, now: float | None = None) -> list[OutputCommand]:
        """Periodic update for pulse releases and switch-scanning progression."""
        ts = now if now is not None else time.monotonic()
        commands: list[OutputCommand] = []

        # Release expired pulses
        for rule in self.profile.rules:
            state = self._rule_states.get(rule.id)
            if state and state.active_pulse_until > 0 and ts >= state.active_pulse_until:
                state.active_pulse_until = 0.0
                cmd = OutputCommand(
                    output_type=rule.output_type,
                    target=rule.target,
                    value=0.0,
                    label=f"rule.{rule.id}",
                )
                self._track_output(cmd)
                commands.append(cmd)

        # Advance switch scanner if enabled
        scan = self.profile.switch_scan
        if scan.enabled and scan.actions:
            if self._scanner.last_step_ts is None:
                self._scanner.last_step_ts = ts
            else:
                interval_s = scan.interval_ms / 1000.0
                if ts - self._scanner.last_step_ts >= interval_s:
                    self._scanner.last_step_ts = ts
                    self._scanner.current_index = (self._scanner.current_index + 1) % len(scan.actions)
                    if scan.announce_items:
                        current_action = scan.actions[self._scanner.current_index]
                        self._announce("announce.plain", name_key=f"scan.{current_action.id}")

        return commands

    def get_scanner_snapshot(self) -> dict[str, Any]:
        """Return current switch-scanner state for UI highlighting."""
        scan = self.profile.switch_scan
        current_action: ScanAction | None = None
        if scan.enabled and scan.actions:
            idx = self._scanner.current_index % len(scan.actions)
            current_action = scan.actions[idx]
        return {
            "enabled": scan.enabled,
            "current_index": self._scanner.current_index if scan.actions else 0,
            "current_action_id": current_action.id if current_action else "",
            "active_toggles": dict(self._scanner.active_toggles),
            "actions": [a.model_dump() for a in scan.actions],
        }

    def get_active_toggles(self) -> dict[str, bool]:
        """Return toggle states for all toggle rules."""
        return {
            rule.id: self._rule_states[rule.id].toggle_active
            for rule in self.profile.rules
            if rule.mode == ActionMode.TOGGLE and rule.id in self._rule_states
        }

    def _evaluate_rule(self, rule: MappingRule, raw_val: float, ts: float) -> list[OutputCommand]:
        state = self._rule_states.setdefault(rule.id, _RuleRuntimeState())

        if rule.mode == ActionMode.ANALOG:
            delta = abs(raw_val - state.prev_raw)
            state.prev_raw = raw_val
            if rule.smoothing <= 0.0:
                adaptive_smooth = 0.0
            else:
                adaptive_smooth = max(
                    0.08,
                    rule.smoothing - min(rule.smoothing * 0.75, delta * 2.5),
                )
            alpha = 1.0 - adaptive_smooth
            state.smoothed_value = alpha * raw_val + (1.0 - alpha) * state.smoothed_value
            val = -state.smoothed_value if rule.invert else state.smoothed_value
            return self._eval_analog(rule, state, val)

        # Digital modes use standard Exponential Moving Average (EMA) smoothing
        alpha = 1.0 - rule.smoothing
        state.smoothed_value = alpha * raw_val + (1.0 - alpha) * state.smoothed_value
        val = -state.smoothed_value if rule.invert else state.smoothed_value

        # Digital modes use threshold + hysteresis (0.1 lower release threshold)
        release_threshold = max(0.05, rule.threshold - 0.1)
        was_triggered = state.is_triggered
        if not was_triggered and val >= rule.threshold:
            if (ts - state.last_trigger_ts) * 1000.0 >= rule.cooldown_ms:
                state.is_triggered = True
                state.last_trigger_ts = ts
        elif was_triggered and val < release_threshold:
            state.is_triggered = False

        rising_edge = (not was_triggered) and state.is_triggered
        falling_edge = was_triggered and (not state.is_triggered)

        if rule.mode == ActionMode.PRESS:
            if rising_edge:
                cmd = OutputCommand(output_type=rule.output_type, target=rule.target, value=1.0, label=f"rule.{rule.id}")
                self._track_output(cmd)
                return [cmd]
            if falling_edge:
                cmd = OutputCommand(output_type=rule.output_type, target=rule.target, value=0.0, label=f"rule.{rule.id}")
                self._track_output(cmd)
                return [cmd]
            return []

        if rule.mode == ActionMode.TOGGLE:
            if rising_edge:
                state.toggle_active = not state.toggle_active
                val_out = 1.0 if state.toggle_active else 0.0
                key = "announce.toggle_on" if state.toggle_active else "announce.toggle_off"
                if rule.announce_tts:
                    self._announce(key, name_key=f"rule.{rule.id}")
                cmd = OutputCommand(output_type=rule.output_type, target=rule.target, value=val_out, label=f"rule.{rule.id}")
                self._track_output(cmd)
                return [cmd]
            return []

        if rule.mode == ActionMode.PULSE:
            if rising_edge:
                state.active_pulse_until = ts + (rule.pulse_ms / 1000.0)
                if rule.announce_tts:
                    self._announce("announce.plain", name_key=f"rule.{rule.id}")
                cmd = OutputCommand(output_type=rule.output_type, target=rule.target, value=1.0, label=f"rule.{rule.id}")
                self._track_output(cmd)
                return [cmd]
            return []

        if rule.mode == ActionMode.MACRO:
            if rising_edge:
                targets = rule.macro_targets or [rule.target]
                if rule.announce_tts:
                    self._announce("announce.macro", name_key=f"rule.{rule.id}")
                cmds: list[OutputCommand] = []
                for target in targets:
                    cmds.append(OutputCommand(output_type=rule.output_type, target=target, value=1.0, label=f"rule.{rule.id}"))
                    cmds.append(OutputCommand(output_type=rule.output_type, target=target, value=0.0, label=f"rule.{rule.id}"))
                return cmds
            return []

        return []

    def _eval_analog(self, rule: MappingRule, state: _RuleRuntimeState, val: float) -> list[OutputCommand]:
        if abs(val) < rule.deadzone:
            out_val = 0.0
        else:
            sign = 1.0 if val > 0 else -1.0
            scaled = (abs(val) - rule.deadzone) / max(1e-6, 1.0 - rule.deadzone)
            curved = scaled ** 1.25
            out_val = round(max(-1.0, min(1.0, sign * curved * rule.sensitivity)), 3)

        # Avoid flooding zero commands on idle frames; emit single zero on return-to-center
        if out_val == 0.0 and state.last_out == 0.0:
            return []

        state.last_out = out_val
        cmd = OutputCommand(output_type=rule.output_type, target=rule.target, value=out_val, label=f"rule.{rule.id}")
        self._track_output(cmd)
        return [cmd]

    def _handle_switch_trigger(self, channel: str, val: float, ts: float) -> list[OutputCommand]:
        scan = self.profile.switch_scan
        if not scan.actions:
            return []
        state = self._rule_states.setdefault(f"__switch__{channel}", _RuleRuntimeState())
        was_triggered = state.is_triggered
        if not was_triggered and val >= 0.5:
            if (ts - state.last_trigger_ts) * 1000.0 >= 300:
                state.is_triggered = True
                state.last_trigger_ts = ts
        elif was_triggered and val < 0.35:
            state.is_triggered = False

        if not (not was_triggered and state.is_triggered):
            return []

        action = scan.actions[self._scanner.current_index % len(scan.actions)]
        if action.mode == ActionMode.TOGGLE:
            new_state = not self._scanner.active_toggles.get(action.id, False)
            self._scanner.active_toggles[action.id] = new_state
            key = "announce.toggle_on" if new_state else "announce.toggle_off"
            self._announce(key, name_key=f"scan.{action.id}")
            cmd = OutputCommand(
                output_type=action.output_type,
                target=action.target,
                value=1.0 if new_state else 0.0,
                label=f"scan.{action.id}",
            )
            self._track_output(cmd)
            return [cmd]

        self._announce("announce.selected", name_key=f"scan.{action.id}")
        return [
            OutputCommand(output_type=action.output_type, target=action.target, value=1.0, label=f"scan.{action.id}"),
            OutputCommand(output_type=action.output_type, target=action.target, value=0.0, label=f"scan.{action.id}"),
        ]

    def _track_output(self, cmd: OutputCommand) -> None:
        key = f"{cmd.output_type.value}:{cmd.target}"
        if cmd.value == 0.0:
            self._active_outputs.pop(key, None)
        else:
            self._active_outputs[key] = cmd

    def _announce(self, key: str, **params: Any) -> None:
        if self.on_announcement:
            self.on_announcement(key, params)
