"""Zero-dependency Windows SendInput output adapter using hardware scan codes."""

from __future__ import annotations

import ctypes
import logging
import math
import sys

from openplay.core.models import OutputCommand, OutputType
from openplay.outputs.base import OutputAdapter

logger = logging.getLogger(__name__)
_IS_WINDOWS = sys.platform == "win32"
_USER32 = ctypes.WinDLL("user32", use_last_error=True) if _IS_WINDOWS else None

# Virtual-Key codes for alphanumeric and common gaming keys
VK_CODES: dict[str, int] = {
    **{str(d): 0x30 + d for d in range(10)},
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    "space": 0x20,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "tab": 0x09,
    "enter": 0x0D,
    "esc": 0x1B,
    "backspace": 0x08,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}
VK_CODES = {k.lower(): v for k, v in VK_CODES.items()}

_EXTENDED_VKS = frozenset({0x25, 0x26, 0x27, 0x28})

if _IS_WINDOWS:
    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("union", _INPUT_UNION)]

    _INPUT_MOUSE = 0
    _INPUT_KEYBOARD = 1
    _KEYEVENTF_EXTENDEDKEY = 0x0001
    _KEYEVENTF_KEYUP = 0x0002
    _KEYEVENTF_SCANCODE = 0x0008
    _MOUSEEVENTF_MOVE = 0x0001
    _MOUSEEVENTF_LEFTDOWN = 0x0002
    _MOUSEEVENTF_LEFTUP = 0x0004
    _MOUSEEVENTF_RIGHTDOWN = 0x0008
    _MOUSEEVENTF_RIGHTUP = 0x0010
    _MOUSEEVENTF_MIDDLEDOWN = 0x0020
    _MOUSEEVENTF_MIDDLEUP = 0x0040


def build_key_input(vk: int, pressed: bool) -> "_INPUT":
    """Build a Windows SendInput KEYBDINPUT struct using hardware scan codes."""
    if not _IS_WINDOWS or _USER32 is None:
        raise RuntimeError("build_key_input is only supported on Windows")
    scan = _USER32.MapVirtualKeyW(vk, 0)
    flags = _KEYEVENTF_SCANCODE
    if not pressed:
        flags |= _KEYEVENTF_KEYUP
    if vk in _EXTENDED_VKS:
        flags |= _KEYEVENTF_EXTENDEDKEY
    return _INPUT(
        type=_INPUT_KEYBOARD,
        union=_INPUT_UNION(ki=_KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)),
    )


class WindowsInputAdapter(OutputAdapter):
    """Injects real keyboard & mouse events on Windows via SendInput."""

    name = "windows_input"

    def __init__(self, mouse_speed: float = 18.0) -> None:
        self.mouse_speed = mouse_speed
        self._rem_x: float = 0.0
        self._rem_y: float = 0.0

    def reset_mouse_remainder(self) -> None:
        self._rem_x = 0.0
        self._rem_y = 0.0

    def send_mouse_delta_float(self, dx: float, dy: float) -> bool:
        """Accumulate sub-pixel mouse deltas and emit integer SendInput moves."""
        if not _IS_WINDOWS:
            return False
        self._rem_x += dx
        self._rem_y += dy
        ix = int(math.trunc(self._rem_x))
        iy = int(math.trunc(self._rem_y))
        self._rem_x -= ix
        self._rem_y -= iy
        if ix != 0 or iy != 0:
            self._send_mouse_move(ix, iy)
        return True

    def is_available(self) -> bool:
        return _IS_WINDOWS

    def status_code(self) -> str:
        return "ready" if _IS_WINDOWS else "windows_only"

    def send(self, command: OutputCommand) -> bool:
        if not _IS_WINDOWS:
            return False

        if command.output_type == OutputType.KEYBOARD:
            vk = VK_CODES.get(command.target.lower())
            if vk is None:
                return False
            self._send_key(vk, pressed=command.value >= 0.5)
            return True

        if command.output_type == OutputType.MOUSE_BUTTON:
            return self._send_mouse_button(command.target.lower(), pressed=command.value >= 0.5)

        if command.output_type == OutputType.MOUSE_AXIS:
            delta = command.value * self.mouse_speed
            dx = delta if command.target == "mouse_x" else 0.0
            dy = delta if command.target == "mouse_y" else 0.0
            return self.send_mouse_delta_float(dx, dy)

        return False

    def _send_struct(self, inp: "_INPUT") -> None:
        if _USER32 is None:
            return
        sent = _USER32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        if sent == 0:
            err = ctypes.get_last_error()
            logger.warning("SendInput returned 0 (lastError=%s)", err)

    def _send_key(self, vk: int, pressed: bool) -> None:
        self._send_struct(build_key_input(vk, pressed))

    def _send_mouse_button(self, button: str, pressed: bool) -> bool:
        if button == "left":
            flag = _MOUSEEVENTF_LEFTDOWN if pressed else _MOUSEEVENTF_LEFTUP
        elif button == "right":
            flag = _MOUSEEVENTF_RIGHTDOWN if pressed else _MOUSEEVENTF_RIGHTUP
        elif button == "middle":
            flag = _MOUSEEVENTF_MIDDLEDOWN if pressed else _MOUSEEVENTF_MIDDLEUP
        else:
            return False
        inp = _INPUT(
            type=_INPUT_MOUSE,
            union=_INPUT_UNION(mi=_MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flag, time=0, dwExtraInfo=0)),
        )
        self._send_struct(inp)
        return True

    def _send_mouse_move(self, dx: int, dy: int) -> None:
        inp = _INPUT(
            type=_INPUT_MOUSE,
            union=_INPUT_UNION(mi=_MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=_MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0)),
        )
        self._send_struct(inp)
