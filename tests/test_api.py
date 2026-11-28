"""FastAPI integration, security hardening, and settings persistence tests."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from openplay import __version__
from openplay.app import create_app


def test_root_state_and_i18n_endpoints(fresh_data_dir: Path):
    with TestClient(create_app(data_dir=fresh_data_dir)) as client:
        r_home = client.get("/")
        assert r_home.status_code == 200
        assert "OpenPlay Access" in r_home.text
        assert r_home.headers.get("x-content-type-options") == "nosniff"
        assert r_home.headers.get("x-frame-options") == "DENY"
        assert "default-src 'self'" in r_home.headers.get("content-security-policy", "")

        r_state = client.get("/api/state")
        assert r_state.status_code == 200
        state = r_state.json()
        assert state["version"] == __version__ == "0.4.0"
        assert state["active_profile"]["id"] == "hybrid_head_eye_action"
        assert len(state["profiles"]) == 8
        assert "voice_languages" in state
        assert state["settings"]["safe_test_mode"] is True

        r_xx = client.get("/api/i18n/xx")
        assert r_xx.status_code == 200
        assert r_xx.json()["tab.home"] == "Home"


def test_security_blocks_unauthenticated_and_cross_origin_requests(fresh_data_dir: Path):
    with TestClient(create_app(data_dir=fresh_data_dir)) as client:
        # Without session cookie -> POST /api/* and /api/camera/stream are rejected
        r_no_cookie_post = client.post("/api/tuning", json={"sensitivity": 2.0})
        assert r_no_cookie_post.status_code == 403

        r_no_cookie_cam = client.get("/api/camera/stream")
        assert r_no_cookie_cam.status_code == 403

        # Obtain valid session cookie
        assert client.get("/").status_code == 200

        # DNS rebinding Host rejection
        r_bad_host = client.get("/api/state", headers={"Host": "evil.com"})
        assert r_bad_host.status_code == 403

        # Cross-origin Origin rejection
        r_bad_origin = client.post(
            "/api/tuning",
            json={"sensitivity": 2.0},
            headers={"Origin": "https://evil.com"},
        )
        assert r_bad_origin.status_code == 403

        # Cross-site Sec-Fetch-Site rejection
        r_cross_site = client.get("/api/camera/stream", headers={"Sec-Fetch-Site": "cross-site"})
        assert r_cross_site.status_code == 403


def test_settings_language_tuning_and_safe_startup_persist(fresh_data_dir: Path):
    with TestClient(create_app(data_dir=fresh_data_dir)) as client:
        assert client.get("/").status_code == 200
        cur = client.get("/api/state").json()["settings"]
        cur["language"] = "de"
        cur["safe_test_mode"] = False
        r_upd = client.post("/api/settings", json=cur)
        assert r_upd.status_code == 200
        assert r_upd.json()["settings"]["language"] == "de"

        r_tune = client.post("/api/tuning", json={"sensitivity": 2.3, "smoothing": 0.65})
        assert r_tune.status_code == 200

    settings_file = fresh_data_dir / "settings.json"
    assert settings_file.exists()
    raw = json.loads(settings_file.read_text(encoding="utf-8"))
    assert raw["settings"]["language"] == "de"

    # Reopen app from same data_dir: language, sensitivity & smoothing persist, safe_test_mode resets to True
    with TestClient(create_app(data_dir=fresh_data_dir)) as client2:
        st2 = client2.get("/api/state").json()
        assert st2["settings"]["language"] == "de"
        assert st2["settings"]["safe_test_mode"] is True
        head_x = next(r for r in st2["active_profile"]["rules"] if r["id"] == "hybrid_head_x")
        assert head_x["sensitivity"] == 2.3
        assert head_x["smoothing"] == 0.65


def test_wizard_apply_preserves_language_and_marks_onboarding_done(fresh_data_dir: Path):
    with TestClient(create_app(data_dir=fresh_data_dir)) as client:
        assert client.get("/").status_code == 200
        cur = client.get("/api/state").json()["settings"]
        cur["language"] = "es"
        client.post("/api/settings", json=cur)

        r_wiz = client.post(
            "/api/wizard/apply",
            json={
                "abilities": ["one_hand"],
                "support_needs": ["high_contrast"],
                "equipment": ["keyboard_mouse"],
                "game_genre": "strategy",
            },
        )
        assert r_wiz.status_code == 200
        st = r_wiz.json()
        assert st["settings"]["language"] == "es"
        assert st["settings"]["onboarding_done"] is True
        assert st["settings"]["high_contrast"] is True
        assert st["active_profile"]["id"] == "one_hand_assist"


def test_per_channel_thresholds_persist_independently(fresh_data_dir: Path):
    with TestClient(create_app(data_dir=fresh_data_dir)) as client:
        assert client.get("/").status_code == 200
        r_tune = client.post(
            "/api/tuning",
            json={"channel_thresholds": {"eyebrow_raise": 0.75, "mouth_open": 0.30}},
        )
        assert r_tune.status_code == 200
        rules = {r["channel"]: r["threshold"] for r in r_tune.json()["active_profile"]["rules"]}
        assert rules["eyebrow_raise"] == 0.75
        assert rules["mouth_open"] == 0.30
        assert rules["wink_left"] == 0.45

    with TestClient(create_app(data_dir=fresh_data_dir)) as client2:
        rules2 = {
            r["channel"]: r["threshold"]
            for r in client2.get("/api/state").json()["active_profile"]["rules"]
        }
        assert rules2["eyebrow_raise"] == 0.75
        assert rules2["mouth_open"] == 0.30
        assert rules2["wink_left"] == 0.45


def test_diagnostics_endpoint_reports_expected_checks(fresh_data_dir: Path):
    with TestClient(create_app(data_dir=fresh_data_dir)) as client:
        r_diag = client.get("/api/diagnostics")
        assert r_diag.status_code == 200
        ids = {c["id"] for c in r_diag.json()["checks"]}
        assert {
            "python",
            "data_dir_writable",
            "web_assets",
            "locales",
            "face_deps",
            "face_model_load",
            "camera",
            "microphone",
            "tts_voices",
            "send_input",
            "vgamepad",
        }.issubset(ids)


def test_devices_noise_calibration_and_hardware_settings_persist(fresh_data_dir: Path):
    with TestClient(create_app(data_dir=fresh_data_dir)) as client:
        r_no_cookie = client.post("/api/audio/calibrate-noise")
        assert r_no_cookie.status_code == 403

        r_devs = client.get("/api/devices")
        assert r_devs.status_code == 200
        devs = r_devs.json()
        assert "cameras" in devs and "microphones" in devs

        assert client.get("/").status_code == 200
        cur = client.get("/api/state").json()["settings"]
        cur["camera_index"] = 1
        cur["low_light_camera_mode"] = False
        cur["mic_gain"] = 8.5
        cur["mic_noise_suppression"] = True
        cur["mic_auto_gain"] = False
        cur["mic_noise_floor"] = 0.042
        r_upd = client.post("/api/settings", json=cur)
        assert r_upd.status_code == 200
        saved = r_upd.json()["settings"]
        assert saved["camera_index"] == 1
        assert saved["low_light_camera_mode"] is False
        assert saved["mic_gain"] == 8.5
        assert saved["mic_auto_gain"] is False
        assert saved["mic_noise_floor"] == 0.042

        r_cal = client.post("/api/audio/calibrate-noise")
        assert r_cal.status_code == 200
        assert "telemetry" in r_cal.json()

    with TestClient(create_app(data_dir=fresh_data_dir)) as client2:
        st2 = client2.get("/api/state").json()["settings"]
        assert st2["camera_index"] == 1
        assert st2["low_light_camera_mode"] is False
        assert st2["mic_gain"] == 8.5
        assert st2["mic_noise_floor"] == 0.042


def test_single_switch_scan_thresholds_persist_via_tuning(fresh_data_dir: Path):
    with TestClient(create_app(data_dir=fresh_data_dir)) as client:
        assert client.get("/").status_code == 200
        r_prof = client.post("/api/profile/single_switch_scan")
        assert r_prof.status_code == 200

        r_tune = client.post(
            "/api/tuning",
            json={"channel_thresholds": {"mouth_open": 0.80, "audio_level": 0.70}},
        )
        assert r_tune.status_code == 200
        scan = r_tune.json()["active_profile"]["switch_scan"]
        assert scan["face_threshold"] == 0.80
        assert scan["audio_threshold"] == 0.70

    with TestClient(create_app(data_dir=fresh_data_dir)) as client2:
        scan2 = client2.get("/api/state").json()["active_profile"]["switch_scan"]
        assert scan2["face_threshold"] == 0.80
        assert scan2["audio_threshold"] == 0.70


def test_devices_and_diagnostics_run_in_threadpool(fresh_data_dir: Path, monkeypatch):
    import asyncio
    import threading

    import openplay.app as app_mod

    main_tid = threading.get_ident()
    seen_tids: dict[str, int] = {}

    def _fake_diag(_runtime):
        seen_tids["diag"] = threading.get_ident()
        return [{"id": "python", "status": "ok", "detail": "test"}]

    monkeypatch.setattr(app_mod, "run_diagnostics", _fake_diag)

    with TestClient(create_app(data_dir=fresh_data_dir)) as client:
        orig_list = client.app.state.runtime.list_devices

        def _wrapped_devices():
            seen_tids["devices"] = threading.get_ident()
            return orig_list()

        monkeypatch.setattr(client.app.state.runtime, "list_devices", _wrapped_devices)
        assert client.get("/api/diagnostics").status_code == 200
        assert client.get("/api/devices").status_code == 200

    assert seen_tids["diag"] != main_tid
    assert seen_tids["devices"] != main_tid


def test_assist_profiles_trigger_via_simulate_and_tick(fresh_data_dir: Path):
    with TestClient(create_app(data_dir=fresh_data_dir)) as client:
        assert client.get("/").status_code == 200

        r_one = client.post("/api/profile/one_hand_assist")
        assert r_one.status_code == 200
        channels = {r["channel"] for r in r_one.json()["active_profile"]["rules"]}
        assert {"assist_toggle_walk", "assist_toggle_sprint", "assist_macro_1"}.issubset(channels)

        assert client.post(
            "/api/simulate",
            json={"channel": "assist_toggle_walk", "value": 1.0, "source": "keyboard_assist"},
        ).status_code == 200
        st = client.get("/api/state").json()
        assert st["active_toggles"]["toggle_walk"] is True

        r_blind = client.post("/api/profile/blind_audio_guided")
        assert r_blind.status_code == 200
        assert client.post(
            "/api/simulate",
            json={"channel": "assist_macro_1", "value": 1.0, "source": "keyboard_assist"},
        ).status_code == 200
        st_blind = client.get("/api/state").json()
        assert st_blind["recent_outputs"][0]["target"] == "e"
