"""Tests for Windows SendInput hardware scan-code key builder."""

from __future__ import annotations

import sys

import pytest

from openplay.core.models import OutputCommand, OutputType
from openplay.outputs.virtual_gamepad import VirtualGamepadAdapter
from openplay.outputs.windows_input import VK_CODES, WindowsInputAdapter, _USER32, build_key_input


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


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_vk_codes_expanded_and_user32_uses_last_error():
    import ctypes

    assert isinstance(_USER32, ctypes.WinDLL)
    # _FUNCFLAG_USE_LASTERROR (0x10) is set when WinDLL(..., use_last_error=True)
    assert bool(_USER32._FuncPtr._flags_ & 0x10)
    for ch in "0123456789abcdefghijklmnopqrstuvwxyz":
        assert ch in VK_CODES
        inp = build_key_input(VK_CODES[ch], pressed=True)
        assert inp.union.ki.wScan != 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_middle_mouse_button_supported(monkeypatch: pytest.MonkeyPatch):
    adapter = WindowsInputAdapter()
    sent_flags: list[int] = []
    monkeypatch.setattr(adapter, "_send_struct", lambda inp: sent_flags.append(inp.union.mi.dwFlags))

    assert adapter.send(OutputCommand(output_type=OutputType.MOUSE_BUTTON, target="middle", value=1.0)) is True
    assert adapter.send(OutputCommand(output_type=OutputType.MOUSE_BUTTON, target="middle", value=0.0)) is True
    assert adapter.send(OutputCommand(output_type=OutputType.MOUSE_BUTTON, target="unknown_btn", value=1.0)) is False
    assert sent_flags == [0x0020, 0x0040]


def test_virtual_gamepad_preserves_diagonal_axes():
    class _FakePad:
        def __init__(self) -> None:
            self.left_calls: list[tuple[float, float]] = []
            self.right_calls: list[tuple[float, float]] = []
            self.updates = 0

        def left_joystick_float(self, x_value_float: float, y_value_float: float) -> None:
            self.left_calls.append((x_value_float, y_value_float))

        def right_joystick_float(self, x_value_float: float, y_value_float: float) -> None:
            self.right_calls.append((x_value_float, y_value_float))

        def update(self) -> None:
            self.updates += 1

    adapter = VirtualGamepadAdapter()
    fake_pad = _FakePad()
    adapter._pad = fake_pad

    assert adapter.send(OutputCommand(output_type=OutputType.GAMEPAD_AXIS, target="lx", value=0.6)) is True
    assert adapter.send(OutputCommand(output_type=OutputType.GAMEPAD_AXIS, target="ly", value=-0.4)) is True
    assert fake_pad.left_calls == [(0.6, 0.0), (0.6, -0.4)]

    assert adapter.send(OutputCommand(output_type=OutputType.GAMEPAD_AXIS, target="rx", value=-0.8)) is True
    assert adapter.send(OutputCommand(output_type=OutputType.GAMEPAD_AXIS, target="ry", value=0.5)) is True
    assert fake_pad.right_calls == [(-0.8, 0.0), (-0.8, 0.5)]
    assert fake_pad.updates == 4
