"""Built-in universal accessibility profiles with per-rule overrides."""

from __future__ import annotations

from typing import Any

from openplay.core.models import (
    ActionMode,
    MappingRule,
    OutputType,
    Profile,
    ScanAction,
    SwitchScanConfig,
)

_ALLOWED_OVERRIDE_FIELDS = {"sensitivity", "deadzone", "threshold", "invert", "smoothing"}


def create_builtin_profiles() -> list[Profile]:
    """Create inclusive starter profiles covering diverse accessibility needs."""
    return [
        Profile(
            id="hybrid_head_eye_action",
            name="profile.hybrid_head_eye_action.name",
            description="profile.hybrid_head_eye_action.desc",
            target_group="profile.hybrid_head_eye_action.target",
            active_inputs=["face_tracker"],
            rules=[
                MappingRule(
                    id="hybrid_head_x",
                    name="rule.hybrid_head_x",
                    source="face_tracker",
                    channel="head_yaw",
                    mode=ActionMode.ANALOG,
                    output_type=OutputType.MOUSE_AXIS,
                    target="mouse_x",
                    deadzone=0.14,
                    sensitivity=1.5,
                    smoothing=0.35,
                    announce_tts=False,
                ),
                MappingRule(
                    id="hybrid_head_y",
                    name="rule.hybrid_head_y",
                    source="face_tracker",
                    channel="head_pitch",
                    mode=ActionMode.ANALOG,
                    output_type=OutputType.MOUSE_AXIS,
                    target="mouse_y",
                    deadzone=0.14,
                    sensitivity=1.5,
                    smoothing=0.35,
                    announce_tts=False,
                ),
                MappingRule(
                    id="hybrid_aim_toggle",
                    name="rule.hybrid_aim_toggle",
                    source="face_tracker",
                    channel="wink_left",
                    mode=ActionMode.TOGGLE,
                    output_type=OutputType.MOUSE_BUTTON,
                    target="right",
                    threshold=0.45,
                    cooldown_ms=400,
                ),
                MappingRule(
                    id="hybrid_shoot",
                    name="rule.hybrid_shoot",
                    source="face_tracker",
                    channel="wink_right",
                    mode=ActionMode.PRESS,
                    output_type=OutputType.MOUSE_BUTTON,
                    target="left",
                    threshold=0.45,
                    cooldown_ms=150,
                    announce_tts=False,
                ),
                MappingRule(
                    id="hybrid_walk",
                    name="rule.hybrid_walk",
                    source="face_tracker",
                    channel="mouth_open",
                    mode=ActionMode.TOGGLE,
                    output_type=OutputType.KEYBOARD,
                    target="w",
                    threshold=0.55,
                    cooldown_ms=450,
                ),
                MappingRule(
                    id="hybrid_jump",
                    name="rule.hybrid_jump",
                    source="face_tracker",
                    channel="eyebrow_raise",
                    mode=ActionMode.PULSE,
                    output_type=OutputType.KEYBOARD,
                    target="space",
                    threshold=0.58,
                    cooldown_ms=350,
                ),
            ],
        ),
        Profile(
            id="glasses_friendly_action",
            name="profile.glasses_friendly_action.name",
            description="profile.glasses_friendly_action.desc",
            target_group="profile.glasses_friendly_action.target",
            active_inputs=["face_tracker", "audio_trigger"],
            rules=[
                MappingRule(
                    id="glasses_head_x",
                    name="rule.glasses_head_x",
                    source="face_tracker",
                    channel="head_yaw",
                    mode=ActionMode.ANALOG,
                    output_type=OutputType.MOUSE_AXIS,
                    target="mouse_x",
                    deadzone=0.14,
                    sensitivity=1.5,
                    smoothing=0.35,
                    announce_tts=False,
                ),
                MappingRule(
                    id="glasses_head_y",
                    name="rule.glasses_head_y",
                    source="face_tracker",
                    channel="head_pitch",
                    mode=ActionMode.ANALOG,
                    output_type=OutputType.MOUSE_AXIS,
                    target="mouse_y",
                    deadzone=0.14,
                    sensitivity=1.5,
                    smoothing=0.35,
                    announce_tts=False,
                ),
                MappingRule(
                    id="glasses_aim_pucker",
                    name="rule.glasses_aim_pucker",
                    source="face_tracker",
                    channel="mouth_pucker",
                    mode=ActionMode.TOGGLE,
                    output_type=OutputType.MOUSE_BUTTON,
                    target="right",
                    threshold=0.55,
                    cooldown_ms=400,
                ),
                MappingRule(
                    id="glasses_shoot_audio",
                    name="rule.glasses_shoot_audio",
                    source="audio_trigger",
                    channel="audio_trigger",
                    mode=ActionMode.PRESS,
                    output_type=OutputType.MOUSE_BUTTON,
                    target="left",
                    threshold=0.45,
                    cooldown_ms=120,
                    announce_tts=False,
                ),
                MappingRule(
                    id="glasses_shoot_cheek",
                    name="rule.glasses_shoot_cheek",
                    source="face_tracker",
                    channel="cheek_puff",
                    mode=ActionMode.PRESS,
                    output_type=OutputType.MOUSE_BUTTON,
                    target="left",
                    threshold=0.55,
                    cooldown_ms=150,
                    announce_tts=False,
                ),
                MappingRule(
                    id="glasses_walk",
                    name="rule.glasses_walk",
                    source="face_tracker",
                    channel="mouth_open",
                    mode=ActionMode.TOGGLE,
                    output_type=OutputType.KEYBOARD,
                    target="w",
                    threshold=0.50,
                    cooldown_ms=450,
                ),
                MappingRule(
                    id="glasses_jump",
                    name="rule.glasses_jump",
                    source="face_tracker",
                    channel="eyebrow_raise",
                    mode=ActionMode.PULSE,
                    output_type=OutputType.KEYBOARD,
                    target="space",
                    threshold=0.60,
                    cooldown_ms=350,
                ),
            ],
        ),
        Profile(
            id="eye_gaze_action",
            name="profile.eye_gaze_action.name",
            description="profile.eye_gaze_action.desc",
            target_group="profile.eye_gaze_action.target",
            active_inputs=["face_tracker"],
            rules=[
                MappingRule(
                    id="gaze_cam_x",
                    name="rule.gaze_cam_x",
                    source="face_tracker",
                    channel="gaze_x",
                    mode=ActionMode.ANALOG,
                    output_type=OutputType.MOUSE_AXIS,
                    target="mouse_x",
                    deadzone=0.22,
                    sensitivity=1.3,
                    smoothing=0.5,
                    announce_tts=False,
                ),
                MappingRule(
                    id="gaze_cam_y",
                    name="rule.gaze_cam_y",
                    source="face_tracker",
                    channel="gaze_y",
                    mode=ActionMode.ANALOG,
                    output_type=OutputType.MOUSE_AXIS,
                    target="mouse_y",
                    deadzone=0.22,
                    sensitivity=1.3,
                    smoothing=0.5,
                    announce_tts=False,
                ),
                MappingRule(
                    id="gaze_aim",
                    name="rule.gaze_aim",
                    source="face_tracker",
                    channel="wink_left",
                    mode=ActionMode.TOGGLE,
                    output_type=OutputType.MOUSE_BUTTON,
                    target="right",
                    threshold=0.45,
                    cooldown_ms=400,
                ),
                MappingRule(
                    id="gaze_shoot",
                    name="rule.gaze_shoot",
                    source="face_tracker",
                    channel="wink_right",
                    mode=ActionMode.PRESS,
                    output_type=OutputType.MOUSE_BUTTON,
                    target="left",
                    threshold=0.45,
                    cooldown_ms=150,
                    announce_tts=False,
                ),
                MappingRule(
                    id="gaze_walk",
                    name="rule.gaze_walk",
                    source="face_tracker",
                    channel="mouth_open",
                    mode=ActionMode.TOGGLE,
                    output_type=OutputType.KEYBOARD,
                    target="w",
                    threshold=0.55,
                    cooldown_ms=450,
                ),
            ],
        ),
        Profile(
            id="head_face_handsfree",
            name="profile.head_face_handsfree.name",
            description="profile.head_face_handsfree.desc",
            target_group="profile.head_face_handsfree.target",
            active_inputs=["face_tracker"],
            rules=[
                MappingRule(
                    id="head_x",
                    name="rule.head_x",
                    source="face_tracker",
                    channel="head_yaw",
                    mode=ActionMode.ANALOG,
                    output_type=OutputType.MOUSE_AXIS,
                    target="mouse_x",
                    deadzone=0.14,
                    sensitivity=1.4,
                    smoothing=0.4,
                    announce_tts=False,
                ),
                MappingRule(
                    id="head_y",
                    name="rule.head_y",
                    source="face_tracker",
                    channel="head_pitch",
                    mode=ActionMode.ANALOG,
                    output_type=OutputType.MOUSE_AXIS,
                    target="mouse_y",
                    deadzone=0.14,
                    sensitivity=1.4,
                    smoothing=0.4,
                    announce_tts=False,
                ),
                MappingRule(
                    id="mouth_walk",
                    name="rule.mouth_walk",
                    source="face_tracker",
                    channel="mouth_open",
                    mode=ActionMode.TOGGLE,
                    output_type=OutputType.KEYBOARD,
                    target="w",
                    threshold=0.55,
                    cooldown_ms=450,
                ),
                MappingRule(
                    id="brow_jump",
                    name="rule.brow_jump",
                    source="face_tracker",
                    channel="eyebrow_raise",
                    mode=ActionMode.PULSE,
                    output_type=OutputType.KEYBOARD,
                    target="space",
                    threshold=0.58,
                    cooldown_ms=350,
                ),
                MappingRule(
                    id="smile_click",
                    name="rule.smile_click",
                    source="face_tracker",
                    channel="smile",
                    mode=ActionMode.PRESS,
                    output_type=OutputType.MOUSE_BUTTON,
                    target="left",
                    threshold=0.55,
                    cooldown_ms=200,
                    announce_tts=False,
                ),
            ],
        ),
        Profile(
            id="single_switch_scan",
            name="profile.single_switch_scan.name",
            description="profile.single_switch_scan.desc",
            target_group="profile.single_switch_scan.target",
            active_inputs=["keyboard_assist", "face_tracker", "audio_trigger"],
            rules=[],
            switch_scan=SwitchScanConfig(
                enabled=True,
                trigger_channel="switch_1",
                interval_ms=1500,
                announce_items=True,
                actions=[
                    ScanAction(id="scan_walk", label="scan.scan_walk", output_type=OutputType.KEYBOARD, target="w", mode=ActionMode.TOGGLE),
                    ScanAction(id="scan_jump", label="scan.scan_jump", output_type=OutputType.KEYBOARD, target="space", mode=ActionMode.PULSE),
                    ScanAction(id="scan_interact", label="scan.scan_interact", output_type=OutputType.KEYBOARD, target="e", mode=ActionMode.PULSE),
                    ScanAction(id="scan_click", label="scan.scan_click", output_type=OutputType.MOUSE_BUTTON, target="left", mode=ActionMode.PULSE),
                    ScanAction(id="scan_menu", label="scan.scan_menu", output_type=OutputType.KEYBOARD, target="esc", mode=ActionMode.PULSE),
                ],
            ),
        ),
        Profile(
            id="acoustic_nonverbal",
            name="profile.acoustic_nonverbal.name",
            description="profile.acoustic_nonverbal.desc",
            target_group="profile.acoustic_nonverbal.target",
            active_inputs=["audio_trigger"],
            rules=[
                MappingRule(
                    id="audio_tap_jump",
                    name="rule.audio_tap_jump",
                    source="audio_trigger",
                    channel="audio_trigger",
                    mode=ActionMode.PULSE,
                    output_type=OutputType.KEYBOARD,
                    target="space",
                    threshold=0.5,
                    cooldown_ms=300,
                ),
                MappingRule(
                    id="audio_loud_click",
                    name="rule.audio_loud_click",
                    source="audio_trigger",
                    channel="audio_loud",
                    mode=ActionMode.PULSE,
                    output_type=OutputType.MOUSE_BUTTON,
                    target="left",
                    threshold=0.75,
                    cooldown_ms=400,
                ),
            ],
        ),
        Profile(
            id="one_hand_assist",
            name="profile.one_hand_assist.name",
            description="profile.one_hand_assist.desc",
            target_group="profile.one_hand_assist.target",
            active_inputs=["keyboard_assist"],
            rules=[
                MappingRule(
                    id="toggle_walk",
                    name="rule.toggle_walk",
                    source="keyboard_assist",
                    channel="assist_toggle_walk",
                    mode=ActionMode.TOGGLE,
                    output_type=OutputType.KEYBOARD,
                    target="w",
                    threshold=0.5,
                ),
                MappingRule(
                    id="toggle_sprint",
                    name="rule.toggle_sprint",
                    source="keyboard_assist",
                    channel="assist_toggle_sprint",
                    mode=ActionMode.TOGGLE,
                    output_type=OutputType.KEYBOARD,
                    target="shift",
                    threshold=0.5,
                ),
                MappingRule(
                    id="combo_dodge",
                    name="rule.combo_dodge",
                    source="keyboard_assist",
                    channel="assist_macro_1",
                    mode=ActionMode.MACRO,
                    output_type=OutputType.KEYBOARD,
                    target="space",
                    macro_targets=["space", "e"],
                    threshold=0.5,
                ),
            ],
        ),
        Profile(
            id="blind_audio_guided",
            name="profile.blind_audio_guided.name",
            description="profile.blind_audio_guided.desc",
            target_group="profile.blind_audio_guided.target",
            active_inputs=["keyboard_assist"],
            rules=[
                MappingRule(
                    id="blind_walk_toggle",
                    name="rule.blind_walk_toggle",
                    source="keyboard_assist",
                    channel="assist_toggle_walk",
                    mode=ActionMode.TOGGLE,
                    output_type=OutputType.KEYBOARD,
                    target="w",
                    threshold=0.5,
                    announce_tts=True,
                ),
                MappingRule(
                    id="blind_interact",
                    name="rule.blind_interact",
                    source="keyboard_assist",
                    channel="assist_macro_1",
                    mode=ActionMode.PULSE,
                    output_type=OutputType.KEYBOARD,
                    target="e",
                    threshold=0.5,
                    announce_tts=True,
                ),
            ],
            metadata={"recommended_high_contrast": True, "recommended_tts": True},
        ),
    ]


