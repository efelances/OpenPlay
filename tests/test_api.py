"""FastAPI integration, security hardening, and settings persistence tests."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

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
