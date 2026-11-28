"""CLI / desktop entrypoint: python -m openplay [--web] [--smoke-test] [--smoke-out PATH] [--port N]."""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn

from openplay.app import create_app
from openplay.core.models import SUPPORTED_LANGUAGES
from openplay.hotkeys import GlobalHotkeyMonitor
from openplay.i18n import t
from openplay.logging_setup import setup_logging
from openplay.paths import get_data_dir

logger = logging.getLogger("openplay.main")


def _show_error_box(title: str, message: str) -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x30)
            return
        except Exception:
            pass
    print(f"[{title}] {message}", file=sys.stderr)


def _acquire_single_instance_mutex() -> Any:
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, "OpenPlayAccess_SingleInstance")
    err = kernel32.GetLastError()
    if err == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def _find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _wait_for_server(host: str, port: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.08)
    return False


def _http_get(url: str, timeout: float = 5.0) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8")


def _run_smoke_test(base_url: str, out_path: Path) -> bool:
    report: dict[str, Any] = {"ok": False, "checks": {}, "diagnostics": []}
    ok = True
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())

    def _get(url: str, timeout: float = 5.0) -> tuple[int, str]:
        with opener.open(url, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8")

    try:
        for path in ("/", "/static/app.js", "/api/state"):
            status, _ = _get(f"{base_url}{path}")
            report["checks"][path] = status
            if status != 200:
                ok = False

        for lang in SUPPORTED_LANGUAGES:
            status, body = _get(f"{base_url}/api/i18n/{lang}")
            parsed = json.loads(body)
            report["checks"][f"/api/i18n/{lang}"] = {"status": status, "keys": len(parsed)}
            if status != 200 or not parsed:
                ok = False

        status, diag_body = _get(f"{base_url}/api/diagnostics", timeout=15.0)
        diag_data = json.loads(diag_body)
        checks = diag_data.get("checks", [])
        report["diagnostics"] = checks
        face_check = next((c for c in checks if c.get("id") == "face_model_load"), None)
        if status != 200 or not face_check or face_check.get("status") != "ok":
            ok = False
    except Exception as exc:
        report["error"] = str(exc)
        ok = False

    report["ok"] = ok
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openplay", description="OpenPlay Access")
    parser.add_argument("--web", action="store_true", help="Open UI in default web browser")
    parser.add_argument("--smoke-test", action="store_true", help="Run headless verification and exit")
    parser.add_argument("--smoke-out", type=str, default="", help="Output path for smoke-test JSON")
    parser.add_argument("--port", type=int, default=0, help="Port to bind (0 = auto free port)")
    args = parser.parse_args(argv)

    data_dir = get_data_dir()
    log_file = setup_logging(data_dir / "logs")

    mutex_handle = None
    if not args.smoke_test:
        mutex_handle = _acquire_single_instance_mutex()
        if mutex_handle is None:
            from openplay.settings_store import SettingsStore

            lang = SettingsStore(data_dir / "settings.json").load()["settings"]["language"]
            _show_error_box("OpenPlay Access", t(lang, "app.already_running"))
            return 0

    host = "127.0.0.1"
    port = args.port if args.port > 0 else _find_free_port(host)
    base_url = f"http://{host}:{port}"

    app = create_app(data_dir=data_dir)
    runtime = app.state.runtime

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_config=None,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    if not _wait_for_server(host, port, timeout=20.0):
        logger.error("Server failed to start on %s", base_url)
        _show_error_box(
            "OpenPlay Access",
            t(runtime.settings.language, "app.server_failed", log_dir=str(log_file.parent)),
        )
        server.should_exit = True
        return 1

    if args.smoke_test:
        out_path = Path(args.smoke_out) if args.smoke_out else (Path(tempfile.gettempdir()) / "openplay_smoke.json")
        ok = _run_smoke_test(base_url, out_path)
        server.should_exit = True
        server_thread.join(timeout=3.0)
        return 0 if ok else 1

    hotkeys = GlobalHotkeyMonitor(
        on_emergency=runtime.emergency_stop,
        on_channel=lambda ch, val: runtime.keyboard_assist.trigger_channel(ch, val),
    )
    hotkeys.start()
    runtime.announce_key("announce.welcome")

    try:
        if args.web:
            logger.info("Opening browser at %s", base_url)
            webbrowser.open(base_url)
            server_thread.join()
            return 0

        try:
            import webview  # type: ignore

            webview.create_window(
                "OpenPlay Access",
                base_url,
                width=1120,
                height=780,
                min_size=(820, 600),
                background_color="#F7F5F0",
            )
            webview_storage = data_dir / "webview"
            webview_storage.mkdir(parents=True, exist_ok=True)
            webview.start(private_mode=False, storage_path=str(webview_storage))
            return 0
        except ImportError:
            logger.warning("pywebview unavailable, opening browser instead")
            webbrowser.open(base_url)
            server_thread.join()
            return 0
    finally:
        hotkeys.stop()
        server.should_exit = True
        server_thread.join(timeout=3.0)
        if mutex_handle and sys.platform == "win32":
            try:
                ctypes.windll.kernel32.CloseHandle(mutex_handle)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
