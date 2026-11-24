"""Tests for pure face signal computation and differential wink filtering."""

from __future__ import annotations

from dataclasses import dataclass

from openplay.inputs.face_signals import compute_signals


@dataclass
class _Pt:
    x: float = 0.5
    y: float = 0.5


def _dummy_landmarks() -> list[_Pt]:
    pts = [_Pt() for _ in range(478)]
    pts[234] = _Pt(x=0.3, y=0.5)
    pts[454] = _Pt(x=0.7, y=0.5)
    pts[10] = _Pt(x=0.5, y=0.2)
    pts[152] = _Pt(x=0.5, y=0.8)
    pts[1] = _Pt(x=0.5, y=0.5)
    return pts


def test_natural_blink_is_filtered_from_winks():
    lm = _dummy_landmarks()
    sig = compute_signals(lm, {"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9})
    assert sig["wink_left"] < 0.2
    assert sig["wink_right"] < 0.2


def test_left_wink_and_swap_eyes():
    lm = _dummy_landmarks()
    # By default, mirrored camera maps eyeBlinkRight -> user's left eye
    sig = compute_signals(lm, {"eyeBlinkRight": 0.9, "eyeBlinkLeft": 0.1}, swap_eyes=False)
    assert sig["wink_left"] > 0.5
    assert sig["wink_right"] == 0.0

    # Swapping eyes flips left and right winks
    swapped = compute_signals(lm, {"eyeBlinkRight": 0.9, "eyeBlinkLeft": 0.1}, swap_eyes=True)
    assert swapped["wink_right"] > 0.5
    assert swapped["wink_left"] == 0.0


def test_switch_face_emitted_only_on_strong_mouth_open():
    lm = _dummy_landmarks()
    assert compute_signals(lm, {"jawOpen": 0.2})["switch_face"] == 0.0
    assert compute_signals(lm, {"jawOpen": 0.8})["switch_face"] == 1.0
    assert "switch_1" not in compute_signals(lm, {"jawOpen": 0.8})


def test_mild_glasses_wink_with_squint_is_amplified():
    lm = _dummy_landmarks()
    sig = compute_signals(
        lm,
        {"eyeBlinkRight": 0.45, "eyeSquintRight": 0.35, "eyeBlinkLeft": 0.10},
        swap_eyes=False,
    )
    assert sig["wink_left"] > 0.5
    assert sig["wink_right"] == 0.0


def test_outer_brow_and_lower_face_glasses_free_signals():
    lm = _dummy_landmarks()
    sig = compute_signals(
        lm,
        {
            "browOuterUpLeft": 0.75,
            "browOuterUpRight": 0.75,
            "mouthPucker": 0.82,
            "cheekPuff": 0.68,
        },
    )
    assert sig["eyebrow_raise"] > 0.6
    assert sig["mouth_pucker"] == 0.82
    assert sig["cheek_puff"] == 0.68


def test_iris_landmarks_drive_gaze_without_blendshapes():
    lm = _dummy_landmarks()
    # Left eye box [0.35..0.45] x [0.46..0.54], iris shifted right to 0.43
    lm[33] = _Pt(x=0.35, y=0.50)
    lm[133] = _Pt(x=0.45, y=0.50)
    lm[159] = _Pt(x=0.40, y=0.46)
    lm[145] = _Pt(x=0.40, y=0.54)
    lm[468] = _Pt(x=0.43, y=0.50)

    # Right eye box [0.55..0.65] x [0.46..0.54], iris shifted right to 0.63
    lm[362] = _Pt(x=0.55, y=0.50)
    lm[263] = _Pt(x=0.65, y=0.50)
    lm[386] = _Pt(x=0.60, y=0.46)
    lm[374] = _Pt(x=0.60, y=0.54)
    lm[473] = _Pt(x=0.63, y=0.50)

    sig = compute_signals(lm, {})
    assert sig["gaze_x"] > 0.3
