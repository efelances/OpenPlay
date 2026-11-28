"""Webcam head-pose, iris eye-gaze, wink, and facial-expression tracker."""

from __future__ import annotations

import hashlib
import logging
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from openplay.inputs.base import InputProvider, SignalCallback
from openplay.inputs.camera_enhance import (
    SignalHoldTracker,
    enhance_low_light_frame,
    light_quality_code,
)
from openplay.inputs.face_signals import compute_signals
from openplay.paths import BUNDLED_MODEL, get_data_dir

logger = logging.getLogger(__name__)

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"

try:
    import cv2  # type: ignore
    import mediapipe as mp  # type: ignore
    from mediapipe.tasks import python as mp_python  # type: ignore
    from mediapipe.tasks.python import vision as mp_vision  # type: ignore

    _HAS_FACE_DEPS = True
except Exception as _face_import_exc:
    cv2 = None
    mp = None
    mp_python = None
    mp_vision = None
    _HAS_FACE_DEPS = False
    logging.getLogger(__name__).warning("Face tracker dependencies unavailable: %s", _face_import_exc)


def resolve_model_path(data_dir: Path | None = None) -> Path | None:
    """Return existing FaceLandmarker model path (bundled first, then user data dir)."""
    if BUNDLED_MODEL.exists():
        return BUNDLED_MODEL
    user_model = get_data_dir(data_dir) / "models" / "face_landmarker.task"
    if user_model.exists():
        return user_model
    return None


