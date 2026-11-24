"""Guided onboarding wizard that recommends an accessibility profile using i18n keys."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WizardAnswers(BaseModel):
    """User responses from the accessible onboarding wizard."""

    abilities: list[str] = Field(
        default_factory=list,
        description="head_face, eye_only, one_hand, single_switch, sound_breath",
    )
    support_needs: list[str] = Field(
        default_factory=list,
        description="high_contrast, large_text, tts_screenreader, nonverbal, glasses_no_wink",
    )
    equipment: list[str] = Field(
        default_factory=list,
        description="webcam, microphone, keyboard_mouse, gamepad",
    )
    game_genre: str = Field(
        default="action_gta",
        description="action_gta, racing, strategy, casual",
    )


class WizardRecommendation(BaseModel):
    """Language-agnostic recommendation returned by the onboarding wizard."""

    profile_id: str
    summary_key: str
    hints_key: str
    recommended_inputs: list[str]
    recommended_flags: dict[str, bool]


def _build_recommendation(
    profile_id: str,
    recommended_inputs: list[str],
    recommended_flags: dict[str, bool],
) -> WizardRecommendation:
    return WizardRecommendation(
        profile_id=profile_id,
        summary_key=f"wizard.result.{profile_id}.summary",
        hints_key=f"wizard.result.{profile_id}.hints",
        recommended_inputs=recommended_inputs,
        recommended_flags=recommended_flags,
    )


def recommend_setup(answers: WizardAnswers) -> WizardRecommendation:
    """Select the best profile and accessibility flags based on user needs."""
    abilities = set(answers.abilities)
    support = set(answers.support_needs)
    equipment = set(answers.equipment)

    flags = {
        "high_contrast": "high_contrast" in support or "tts_screenreader" in support,
        "large_text": "large_text" in support or "high_contrast" in support,
        "tts_enabled": True,
    }

    has_webcam = "webcam" in equipment or not equipment
    has_mic = "microphone" in equipment

    if "single_switch" in abilities and not ({"head_face", "one_hand"} & abilities):
        return _build_recommendation(
            "single_switch_scan",
            ["keyboard_assist"] + (["face_tracker"] if has_webcam else []),
            flags,
        )

    if "eye_only" in abilities and "head_face" not in abilities and has_webcam:
        return _build_recommendation("eye_gaze_action", ["face_tracker"], flags)

    if "head_face" in abilities and has_webcam and "glasses_no_wink" in support:
        return _build_recommendation(
            "glasses_friendly_action",
            ["face_tracker"] + (["audio_trigger"] if has_mic else []),
            flags,
        )

    if "head_face" in abilities and has_webcam and answers.game_genre in {"action_gta", "racing"}:
        return _build_recommendation("hybrid_head_eye_action", ["face_tracker"], flags)

    if "head_face" in abilities and has_webcam:
        return _build_recommendation("head_face_handsfree", ["face_tracker"], flags)

    if "sound_breath" in abilities and has_mic:
        return _build_recommendation("acoustic_nonverbal", ["audio_trigger"], flags)

    if "tts_screenreader" in support and not ({"one_hand", "head_face", "eye_only"} & abilities):
        return _build_recommendation("blind_audio_guided", ["keyboard_assist"], flags)

    return _build_recommendation("one_hand_assist", ["keyboard_assist"], flags)
