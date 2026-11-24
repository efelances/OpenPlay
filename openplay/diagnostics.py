"""System diagnostics checks for camera, microphone, models, voices, and OS permissions."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openplay.core.models import SUPPORTED_LANGUAGES
from openplay.inputs.face_tracker import FaceTrackerProvider, resolve_model_path
from openplay.outputs.virtual_gamepad import VirtualGamepadAdapter
from openplay.paths import FROZEN, LOCALES_DIR, WEB_DIR

if TYPE_CHECKING:
    from openplay.runtime import AccessRuntime


def _item(diag_id: str, status: str, detail: str = "") -> dict[str, str]:
    return {"id": diag_id, "status": status, "detail": detail}


def run_diagnostics(runtime: "AccessRuntime") -> list[dict[str, str]]:
    """Run non-destructive hardware and environment checks."""
    results: list[dict[str, str]] = []

    # 1. Python runtime
    results.append(
        _item(
            "python",
            "ok",
            f"Python {sys.version.split()[0]} ({'frozen' if FROZEN else 'source'})",
        )
    )

    # 2. Writable user data directory
    try:
        probe = Path(runtime.data_dir) / ".diag_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        results.append(_item("data_dir_writable", "ok", str(runtime.data_dir)))
    except Exception as exc:
        results.append(_item("data_dir_writable", "fail", str(exc)))

    # 3. Web UI assets
    missing_web = [f for f in ("index.html", "styles.css", "app.js") if not (WEB_DIR / f).exists()]
    if missing_web:
        results.append(_item("web_assets", "fail", f"Missing: {', '.join(missing_web)}"))
    else:
        results.append(_item("web_assets", "ok", str(WEB_DIR)))

    # 4. Locale files
    missing_loc = [lang for lang in SUPPORTED_LANGUAGES if not (LOCALES_DIR / f"{lang}.json").exists()]
    if missing_loc:
        results.append(_item("locales", "fail", f"Missing: {', '.join(missing_loc)}"))
    else:
        results.append(_item("locales", "ok", ", ".join(SUPPORTED_LANGUAGES)))

    # 5. Face dependencies
    face_provider = runtime.inputs.get("face_tracker")
    has_face_deps = isinstance(face_provider, FaceTrackerProvider) and face_provider.is_available()
    if has_face_deps:
        import cv2  # type: ignore
        import mediapipe as mp  # type: ignore

        results.append(_item("face_deps", "ok", f"cv2 {cv2.__version__}, mediapipe {mp.__version__}"))
    else:
        results.append(_item("face_deps", "fail", "opencv-python / mediapipe missing"))

    # 6. FaceLandmarker model load + dummy inference
    model_path = resolve_model_path(runtime.data_dir)
    if not has_face_deps:
        results.append(_item("face_model_load", "fail", "Dependencies unavailable"))
    elif model_path is None:
        results.append(_item("face_model_load", "warn", "Model not found locally (downloads on camera start)"))
    else:
        try:
            import mediapipe as mp  # type: ignore
            import numpy as np  # type: ignore
            from mediapipe.tasks import python as mp_python  # type: ignore
            from mediapipe.tasks.python import vision as mp_vision  # type: ignore

            opts = mp_vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_buffer=model_path.read_bytes()),
                running_mode=mp_vision.RunningMode.IMAGE,
                output_face_blendshapes=True,
                num_faces=1,
            )
            landmarker = mp_vision.FaceLandmarker.create_from_options(opts)
            try:
                dummy = np.zeros((240, 320, 3), dtype=np.uint8)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=dummy)
                landmarker.detect(mp_img)
            finally:
                landmarker.close()
            results.append(_item("face_model_load", "ok", model_path.name))
        except Exception as exc:
            results.append(_item("face_model_load", "fail", str(exc)))

    # 7. Webcam probe
    if isinstance(face_provider, FaceTrackerProvider) and face_provider.is_running:
        results.append(_item("camera", "ok", "Streaming"))
    elif has_face_deps:
        try:
            import cv2  # type: ignore

            if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW"):
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(0)
            opened = bool(cap.isOpened())
            cap.release()
            if opened:
                results.append(_item("camera", "ok", "Device 0 ready"))
            else:
                results.append(_item("camera", "warn", "No webcam detected or camera busy"))
        except Exception as exc:
            results.append(_item("camera", "warn", str(exc)))
    else:
        results.append(_item("camera", "warn", "OpenCV missing"))

    # 8. Microphone probe
    try:
        import sounddevice as sd  # type: ignore

        devs = sd.query_devices()
        mic_count = sum(1 for d in devs if d.get("max_input_channels", 0) > 0)
        if mic_count > 0:
            results.append(_item("microphone", "ok", f"{mic_count} input device(s)"))
        else:
            results.append(_item("microphone", "warn", "No input devices found"))
    except Exception as exc:
        results.append(_item("microphone", "warn", str(exc)))

    # 9. TTS voices
    langs = sorted(runtime.tts.available_languages())
    cur_lang = runtime.settings.language
    if langs and cur_lang in langs:
        results.append(_item("tts_voices", "ok", f"Available: {', '.join(langs)}"))
    elif langs:
        results.append(_item("tts_voices", "warn", f"Active '{cur_lang}' missing; found: {', '.join(langs)}"))
    else:
        results.append(_item("tts_voices", "warn", "No SAPI voices detected"))

    # 10. Windows SendInput
    if sys.platform == "win32":
        results.append(_item("send_input", "ok", "Win32 SendInput (scan codes)"))
    else:
        results.append(_item("send_input", "warn", "Windows only"))

    # 11. Virtual Xbox 360 gamepad (optional)
    vg_adapter: Any = next((o for o in runtime.outputs if isinstance(o, VirtualGamepadAdapter)), None)
    if vg_adapter and vg_adapter.is_available():
        results.append(_item("vgamepad", "ok", "ViGEmBus connected"))
    else:
        detail = vg_adapter.detail() if vg_adapter else ""
        results.append(_item("vgamepad", "warn", detail or "Optional ViGEmBus not installed"))

    return results