class FaceTrackerProvider(InputProvider):
    """Tracks head yaw/pitch, eye gaze, differential winks, and facial expressions."""

    name = "face_tracker"

    def __init__(self, camera_index: int = 0, data_dir: Path | None = None) -> None:
        super().__init__()
        self.camera_index = camera_index
        self.data_dir = data_dir
        self.swap_eyes: bool = False
        self.low_light_mode: bool = True
        self._thread: threading.Thread | None = None
        self._frame_lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._status_code_override: str = ""
        self._downloading: bool = False
        self._stream_id: int = 0
        self._telemetry_lock = threading.Lock()
        self._telemetry: dict[str, Any] = {
            "fps": 0.0,
            "brightness": 0.0,
            "light_status": "unknown",
            "face_detected": False,
            "enhanced": False,
            "camera_index": self.camera_index,
            "stream_id": 0,
        }

    @property
    def stream_id(self) -> int:
        return self._stream_id

    def info(self) -> dict[str, Any]:
        data = super().info()
        data["stream_id"] = self._stream_id
        return data

    def get_latest_jpeg(self) -> bytes | None:
        with self._frame_lock:
            return self._latest_jpeg

    def get_telemetry(self) -> dict[str, Any]:
        with self._telemetry_lock:
            return dict(self._telemetry)

    def _set_telemetry(self, **updates: Any) -> None:
        with self._telemetry_lock:
            self._telemetry.update(updates)

    def list_cameras(self, max_index: int = 4) -> list[dict[str, Any]]:
        """Probe available webcam indices without interrupting an active stream."""
        if cv2 is None:
            return []
        found: list[dict[str, Any]] = []
        consecutive_misses = 0
        for idx in range(max(1, max_index)):
            if self._running and idx == self.camera_index:
                found.append({"index": idx, "label": f"Camera {idx}"})
                consecutive_misses = 0
                continue
            cap = None
            try:
                if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW"):
                    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                else:
                    cap = cv2.VideoCapture(idx)
                if cap is not None and cap.isOpened():
                    found.append({"index": idx, "label": f"Camera {idx}"})
                    consecutive_misses = 0
                else:
                    consecutive_misses += 1
                    if idx >= 1 and consecutive_misses >= 2:
                        break
            except Exception:
                consecutive_misses += 1
                if idx >= 1 and consecutive_misses >= 2:
                    break
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
        if self._running and not any(c["index"] == self.camera_index for c in found):
            found.insert(0, {"index": self.camera_index, "label": f"Camera {self.camera_index}"})
        return found

    def is_available(self) -> bool:
        return _HAS_FACE_DEPS

    def status_code(self) -> str:
        if not _HAS_FACE_DEPS:
            return "missing_deps"
        if self._downloading:
            return "model_downloading"
        if self._status_code_override:
            return self._status_code_override
        if self._running:
            return "running"
        if resolve_model_path(self.data_dir) is None:
            return "model_missing"
        return "ready"

    def start(self, callback: SignalCallback) -> bool:
        if not self.is_available():
            return False
        self._callback = callback
        self._running = True
        self._last_error = ""
        self._status_code_override = ""
        self._stream_id += 1
        with self._frame_lock:
            self._latest_jpeg = None
        self._set_telemetry(
            fps=0.0,
            brightness=0.0,
            light_status="unknown",
            face_detected=False,
            enhanced=False,
            camera_index=self.camera_index,
            stream_id=self._stream_id,
        )
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        super().stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def _ensure_model(self) -> Path | None:
        existing = resolve_model_path(self.data_dir)
        if existing is not None:
            return existing
        target = get_data_dir(self.data_dir) / "models" / "face_landmarker.task"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".task.tmp")
        self._downloading = True
        try:
            logger.info("Downloading face_landmarker.task to %s", target)
            with urllib.request.urlopen(MODEL_URL, timeout=60) as resp:
                data = resp.read()
            digest = hashlib.sha256(data).hexdigest().lower()
            if digest != MODEL_SHA256:
                raise ValueError(f"Model SHA-256 mismatch: {digest}")
            tmp.write_bytes(data)
            tmp.replace(target)
            return target
        except Exception as exc:
            logger.error("Failed to download FaceLandmarker model: %s", exc)
            self._last_error = str(exc)
            self._status_code_override = "model_missing"
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            return None
        finally:
            self._downloading = False

    def _configure_capture(self, cap: Any) -> None:
        props: list[tuple[str, Any]] = [
            ("CAP_PROP_FRAME_WIDTH", 640),
            ("CAP_PROP_FRAME_HEIGHT", 480),
            ("CAP_PROP_FPS", 30),
            ("CAP_PROP_BUFFERSIZE", 1),
        ]
        if hasattr(cv2, "VideoWriter_fourcc"):
            try:
                props.insert(0, ("CAP_PROP_FOURCC", cv2.VideoWriter_fourcc(*"MJPG")))
            except Exception:
                pass
        for attr, val in props:
            prop_id = getattr(cv2, attr, None)
            if prop_id is not None:
                try:
                    cap.set(prop_id, val)
                except Exception:
                    pass

    def _open_camera(self):
        cap = None
        if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW"):
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = None
        if cap is None:
            cap = cv2.VideoCapture(self.camera_index)
        if cap is not None and cap.isOpened():
            self._configure_capture(cap)
        return cap

    def _run_loop(self) -> None:
        if cv2 is None or mp is None or mp_python is None or mp_vision is None:
            return

        model_path = self._ensure_model()
        if model_path is None or not self._running:
            self._running = False
            return

        cap = self._open_camera()
        if not cap.isOpened():
            self._status_code_override = "no_camera"
            self._last_error = "Webcam could not be opened"
            self._running = False
            return

        conf = 0.35 if self.low_light_mode else 0.5
        try:
            options = mp_vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_buffer=model_path.read_bytes()),
                running_mode=mp_vision.RunningMode.VIDEO,
                output_face_blendshapes=True,
                num_faces=1,
                min_face_detection_confidence=conf,
                min_face_presence_confidence=conf,
                min_tracking_confidence=conf,
            )
            landmarker = mp_vision.FaceLandmarker.create_from_options(options)
        except Exception as exc:
            self._status_code_override = "error"
            self._last_error = str(exc)
            cap.release()
            self._running = False
            return

        start_ms = int(time.monotonic() * 1000)
        prev_frame_ts = time.monotonic()
        ema_fps = 0.0
        hold = SignalHoldTracker(grace_sec=0.25)

        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.03)
                    continue

                frame = cv2.flip(frame, 1)
                proc_frame, brightness, enhanced = enhance_low_light_frame(
                    frame,
                    enabled=self.low_light_mode,
                )

                ok_enc, buf = cv2.imencode(".jpg", proc_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if ok_enc:
                    with self._frame_lock:
                        self._latest_jpeg = buf.tobytes()

                rgb = cv2.cvtColor(proc_frame, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                now = time.monotonic()
                dt = max(1e-3, now - prev_frame_ts)
                prev_frame_ts = now
                inst_fps = min(60.0, 1.0 / dt)
                ema_fps = inst_fps if ema_fps <= 0.0 else (ema_fps * 0.8 + inst_fps * 0.2)

                ts_ms = max(1, int(now * 1000) - start_ms)
                result = landmarker.detect_for_video(mp_img, ts_ms)

                face_detected = bool(result.face_landmarks)
                if face_detected:
                    bs = {}
                    if result.face_blendshapes:
                        bs = {b.category_name: b.score for b in result.face_blendshapes[0]}
                    signals = compute_signals(result.face_landmarks[0], bs, swap_eyes=self.swap_eyes)
                    out_signals = hold.on_detected(signals, now)
                    for channel, val in out_signals.items():
                        self.emit(channel, val, now)
                else:
                    held_signals, _ = hold.on_missed(now)
                    for channel, val in held_signals.items():
                        self.emit(channel, val, now)

                self._set_telemetry(
                    fps=round(ema_fps, 1),
                    brightness=round(brightness, 1),
                    light_status=light_quality_code(brightness),
                    face_detected=face_detected,
                    enhanced=enhanced,
                    camera_index=self.camera_index,
                )

                time.sleep(0.02)
        finally:
            self._set_telemetry(
                fps=0.0,
                face_detected=False,
                enhanced=False,
            )
            landmarker.close()
            cap.release()
