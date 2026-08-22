#!/usr/bin/env python3
"""adb-backed device control for the Dolphin MCP server.

The GDB stub covers guest memory and CPU state, but not the things around it:
seeing what is on screen, pressing a button, knowing whether the app is even
running. Those go through adb.

Controller input is synthesized with `sendevent` on the gamepad's own event
node rather than `input keyevent`, for two reasons. `input keyevent` sends a
down and an up together, so it cannot hold Select while pressing R1 - which is
exactly the shape of every hotkey this fork adds. And writing to the real node
means the emulator sees ordinary hardware input, with no special-casing.

This works because Android puts the shell user in the `input` group and the
event nodes are mode 660 `root:input`. No root required.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Sequence

DEFAULT_PACKAGE = "org.dolphinemu.dolphinemu"

EV_SYN = 0
EV_KEY = 1
EV_ABS = 3

# Linux evdev codes. Android's generic gamepad key layout maps BTN_NORTH to
# BUTTON_X and BTN_WEST to BUTTON_Y, which is why those two look transposed.
BUTTONS = {
    "a": 0x130,
    "b": 0x131,
    "c": 0x132,
    "x": 0x133,
    "y": 0x134,
    "z": 0x135,
    "l1": 0x136,
    "r1": 0x137,
    "l2": 0x138,
    "r2": 0x139,
    "select": 0x13A,
    "start": 0x13B,
    "mode": 0x13C,
    "thumbl": 0x13D,
    "thumbr": 0x13E,
    "up": 0x220,
    "down": 0x221,
    "left": 0x222,
    "right": 0x223,
}

# Right stick. The left stick is ABS_X/ABS_Y (0/1); see the verified axis table
# in AGENTS.md - this pad has no ABS_RY, so vertical is ABS_RZ.
ABS_RIGHT_X = 2
ABS_RIGHT_Y = 5
STICK_FULL = 32767

#: Emulator packages that share this device. A run taken while one of these is
#: burning CPU is not worth having.
RIVAL_PATTERN = (
    "armsx2|eden_emulator|rpcsx|rpcs3|vita3k|azahar|citra|yuzu|cemu|xenia|pcsx|"
    "ppsspp|melon|duckstation|retroarch"
)


class DeviceError(RuntimeError):
    """adb was unavailable, or a command failed in a way worth reporting."""


class AdbDevice:
    def __init__(self, serial: str | None = None, package: str = DEFAULT_PACKAGE):
        self.serial = serial
        self.package = package
        self._event_node: str | None = None

    # -- plumbing -----------------------------------------------------------

    def _base(self) -> list[str]:
        adb = shutil.which("adb")
        if adb is None:
            raise DeviceError(
                "adb is not on PATH. Add the Android platform-tools directory to PATH."
            )
        return [adb] + (["-s", self.serial] if self.serial else [])

    def run(self, args: Sequence[str], timeout: float = 30.0) -> str:
        proc = subprocess.run(
            self._base() + list(args),
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip() or "no detail"
            raise DeviceError(f"adb {' '.join(args)} failed: {detail}")
        return proc.stdout.decode("utf-8", "replace").replace("\r\n", "\n")

    def run_binary(self, args: Sequence[str], timeout: float = 30.0) -> bytes:
        proc = subprocess.run(self._base() + list(args), capture_output=True, timeout=timeout)
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip() or "no detail"
            raise DeviceError(f"adb {' '.join(args)} failed: {detail}")
        return proc.stdout

    def shell(self, command: str, timeout: float = 30.0) -> str:
        return self.run(["shell", command], timeout=timeout).strip()

    # -- state --------------------------------------------------------------

    def model(self) -> str:
        return self.shell("getprop ro.product.model")

    def app_running(self) -> bool:
        out = self.shell(f"ps -A -o NAME | grep -cx {self.package}")
        return out.strip().isdigit() and int(out.strip()) > 0

    def busy_emulators(self) -> int:
        """How many *other* emulators are actually consuming CPU right now.

        Residency alone is not contention - a cached process can sit around for
        hours - so this samples each candidate's CPU time over a short interval.
        """
        script = (
            f"pids=$(ps -A -o PID,NAME | grep -iE '{RIVAL_PATTERN}' | awk '{{print $1}}'); "
            "n=0; for p in $pids; do "
            "a=$(awk '{print $14+$15}' /proc/$p/stat 2>/dev/null) || continue; "
            "sleep 2; "
            "b=$(awk '{print $14+$15}' /proc/$p/stat 2>/dev/null) || continue; "
            "[ $((b-a)) -gt 8 ] && n=$((n+1)); "
            "done; echo $n"
        )
        out = self.shell(script, timeout=60.0).strip().splitlines()
        return int(out[-1]) if out and out[-1].isdigit() else 0

    def start_app(self, activity: str = ".ui.main.MainActivity") -> str:
        return self.shell(f"am start -n {self.package}/{activity}")

    def stop_app(self) -> str:
        return self.shell(f"am force-stop {self.package}")

    def screenshot(self) -> bytes:
        """A PNG of the current screen.

        `exec-out` rather than `shell` so no newline translation corrupts it.
        """
        data = self.run_binary(["exec-out", "screencap", "-p"], timeout=60.0)
        if not data.startswith(b"\x89PNG"):
            raise DeviceError("screencap did not return a PNG")
        return data

    def list_savestates(self) -> list[str]:
        path = f"/storage/emulated/0/Android/data/{self.package}/files/StateSaves"
        out = self.shell(f"ls -1 {path} 2>/dev/null")
        return [line for line in out.splitlines() if line.strip()]

    # -- input --------------------------------------------------------------

    def gamepad_node(self) -> str:
        """The event node of the built-in gamepad, discovered rather than assumed."""
        if self._event_node:
            return self._event_node
        out = self.shell(
            "getevent -pl 2>/dev/null | grep -B3 -iE 'Odin Controller|Thor Controller' "
            "| grep -o '/dev/input/event[0-9]*' | head -1"
        )
        node = out.strip().splitlines()[-1] if out.strip() else ""
        if not node.startswith("/dev/input/event"):
            raise DeviceError(
                "could not find the gamepad's event node; is the controller attached?"
            )
        self._event_node = node
        return node

    def _events(self, lines: Sequence[str]) -> None:
        node = self.gamepad_node()
        script = "; ".join(f"sendevent {node} {line}" for line in lines)
        self.shell(script, timeout=60.0)

    def press_buttons(self, names: Sequence[str], hold_ms: int = 200) -> str:
        """Press buttons together, the way a hotkey chord needs.

        Presses in the order given and releases in reverse, so
        `["select", "r1"]` holds Select while R1 goes down and up.
        """
        codes = []
        for name in names:
            key = name.strip().lower()
            if key not in BUTTONS:
                valid = ", ".join(sorted(BUTTONS))
                raise DeviceError(f"unknown button {name!r}; expected one of {valid}")
            codes.append(BUTTONS[key])

        lines: list[str] = []
        for code in codes:
            lines += [f"{EV_KEY} {code} 1", f"{EV_SYN} 0 0"]
        self._events(lines)

        # A separate shell round trip is a crude but adequate hold.
        self.shell(f"sleep {max(hold_ms, 0) / 1000.0}")

        lines = []
        for code in reversed(codes):
            lines += [f"{EV_KEY} {code} 0", f"{EV_SYN} 0 0"]
        self._events(lines)
        return f"pressed {' + '.join(names)}"

    def move_right_stick(self, x: float = 0.0, y: float = 0.0, hold_ms: int = 400) -> str:
        """Deflect the right stick, then return it to centre.

        `y` is negative for up, matching the axis the pad reports.
        """
        for value in (x, y):
            if not -1.0 <= value <= 1.0:
                raise DeviceError("stick values must be between -1.0 and 1.0")
        raw_x = int(x * STICK_FULL)
        raw_y = int(y * STICK_FULL)
        self._events(
            [f"{EV_ABS} {ABS_RIGHT_X} {raw_x}", f"{EV_ABS} {ABS_RIGHT_Y} {raw_y}", f"{EV_SYN} 0 0"]
        )
        self.shell(f"sleep {max(hold_ms, 0) / 1000.0}")
        self._events(
            [f"{EV_ABS} {ABS_RIGHT_X} 0", f"{EV_ABS} {ABS_RIGHT_Y} 0", f"{EV_SYN} 0 0"]
        )
        return f"right stick to ({x}, {y}) and back"

    def hotkey(self, name: str) -> str:
        """One of this fork's Android hotkeys, by what it does.

        The defaults are Select + right stick down to save, Select + right stick
        up to load, and Select + R1 for the speed toggle.
        """
        combos = {
            "quick_save": ("select", (0.0, 1.0)),
            "quick_load": ("select", (0.0, -1.0)),
            "speed_toggle": ("select", None),
        }
        if name not in combos:
            raise DeviceError(f"unknown hotkey {name!r}; expected one of {', '.join(combos)}")
        if name == "speed_toggle":
            return self.press_buttons(["select", "r1"])

        _, (sx, sy) = combos[name]
        hold = BUTTONS["select"]
        self._events([f"{EV_KEY} {hold} 1", f"{EV_SYN} 0 0"])
        self.shell("sleep 0.3")
        self.move_right_stick(sx, sy)
        self._events([f"{EV_KEY} {hold} 0", f"{EV_SYN} 0 0"])
        return f"sent {name} (Select + right stick {'down' if sy > 0 else 'up'})"
