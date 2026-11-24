"""FastAPI application factory and HTTP/WebSocket routes with localhost security."""

from __future__ import annotations

import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from openplay import __version__
from openplay.core.models import AccessibilitySettings
from openplay.core.wizard import WizardAnswers, recommend_setup
from openplay.diagnostics import run_diagnostics
from openplay.i18n import get_dict
from openplay.inputs.face_tracker import FaceTrackerProvider
from openplay.paths import WEB_DIR
from openplay.runtime import AccessRuntime

_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "testserver"})
_ALLOWED_FETCH_SITES = frozenset({"same-origin", "none"})
_SESSION_COOKIE = "openplay_session"

_CSP_HEADER = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self' ws://127.0.0.1:* ws://localhost:*"
)


def _is_allowed_host(host_header: str) -> bool:
    if not host_header:
        return False
    host = host_header.split(":")[0].strip().lower()
    return host in _ALLOWED_HOSTS


def _is_allowed_origin(origin_header: str) -> bool:
    if not origin_header:
        return True
    try:
        parsed = urlparse(origin_header)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in _ALLOWED_HOSTS


def _has_valid_session(
    cookies: Mapping[str, str],
    headers: Mapping[str, str],
    expected_token: str,
) -> bool:
    cookie_val = cookies.get(_SESSION_COOKIE) or ""
    header_val = headers.get("x-openplay-token") or ""
    if cookie_val and secrets.compare_digest(cookie_val, expected_token):
        return True
    if header_val and secrets.compare_digest(header_val, expected_token):
        return True
    return False


class SimulateRequest(BaseModel):
    channel: str
    value: float
    source: str | None = None


class CalibrateRequest(BaseModel):
    channels: list[str] = ["head_yaw", "head_pitch", "gaze_x", "gaze_y"]
    reset: bool = False


class TuningRequest(BaseModel):
    sensitivity: float | None = None
    deadzone: float | None = None
    smoothing: float | None = None
    threshold: float | None = None
    channel_thresholds: dict[str, float] | None = None
    invert_x: bool | None = None
    invert_y: bool | None = None


class SpeakRequest(BaseModel):
    text: str


def create_app(data_dir: Path | None = None) -> FastAPI:
    """Create a configured FastAPI instance backed by an isolated AccessRuntime."""
    runtime = AccessRuntime(data_dir=data_dir)
    session_token = secrets.token_urlsafe(24)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        loop = asyncio.get_running_loop()
        runtime.attach_loop(loop)

        async def _ticker():
            while True:
                runtime.tick()
                await asyncio.sleep(0.05)

        async def _signal_flusher():
            while True:
                runtime.flush_signals()
                await asyncio.sleep(1.0 / 15.0)

        async def _mouse_pump():
            last = time.monotonic()
            while True:
                await asyncio.sleep(0.01)
                now = time.monotonic()
                dt = min(0.05, max(0.001, now - last))
                last = now
                runtime.step_mouse(dt)

        ticker_task = asyncio.create_task(_ticker())
        flusher_task = asyncio.create_task(_signal_flusher())
        mouse_task = asyncio.create_task(_mouse_pump())
        try:
            yield
        finally:
            ticker_task.cancel()
            flusher_task.cancel()
            mouse_task.cancel()
            runtime.shutdown()

    app = FastAPI(title="OpenPlay Access", version=__version__, lifespan=lifespan)
    app.state.runtime = runtime
    app.state.session_token = session_token

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        host = request.headers.get("host", "")
        if not _is_allowed_host(host):
            return JSONResponse({"detail": "Forbidden host"}, status_code=403)

        origin = request.headers.get("origin", "")
        if not _is_allowed_origin(origin):
            return JSONResponse({"detail": "Forbidden origin"}, status_code=403)

        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        if fetch_site and fetch_site not in _ALLOWED_FETCH_SITES:
            return JSONResponse({"detail": "Forbidden cross-site request"}, status_code=403)

        path = request.url.path
        requires_session = (
            (request.method == "POST" and path.startswith("/api/"))
            or path == "/api/camera/stream"
        )
        if requires_session and not _has_valid_session(request.cookies, request.headers, session_token):
            return JSONResponse({"detail": "Missing or invalid session token"}, status_code=403)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = _CSP_HEADER
        return response

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    async def index():
        resp = FileResponse(WEB_DIR / "index.html")
        resp.set_cookie(
            _SESSION_COOKIE,
            session_token,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return resp

    @app.get("/api/state")
    async def get_state():
        return runtime.get_state_snapshot()

    @app.get("/api/i18n/{lang}")
    async def get_i18n(lang: str):
        return get_dict(lang)

    @app.get("/api/diagnostics")
    async def get_diagnostics():
        return {"checks": run_diagnostics(runtime)}

    @app.get("/api/devices")
    async def get_devices():
        return runtime.list_devices()

    @app.post("/api/audio/calibrate-noise")
    async def calibrate_mic_noise():
        return runtime.calibrate_mic_noise()

    @app.post("/api/profile/{profile_id}")
    async def select_profile(profile_id: str):
        return runtime.switch_profile(profile_id)

    @app.post("/api/settings")
    async def update_settings(new_settings: AccessibilitySettings):
        return runtime.update_settings(new_settings)

    @app.post("/api/speak")
    async def speak_text(req: SpeakRequest):
        if runtime.settings.tts_enabled:
            runtime.tts.speak(runtime.settings.language, req.text)
        return {"ok": True}

    @app.post("/api/inputs/{name}/toggle")
    async def toggle_input(name: str):
        return runtime.toggle_input(name)

    @app.post("/api/calibrate")
    async def calibrate(req: CalibrateRequest):
        return runtime.calibrate(req.channels, reset=req.reset)

    @app.post("/api/tuning")
    async def update_tuning(req: TuningRequest):
        return runtime.update_tuning(
            sensitivity=req.sensitivity,
            deadzone=req.deadzone,
            smoothing=req.smoothing,
            threshold=req.threshold,
            channel_thresholds=req.channel_thresholds,
            invert_x=req.invert_x,
            invert_y=req.invert_y,
        )

    @app.get("/api/camera/stream")
    async def camera_stream():
        face_provider = runtime.inputs.get("face_tracker")
        if not isinstance(face_provider, FaceTrackerProvider) or not face_provider.is_running:
            raise HTTPException(status_code=404, detail="Camera is not active")

        async def frame_gen():
            while face_provider.is_running:
                jpg = face_provider.get_latest_jpeg()
                if jpg:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                await asyncio.sleep(0.05)

        return StreamingResponse(frame_gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.post("/api/simulate")
    async def simulate_input(req: SimulateRequest):
        runtime.keyboard_assist.trigger_channel(
            channel=req.channel,
            value=req.value,
            source_override=req.source,
        )
        return {"ok": True}

    @app.post("/api/emergency-stop")
    async def emergency_stop():
        return runtime.emergency_stop()

    @app.post("/api/wizard/recommend")
    async def wizard_recommend(answers: WizardAnswers):
        return recommend_setup(answers).model_dump()

    @app.post("/api/wizard/apply")
    async def wizard_apply(answers: WizardAnswers):
        return runtime.apply_wizard(answers)

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        origin = ws.headers.get("origin", "")
        fetch_site = ws.headers.get("sec-fetch-site", "").lower()
        if (
            not _is_allowed_origin(origin)
            or (fetch_site and fetch_site not in _ALLOWED_FETCH_SITES)
            or not _has_valid_session(ws.cookies, ws.headers, session_token)
        ):
            await ws.close(code=1008)
            return

        await runtime.register_ws(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            runtime.unregister_ws(ws)

    return app
