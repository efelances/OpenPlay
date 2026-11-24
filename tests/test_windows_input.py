"""Tests for Windows SendInput hardware scan-code key builder."""

from __future__ import annotations

import sys

import pytest

from openplay.outputs.windows_input import VK_CODES, WindowsInputAdapter, build_key_input


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_build_key_input_uses_hardware_scancode():
    inp_down = build_key_input(VK_CODES["w"], pressed=True)
    ki = inp_down.union.ki
    assert ki.wVk == 0
    assert ki.wScan != 0
    assert ki.dwFlags & 0x0008  # KEYEVENTF_SCANCODE
    assert not (ki.dwFlags & 0x0002)  # not KEYUP

    inp_up = build_key_input(VK_CODES["w"], pressed=False)
    ki_up = inp_up.union.ki
    assert ki_up.dwFlags & 0x0008
    assert ki_up.dwFlags & 0x0002  # KEYEVENTF_KEYUP


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_extended_flag_set_for_arrow_keys():
    inp_up_arrow = build_key_input(VK_CODES["up"], pressed=True)
    assert inp_up_arrow.union.ki.dwFlags & 0x0001  # KEYEVENTF_EXTENDEDKEY


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_subpixel_mouse_accumulator(monkeypatch: pytest.MonkeyPatch):
    adapter = WindowsInputAdapter()
    moves: list[tuple[int, int]] = []
    monkeypatch.setattr(adapter, "_send_mouse_move", lambda dx, dy: moves.append((dx, dy)))

    adapter.send_mouse_delta_float(0.4, 0.0)
    adapter.send_mouse_delta_float(0.4, 0.0)
    assert moves == []

    adapter.send_mouse_delta_float(0.4, 0.0)
    assert moves == [(1, 0)]
    assert abs(adapter._rem_x - 0.2) < 1e-6
