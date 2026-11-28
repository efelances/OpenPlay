"""Tests for MappingEngine, ProfileManager, and Wizard recommendations."""

from __future__ import annotations

from openplay.core.mapping_engine import MappingEngine
from openplay.core.models import ActionMode, InputSignal, MappingRule, OutputType, Profile
from openplay.core.profile_manager import ProfileManager, create_builtin_profiles
from openplay.core.wizard import WizardAnswers, recommend_setup


def test_builtin_profiles_cover_diverse_needs():
    profiles = create_builtin_profiles()
    assert len(profiles) == 8
    assert profiles[0].id == "hybrid_head_eye_action"
    ids = {p.id for p in profiles}
    assert {
        "hybrid_head_eye_action",
        "glasses_friendly_action",
        "eye_gaze_action",
        "head_face_handsfree",
        "single_switch_scan",
        "acoustic_nonverbal",
        "one_hand_assist",
        "blind_audio_guided",
    } == ids


def test_toggle_mode_and_release_all():
    announcements: list[str] = []
    profile = Profile(
        id="test_toggle",
        name="Test Toggle",
        description="",
        target_group="",
        rules=[
            MappingRule(
                id="walk",
                name="rule.hybrid_walk",
                source="face_tracker",
                channel="mouth_open",
                mode=ActionMode.TOGGLE,
                output_type=OutputType.KEYBOARD,
                target="w",
                threshold=0.5,
                smoothing=0.0,
                cooldown_ms=0,
            )
        ],
    )
    engine = MappingEngine(profile, on_announcement=lambda k, _p: announcements.append(k))

    # First rise -> toggle ON
    cmds = engine.process_signal(InputSignal(source="face_tracker", channel="mouth_open", value=0.9), now=1.0)
    assert len(cmds) == 1
    assert cmds[0].target == "w" and cmds[0].value == 1.0
    assert engine.get_active_toggles()["walk"] is True

    # Release input
    engine.process_signal(InputSignal(source="face_tracker", channel="mouth_open", value=0.0), now=1.1)

    # Second rise -> toggle OFF
    cmds = engine.process_signal(InputSignal(source="face_tracker", channel="mouth_open", value=0.9), now=1.5)
    assert len(cmds) == 1
    assert cmds[0].target == "w" and cmds[0].value == 0.0
    assert engine.get_active_toggles()["walk"] is False
    assert announcements == ["announce.toggle_on", "announce.toggle_off"]


def test_analog_deadzone_calibration_and_single_zero_release():
    profile = Profile(
        id="test_analog",
        name="Test Analog",
        description="",
        target_group="",
        rules=[
            MappingRule(
                id="yaw",
                name="rule.head_x",
                source="face_tracker",
                channel="head_yaw",
                mode=ActionMode.ANALOG,
                output_type=OutputType.MOUSE_AXIS,
                target="mouse_x",
                deadzone=0.2,
                sensitivity=1.0,
                smoothing=0.0,
            )
        ],
    )
    engine = MappingEngine(profile)

    # Already at zero within deadzone -> stays silent (no zero flood)
    cmds = engine.process_signal(InputSignal(source="face_tracker", channel="head_yaw", value=0.15), now=1.0)
    assert cmds == []

    # Move strongly past deadzone -> produces non-zero command
    cmds = engine.process_signal(InputSignal(source="face_tracker", channel="head_yaw", value=0.9), now=1.1)
    assert len(cmds) == 1 and cmds[0].value > 0.4

    # Return inside deadzone -> emits a single 0.0 release command, then stays quiet
    rel = engine.process_signal(InputSignal(source="face_tracker", channel="head_yaw", value=0.0), now=1.2)
    assert len(rel) == 1 and rel[0].value == 0.0
    idle = engine.process_signal(InputSignal(source="face_tracker", channel="head_yaw", value=0.05), now=1.3)
    assert idle == []

    # Calibrate resting head at 0.3
    engine.calibrate_channel("head_yaw", neutral_value=0.3)
    cmds = engine.process_signal(InputSignal(source="face_tracker", channel="head_yaw", value=0.35), now=1.4)
    assert cmds == []

    cmds = engine.process_signal(InputSignal(source="face_tracker", channel="head_yaw", value=0.9), now=1.5)
    assert len(cmds) == 1 and cmds[0].value > 0.4


