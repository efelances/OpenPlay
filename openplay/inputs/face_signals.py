"""Pure signal computation from face landmarks and blendshapes (easy to unit-test)."""

from __future__ import annotations

from typing import Sequence


def clamp(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))


def _ear_closed(
    landmarks: Sequence,
    outer_idx: int,
    inner_idx: int,
    top_idx: int,
    bottom_idx: int,
) -> float:
    """Compute geometric eye-closure score [0, 1] from Eye Aspect Ratio."""
    eye_w = abs(landmarks[inner_idx].x - landmarks[outer_idx].x)
    if eye_w < 1e-3:
        return 0.0
    eye_h = abs(landmarks[bottom_idx].y - landmarks[top_idx].y)
    ear = eye_h / eye_w
    return clamp((0.26 - ear) / 0.14, 0.0, 1.0)


def _iris_gaze(landmarks: Sequence) -> tuple[float, float] | None:
    """Compute normalized [x, y] iris position inside both eye sockets."""
    if len(landmarks) <= 473:
        return None
    # Mirrored preview: MP right eye (33/133/159/145, iris 468) is on user's left,
    # MP left eye (362/263/386/374, iris 473) is on user's right.
    w1 = landmarks[133].x - landmarks[33].x
    h1 = landmarks[145].y - landmarks[159].y
    w2 = landmarks[263].x - landmarks[362].x
    h2 = landmarks[374].y - landmarks[386].y
    if w1 < 1e-3 or w2 < 1e-3 or h1 < 1e-3 or h2 < 1e-3:
        return None

    rx1 = (landmarks[468].x - landmarks[33].x) / w1
    rx2 = (landmarks[473].x - landmarks[362].x) / w2
    ry1 = (landmarks[468].y - landmarks[159].y) / h1
    ry2 = (landmarks[473].y - landmarks[386].y) / h2

    ix = clamp(((rx1 + rx2) / 2.0 - 0.5) * 4.5, -1.0, 1.0)
    iy = clamp(((ry1 + ry2) / 2.0 - 0.5) * 3.5, -1.0, 1.0)
    return ix, iy


def compute_signals(
    landmarks: Sequence,
    blendshapes: dict[str, float],
    swap_eyes: bool = False,
) -> dict[str, float]:
    """Compute normalized control signals from MediaPipe face landmarks and blendshapes."""
    nose = landmarks[1]
    left_face = landmarks[234]
    right_face = landmarks[454]
    top_face = landmarks[10]
    bottom_face = landmarks[152]

    face_width = max(1e-4, abs(right_face.x - left_face.x))
    face_height = max(1e-4, abs(bottom_face.y - top_face.y))

    center_x = (left_face.x + right_face.x) / 2.0
    center_y = (top_face.y + bottom_face.y) / 2.0
    head_yaw = clamp((nose.x - center_x) / (face_width * 0.25), -1.0, 1.0)
    head_pitch = clamp((nose.y - center_y) / (face_height * 0.25), -1.0, 1.0)

    # Mirrored preview: MediaPipe 'Right' corresponds to user's left eye by default
    raw_left_blink = clamp(blendshapes.get("eyeBlinkRight", 0.0), 0.0, 1.0)
    raw_right_blink = clamp(blendshapes.get("eyeBlinkLeft", 0.0), 0.0, 1.0)
    raw_left_squint = clamp(blendshapes.get("eyeSquintRight", 0.0), 0.0, 1.0)
    raw_right_squint = clamp(blendshapes.get("eyeSquintLeft", 0.0), 0.0, 1.0)
    ear_left = _ear_closed(landmarks, 33, 133, 159, 145)
    ear_right = _ear_closed(landmarks, 362, 263, 386, 374)

    closed_left = max(
        raw_left_blink,
        clamp(raw_left_blink * 0.75 + raw_left_squint * 0.45, 0.0, 1.0),
        ear_left,
    )
    closed_right = max(
        raw_right_blink,
        clamp(raw_right_blink * 0.75 + raw_right_squint * 0.45, 0.0, 1.0),
        ear_right,
    )

    if swap_eyes:
        blink_left, blink_right = closed_right, closed_left
    else:
        blink_left, blink_right = closed_left, closed_right

    # Differential wink filters out natural two-eye blinks while amplifying intentional winks
    wink_left = clamp((blink_left - blink_right - 0.06) * 2.4, 0.0, 1.0)
    wink_right = clamp((blink_right - blink_left - 0.06) * 2.4, 0.0, 1.0)

    mouth_open = clamp(blendshapes.get("jawOpen", 0.0), 0.0, 1.0)
    brow_outer = (
        blendshapes.get("browOuterUpLeft", 0.0) + blendshapes.get("browOuterUpRight", 0.0)
    ) / 2.0
    eyebrow_raise = clamp(max(blendshapes.get("browInnerUp", 0.0), brow_outer), 0.0, 1.0)
    smile = clamp(
        (blendshapes.get("mouthSmileLeft", 0.0) + blendshapes.get("mouthSmileRight", 0.0)) / 2.0,
        0.0,
        1.0,
    )

    # Lower-face gestures unaffected by eyeglasses
    mouth_pucker = clamp(blendshapes.get("mouthPucker", 0.0), 0.0, 1.0)
    cheek_puff = clamp(blendshapes.get("cheekPuff", 0.0), 0.0, 1.0)
    mouth_left = clamp(blendshapes.get("mouthRight", 0.0), 0.0, 1.0)
    mouth_right = clamp(blendshapes.get("mouthLeft", 0.0), 0.0, 1.0)

    look_right = (blendshapes.get("eyeLookOutLeft", 0.0) + blendshapes.get("eyeLookInRight", 0.0)) / 2.0
    look_left = (blendshapes.get("eyeLookInLeft", 0.0) + blendshapes.get("eyeLookOutRight", 0.0)) / 2.0
    look_up = (blendshapes.get("eyeLookUpLeft", 0.0) + blendshapes.get("eyeLookUpRight", 0.0)) / 2.0
    look_down = (blendshapes.get("eyeLookDownLeft", 0.0) + blendshapes.get("eyeLookDownRight", 0.0)) / 2.0
    bs_gx = clamp((look_right - look_left) * 1.5, -1.0, 1.0)
    bs_gy = clamp((look_down - look_up) * 1.5, -1.0, 1.0)

    iris = _iris_gaze(landmarks)
    if iris is not None:
        gaze_x = clamp(iris[0] * 0.65 + bs_gx * 0.35 + head_yaw * 0.35, -1.0, 1.0)
        gaze_y = clamp(iris[1] * 0.65 + bs_gy * 0.35 + head_pitch * 0.35, -1.0, 1.0)
    else:
        gaze_x = clamp(bs_gx + head_yaw * 0.65, -1.0, 1.0)
        gaze_y = clamp(bs_gy + head_pitch * 0.65, -1.0, 1.0)

    switch_face = mouth_open

    return {
        "head_yaw": head_yaw,
        "head_pitch": head_pitch,
        "gaze_x": gaze_x,
        "gaze_y": gaze_y,
        "blink_left": blink_left,
        "blink_right": blink_right,
        "wink_left": wink_left,
        "wink_right": wink_right,
        "mouth_open": mouth_open,
        "eyebrow_raise": eyebrow_raise,
        "smile": smile,
        "mouth_pucker": mouth_pucker,
        "cheek_puff": cheek_puff,
        "mouth_left": mouth_left,
        "mouth_right": mouth_right,
        "switch_face": switch_face,
    }