class ProfileManager:
    """Manages built-in profiles and user-level rule tuning overrides."""

    def __init__(self, overrides: dict[str, dict[str, dict[str, Any]]] | None = None) -> None:
        self._overrides: dict[str, dict[str, dict[str, Any]]] = {
            pid: {rid: dict(vals) for rid, vals in rules.items()}
            for pid, rules in (overrides or {}).items()
        }
        self._profiles: dict[str, Profile] = {}
        self._rebuild()

    def _rebuild(self) -> None:
        self._profiles = {}
        for profile in create_builtin_profiles():
            prof_overrides = self._overrides.get(profile.id, {})
            for rule in profile.rules:
                rule_ov = prof_overrides.get(rule.id)
                if rule_ov:
                    for field, val in rule_ov.items():
                        if field in _ALLOWED_OVERRIDE_FIELDS:
                            setattr(rule, field, val)
            self._profiles[profile.id] = profile

    def list_profiles(self) -> list[Profile]:
        return list(self._profiles.values())

    def get(self, profile_id: str) -> Profile | None:
        return self._profiles.get(profile_id)

    def set_rule_override(self, profile_id: str, rule_id: str, **fields: Any) -> None:
        filtered = {k: v for k, v in fields.items() if k in _ALLOWED_OVERRIDE_FIELDS and v is not None}
        if not filtered:
            return
        prof_ov = self._overrides.setdefault(profile_id, {})
        rule_ov = prof_ov.setdefault(rule_id, {})
        rule_ov.update(filtered)

        profile = self._profiles.get(profile_id)
        if profile:
            for rule in profile.rules:
                if rule.id == rule_id:
                    for k, v in filtered.items():
                        setattr(rule, k, v)
                    break

    def get_overrides(self) -> dict[str, dict[str, dict[str, Any]]]:
        return {
            pid: {rid: dict(vals) for rid, vals in rules.items()}
            for pid, rules in self._overrides.items()
        }