def test_pulse_and_tick_release():
    profile = Profile(
        id="test_pulse",
        name="Test Pulse",
        description="",
        target_group="",
        rules=[
            MappingRule(
                id="jump",
                name="rule.audio_tap_jump",
                source="audio_trigger",
                channel="audio_trigger",
                mode=ActionMode.PULSE,
                output_type=OutputType.KEYBOARD,
                target="space",
                threshold=0.5,
                smoothing=0.0,
                pulse_ms=100,
                cooldown_ms=0,
            )
        ],
    )
    engine = MappingEngine(profile)
    cmds = engine.process_signal(InputSignal(source="audio_trigger", channel="audio_trigger", value=0.8), now=2.0)
    assert len(cmds) == 1 and cmds[0].value == 1.0

    # Before 100ms -> still active
    assert engine.tick(now=2.05) == []
    # After 100ms -> released
    rel = engine.tick(now=2.15)
    assert len(rel) == 1 and rel[0].target == "space" and rel[0].value == 0.0


def test_single_switch_scanning_accepts_face_and_audio_channels():
    scan_profile = next(p for p in create_builtin_profiles() if p.id == "single_switch_scan")
    engine = MappingEngine(scan_profile)

    # Trigger via switch_face
    cmds = engine.process_signal(InputSignal(source="face_tracker", channel="switch_face", value=1.0), now=1.0)
    assert len(cmds) == 1
    assert cmds[0].target == "w" and cmds[0].value == 1.0

    # Advance scanner clock past interval_ms
    engine.tick(now=1.0)
    engine.tick(now=5.0)
    snap = engine.get_scanner_snapshot()
    assert snap["current_index"] == 1

    # Trigger via switch_audio on index 1 (space)
    cmds2 = engine.process_signal(InputSignal(source="audio_trigger", channel="switch_audio", value=1.0), now=5.1)
    assert any(c.target == "space" and c.value == 1.0 for c in cmds2)


def test_profile_manager_overrides():
    pm = ProfileManager({"hybrid_head_eye_action": {"hybrid_head_x": {"sensitivity": 2.4, "invert": True}}})
    prof = pm.get("hybrid_head_eye_action")
    assert prof is not None
    rule = next(r for r in prof.rules if r.id == "hybrid_head_x")
    assert rule.sensitivity == 2.4
    assert rule.invert is True


def test_wizard_recommendations():
    rec_eye = recommend_setup(
        WizardAnswers(abilities=["eye_only"], equipment=["webcam"], game_genre="action_gta")
    )
    assert rec_eye.profile_id == "eye_gaze_action"

    rec_gta = recommend_setup(
        WizardAnswers(abilities=["head_face"], equipment=["webcam"], game_genre="action_gta")
    )
    assert rec_gta.profile_id == "hybrid_head_eye_action"

    rec_both = recommend_setup(
        WizardAnswers(abilities=["head_face", "eye_only"], equipment=["webcam"], game_genre="action_gta")
    )
    assert rec_both.profile_id == "hybrid_head_eye_action"

    rec_glasses = recommend_setup(
        WizardAnswers(
            abilities=["head_face"],
            support_needs=["glasses_no_wink"],
            equipment=["webcam", "microphone"],
            game_genre="action_gta",
        )
    )
    assert rec_glasses.profile_id == "glasses_friendly_action"
    assert "audio_trigger" in rec_glasses.recommended_inputs

    rec_sw = recommend_setup(WizardAnswers(abilities=["single_switch"], equipment=["keyboard_mouse"]))
    assert rec_sw.profile_id == "single_switch_scan"

    rec_blind = recommend_setup(
        WizardAnswers(support_needs=["tts_screenreader", "high_contrast"], equipment=["keyboard_mouse"])
    )
    assert rec_blind.profile_id == "blind_audio_guided"
    assert rec_blind.recommended_flags["high_contrast"] is True
    assert rec_blind.recommended_flags["tts_enabled"] is True

    rec_sound_no_mic = recommend_setup(
        WizardAnswers(abilities=["sound_breath"], equipment=["webcam", "keyboard_mouse"])
    )
    assert rec_sound_no_mic.profile_id == "acoustic_nonverbal"
    assert rec_sound_no_mic.recommended_inputs == ["audio_trigger"]


