"""Optional virtual Xbox 360 gamepad adapter via vgamepad (ViGEmBus)."""

from __future__ import annotations

from openplay.core.models import OutputCommand, OutputType
from openplay.outputs.base import OutputAdapter

try:
    import vgamepad as vg  # type: ignore

    _HAS_VGAMEPAD = True
except Exception:
    vg = None
    _HAS_VGAMEPAD = False


class VirtualGamepadAdapter(OutputAdapter):
    """Emulates a standard Xbox 360 controller for PC games."""

    name = "virtual_gamepad"

    def __init__(self) -> None:
        self._pad = None
        self._error = ""
        self._lx: float = 0.0
        self._ly: float = 0.0
        self._rx: float = 0.0
        self._ry: float = 0.0
        if _HAS_VGAMEPAD and vg is not None:
            try:
                self._pad = vg.VX360Gamepad()
            except Exception as exc:
                self._error = str(exc)

    def is_available(self) -> bool:
        return self._pad is not None

    def status_code(self) -> str:
        return "ready" if self._pad is not None else "missing_driver"

    def detail(self) -> str:
        return self._error

    def send(self, command: OutputCommand) -> bool:
        if self._pad is None:
            return False

        if command.output_type == OutputType.GAMEPAD_BUTTON:
            if vg is None:
                return False
            button_map = {
                "a": vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
                "b": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
                "x": vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
                "y": vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
                "lb": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
                "rb": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
                "start": vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
            }
            btn = button_map.get(command.target.lower())
            if btn is None:
                return False
            if command.value >= 0.5:
                self._pad.press_button(button=btn)
            else:
                self._pad.release_button(button=btn)
            self._pad.update()
            return True

        if command.output_type == OutputType.GAMEPAD_AXIS:
            val = max(-1.0, min(1.0, command.value))
            if command.target == "lx":
                self._lx = val
                self._pad.left_joystick_float(x_value_float=self._lx, y_value_float=self._ly)
            elif command.target == "ly":
                self._ly = val
                self._pad.left_joystick_float(x_value_float=self._lx, y_value_float=self._ly)
            elif command.target == "rx":
                self._rx = val
                self._pad.right_joystick_float(x_value_float=self._rx, y_value_float=self._ry)
            elif command.target == "ry":
                self._ry = val
                self._pad.right_joystick_float(x_value_float=self._rx, y_value_float=self._ry)
            else:
                return False
            self._pad.update()
            return True

        return False
