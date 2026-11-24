"""Download required MediaPipe FaceLandmarker model and verify its SHA-256 hash."""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "openplay" / "models" / "face_landmarker.task"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def main() -> int:
    if TARGET.exists() and TARGET.stat().st_size > 100_000:
        existing_hash = _sha256_bytes(TARGET.read_bytes())
        if existing_hash == MODEL_SHA256:
            print(f"Model already present and verified: {TARGET}")
            return 0
        print(f"Existing model hash mismatch ({existing_hash}), re-downloading...")

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    tmp = TARGET.with_suffix(".task.tmp")
    print(f"Downloading {MODEL_URL} -> {TARGET} ...")
    with urllib.request.urlopen(MODEL_URL, timeout=60) as resp:
        data = resp.read()

    digest = _sha256_bytes(data)
    if digest != MODEL_SHA256:
        raise RuntimeError(f"Model SHA-256 verification failed: expected {MODEL_SHA256}, got {digest}")

    tmp.write_bytes(data)
    tmp.replace(TARGET)
    print(f"Downloaded and verified {TARGET.stat().st_size} bytes (SHA-256: {digest}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
