"""Unit tests for low-quality camera and microphone DSP enhancements."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

import numpy as np

from openplay.inputs.audio_dsp import AudioDSPProcessor
from openplay.inputs.camera_enhance import (
    SignalHoldTracker,
    assess_brightness,
    enhance_low_light_frame,
    light_quality_code,
)
from openplay.inputs.face_tracker import FaceTrackerProvider
from openplay.logging_setup import setup_logging


def test_low_light_enhancement_brightens_dark_frames_and_skips_bright():
    dark = np.full((120, 160, 3), 25, dtype=np.uint8)
    bright = np.full((120, 160, 3), 160, dtype=np.uint8)

    assert light_quality_code(25.0) == "very_dark"
    assert light_quality_code(75.0) == "low"
    assert light_quality_code(150.0) == "good"
    assert light_quality_code(240.0) == "overexposed"

    out_dark, b_dark, applied_dark = enhance_low_light_frame(dark, enabled=True)
    assert applied_dark is True
    assert b_dark < 30.0
    assert assess_brightness(out_dark) > b_dark + 35.0

    out_bright, b_bright, applied_bright = enhance_low_light_frame(bright, enabled=True)
    assert applied_bright is False
    assert b_bright >= 150.0
    assert np.array_equal(out_bright, bright)

    out_off, _, applied_off = enhance_low_light_frame(dark, enabled=False)
    assert applied_off is False
    assert np.array_equal(out_off, dark)


def test_signal_hold_tracker_grace_decays_analog_and_clears_digital():
    tracker = SignalHoldTracker(grace_sec=0.25, decay=0.8)
    tracker.on_detected(
        {"head_yaw": 0.5, "head_pitch": -0.25, "wink_left": 0.9, "mouth_open": 0.8},
        now=10.0,
    )

    held, active = tracker.on_missed(now=10.10)
    assert active is True
    assert abs(held["head_yaw"] - 0.4) < 1e-6
    assert abs(held["head_pitch"] - (-0.2)) < 1e-6
    assert held["wink_left"] == 0.0
    assert held["mouth_open"] == 0.0

    zeros, active_after = tracker.on_missed(now=10.40)
    assert active_after is False
    assert all(v == 0.0 for v in zeros.values())

    empty, active_again = tracker.on_missed(now=10.60)
    assert active_again is False
    assert empty == {}


def test_audio_dsp_rejects_50hz_hum_and_dc_across_sample_rates():
    for sr in (16000, 48000):
        n = int(sr * 0.032)
        t = np.arange(n, dtype=np.float32) / float(sr)
        hum_plus_dc = 0.25 + 0.12 * np.sin(2.0 * np.pi * 50.0 * t)
        voice_band = 0.08 * np.sin(2.0 * np.pi * 650.0 * t)

        dsp = AudioDSPProcessor(samplerate=sr, gain=4.0, noise_suppression=True, auto_gain=False, noise_floor=0.005)
        hum_level, _ = dsp.process_block(hum_plus_dc, now=1.0)
        voice_level, _ = dsp.process_block(voice_band, now=1.1)

        assert hum_level < 0.05
        assert voice_level > 0.20


def test_audio_dsp_ambient_calibration_gates_fan_noise_and_passes_puff():
    sr = 16000
    n = 512
    t = np.arange(n, dtype=np.float32) / float(sr)
    steady_fan = 0.025 * np.sin(2.0 * np.pi * 420.0 * t)
    puff = 0.16 * np.sin(2.0 * np.pi * 550.0 * t)

    dsp = AudioDSPProcessor(samplerate=sr, gain=5.0, noise_suppression=True, auto_gain=False)
    dsp.start_noise_calibration(duration_sec=0.5, now=0.0)

    lvl1, done1 = dsp.process_block(steady_fan, now=0.2)
    assert lvl1 == 0.0 and done1 is False

    lvl2, done2 = dsp.process_block(steady_fan, now=0.6)
    assert lvl2 == 0.0 and done2 is True
    assert dsp.noise_floor > 0.015

    gated_fan, _ = dsp.process_block(steady_fan, now=0.8)
    puff_level, _ = dsp.process_block(puff, now=0.9)
    assert gated_fan == 0.0
    assert puff_level > 0.35


def test_audio_dsp_auto_gain_lifts_quiet_mic():
    sr = 16000
    t = np.arange(512, dtype=np.float32) / float(sr)
    quiet_signal = 0.03 * np.sin(2.0 * np.pi * 700.0 * t)

    dsp_no_agc = AudioDSPProcessor(samplerate=sr, gain=4.0, noise_suppression=False, auto_gain=False)
    dsp_agc = AudioDSPProcessor(samplerate=sr, gain=4.0, noise_suppression=False, auto_gain=True)

    lvl_no_agc = 0.0
    lvl_agc = 0.0
    for i in range(40):
        lvl_no_agc, _ = dsp_no_agc.process_block(quiet_signal, now=float(i) * 0.03)
        lvl_agc, _ = dsp_agc.process_block(quiet_signal, now=float(i) * 0.03)

    assert lvl_agc > lvl_no_agc * 2.0


def test_audio_dsp_caches_fft_tables_and_calibration_is_thread_safe():
    dsp = AudioDSPProcessor(samplerate=16000, noise_suppression=True)
    block = 0.05 * np.sin(2.0 * np.pi * 600.0 * (np.arange(512, dtype=np.float32) / 16000.0))

    dsp.process_block(block, now=0.1)
    win1 = dsp._cached_win
    freqs1 = dsp._cached_freqs
    dsp.process_block(block, now=0.2)
    assert dsp._cached_win is win1
    assert dsp._cached_freqs is freqs1

    # Different samplerate invalidates and rebuilds cache
    dsp.samplerate = 48000.0
    dsp.process_block(block, now=0.3)
    assert dsp._fft_cache_key == (512, 48000.0)
    assert dsp._cached_freqs is not freqs1

    # Concurrent calibration + processing + telemetry does not raise
    errors: list[Exception] = []

    def _worker():
        try:
            for idx in range(30):
                dsp.process_block(block)
                if idx % 10 == 0:
                    dsp.get_telemetry()
        except Exception as exc:
            errors.append(exc)

    dsp.start_noise_calibration(duration_sec=0.2)
    threads = [threading.Thread(target=_worker) for _ in range(3)]
    for t_obj in threads:
        t_obj.start()
    for t_obj in threads:
        t_obj.join()
    assert errors == []


def test_face_tracker_stream_id_increments_and_exposes_in_info(monkeypatch, tmp_path: Path):
    tracker = FaceTrackerProvider(data_dir=tmp_path)
    monkeypatch.setattr(tracker, "is_available", lambda: True)
    monkeypatch.setattr(tracker, "_run_loop", lambda: None)

    assert tracker.stream_id == 0
    assert tracker.start(lambda _sig: None) is True
    assert tracker.stream_id == 1
    assert tracker.info()["stream_id"] == 1
    tracker.stop()

    assert tracker.start(lambda _sig: None) is True
    assert tracker.stream_id == 2
    assert tracker.info()["stream_id"] == 2
    tracker.stop()


def test_logging_setup_separates_stdio_log_from_rotating_log(monkeypatch, tmp_path: Path):
    import openplay.logging_setup as ls

    monkeypatch.setattr(ls, "_CONFIGURED", False)
    root_logger = logging.getLogger("openplay")
    old_handlers = list(root_logger.handlers)
    root_logger.handlers.clear()

    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        monkeypatch.setattr(sys, "stdout", None)
        monkeypatch.setattr(sys, "stderr", None)
        log_file = setup_logging(tmp_path / "logs")
        assert log_file.name == "openplay.log"
        assert (tmp_path / "logs" / "stdio.log").exists()
        assert sys.stdout is not None and Path(sys.stdout.name).name == "stdio.log"

        # RotatingFileHandler rollover must succeed without WinError 32
        root_logger.info("hello before rollover")
        for h in root_logger.handlers:
            if hasattr(h, "doRollover"):
                h.doRollover()
        assert (tmp_path / "logs" / "openplay.log.1").exists()
    finally:
        for h in list(root_logger.handlers):
            h.close()
        root_logger.handlers.clear()
        root_logger.handlers.extend(old_handlers)
        if sys.stdout not in (None, old_stdout):
            sys.stdout.close()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