def test_digital_fast_test_triggers_at_high_thresholds_and_releases_cleanly():
    for th in (0.20, 0.75, 0.90, 0.95):
        profile = Profile(
            id="test_high_th",
            name="Test High Threshold",
            description="",
            target_group="",
            rules=[
                MappingRule(
                    id="wink",
                    name="rule.hybrid_shoot",
                    source="face_tracker",
                    channel="wink_right",
                    mode=ActionMode.PRESS,
                    output_type=OutputType.MOUSE_BUTTON,
                    target="left",
                    threshold=th,
                    smoothing=0.35,
                    cooldown_ms=0,
                )
            ],
        )
        engine = MappingEngine(profile)
        cmds = engine.process_signal(
            InputSignal(source="face_tracker", channel="wink_right", value=1.0),
            now=1.0,
        )
        assert len(cmds) == 1 and cmds[0].value == 1.0

        rel = engine.process_signal(
            InputSignal(source="face_tracker", channel="wink_right", value=0.0),
            now=1.1,
        )
        assert len(rel) == 1 and rel[0].value == 0.0


def test_macro_and_switch_scan_pulse_hold_duration_via_tick():
    profile = Profile(
        id="test_macro",
        name="Test Macro",
        description="",
        target_group="",
        rules=[
            MappingRule(
                id="combo",
                name="rule.combo_dodge",
                source="keyboard_assist",
                channel="assist_macro_1",
                mode=ActionMode.MACRO,
                output_type=OutputType.KEYBOARD,
                target="space",
                macro_targets=["space", "e"],
                threshold=0.5,
                pulse_ms=100,
                cooldown_ms=0,
            )
        ],
    )
    engine = MappingEngine(profile)
    cmds = engine.process_signal(
        InputSignal(source="keyboard_assist", channel="assist_macro_1", value=1.0),
        now=1.0,
    )
    assert len(cmds) == 1
    assert cmds[0].target == "space" and cmds[0].value == 1.0

    # Still held before 100 ms
    assert engine.tick(now=1.05) == []
    # Released at >= 100 ms
    rel1 = engine.tick(now=1.10)
    assert len(rel1) == 1 and rel1[0].target == "space" and rel1[0].value == 0.0

    # Second macro key pressed after gap (1.13s) and released after hold (1.23s)
    press2 = engine.tick(now=1.14)
    assert len(press2) == 1 and press2[0].target == "e" and press2[0].value == 1.0
    rel2 = engine.tick(now=1.25)
    assert len(rel2) == 1 and rel2[0].target == "e" and rel2[0].value == 0.0

    # release_all cancels pending macro steps
    engine.process_signal(InputSignal(source="keyboard_assist", channel="assist_macro_1", value=0.0), now=1.3)
    engine.process_signal(InputSignal(source="keyboard_assist", channel="assist_macro_1", value=1.0), now=1.4)
    released = engine.release_all()
    assert any(c.target == "space" and c.value == 0.0 for c in released)
    assert engine.tick(now=2.0) == []


def test_single_switch_scan_pulse_hold_and_custom_thresholds():
    scan_profile = next(p for p in create_builtin_profiles() if p.id == "single_switch_scan")
    scan_profile.switch_scan.face_threshold = 0.80
    scan_profile.switch_scan.audio_threshold = 0.70
    engine = MappingEngine(scan_profile)

    # Advance scanner to index 1 (scan_jump: PULSE space)
    engine.tick(now=1.0)
    engine.tick(now=3.0)
    assert engine.get_scanner_snapshot()["current_index"] == 1

    # Below custom face threshold (0.72 < 0.80) -> ignored
    assert engine.process_signal(InputSignal(source="face_tracker", channel="switch_face", value=0.72), now=3.1) == []

    # At/above face threshold -> pressed immediately, released via tick after ~100 ms
    cmds = engine.process_signal(InputSignal(source="face_tracker", channel="switch_face", value=0.85), now=3.2)
    assert len(cmds) == 1 and cmds[0].target == "space" and cmds[0].value == 1.0
    assert engine.tick(now=3.25) == []
    rel = engine.tick(now=3.32)
    assert len(rel) == 1 and rel[0].target == "space" and rel[0].value == 0.0

    # Release switch_face, then verify custom audio threshold
    engine.process_signal(InputSignal(source="face_tracker", channel="switch_face", value=0.0), now=3.4)
    assert engine.process_signal(InputSignal(source="audio_trigger", channel="switch_audio", value=0.60), now=3.5) == []
    cmds_audio = engine.process_signal(InputSignal(source="audio_trigger", channel="switch_audio", value=0.75), now=4.0)
    assert len(cmds_audio) == 1 and cmds_audio[0].target == "space" and cmds_audio[0].value == 1.0
