#!/usr/bin/env python3
"""Tests for the adb-backed device layer. No device required.

    python Tools/mcp/test_device.py

The interesting part is the input synthesis: a hotkey chord is only a chord if
the modifier goes down first and comes up last, and the right stick has to be
returned to centre or the guest sees it held forever.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from device import BUTTONS, AdbDevice, DeviceError  # noqa: E402


class RecordingDevice(AdbDevice):
    """Captures what would have been sent instead of talking to adb."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.events: list[str] = []
        self.shell_calls: list[str] = []
        self._event_node = "/dev/input/event9"

    def _events(self, lines):
        self.events.extend(lines)

    def shell(self, command, timeout=30.0):
        self.shell_calls.append(command)
        return ""


class ButtonTest(unittest.TestCase):
    def setUp(self):
        self.device = RecordingDevice()

    def test_press_is_down_then_up(self):
        self.device.press_buttons(["a"])
        code = BUTTONS["a"]
        self.assertEqual(
            self.device.events,
            [f"1 {code} 1", "0 0 0", f"1 {code} 0", "0 0 0"],
        )

    def test_chord_holds_the_first_button_across_the_second(self):
        self.device.press_buttons(["select", "r1"])
        select, r1 = BUTTONS["select"], BUTTONS["r1"]
        # Down in order, up in reverse: Select is still held while R1 is pressed
        # and released, which is what the fork's hotkeys require.
        self.assertEqual(
            self.device.events,
            [
                f"1 {select} 1", "0 0 0",
                f"1 {r1} 1", "0 0 0",
                f"1 {r1} 0", "0 0 0",
                f"1 {select} 0", "0 0 0",
            ],
        )

    def test_unknown_button_is_rejected_with_the_valid_list(self):
        with self.assertRaises(DeviceError) as caught:
            self.device.press_buttons(["turbo"])
        self.assertIn("select", str(caught.exception))

    def test_nothing_is_sent_when_a_button_name_is_bad(self):
        with self.assertRaises(DeviceError):
            self.device.press_buttons(["a", "nope"])
        self.assertEqual(self.device.events, [], "a bad name must not half-send a chord")

    def test_button_codes_match_linux_evdev(self):
        # These are the codes the pad actually reports; see AGENTS.md.
        self.assertEqual(BUTTONS["select"], 0x13A)
        self.assertEqual(BUTTONS["start"], 0x13B)
        self.assertEqual(BUTTONS["r1"], 0x137)
        self.assertEqual(BUTTONS["up"], 0x220)


class StickTest(unittest.TestCase):
    def setUp(self):
        self.device = RecordingDevice()

    def test_deflection_returns_to_centre(self):
        self.device.move_right_stick(0.0, 1.0)
        self.assertEqual(self.device.events[0], "3 2 0")
        self.assertEqual(self.device.events[1], "3 5 32767")
        self.assertEqual(self.device.events[-3:], ["3 2 0", "3 5 0", "0 0 0"])

    def test_up_is_negative(self):
        self.device.move_right_stick(0.0, -1.0)
        self.assertIn("3 5 -32767", self.device.events)

    def test_out_of_range_is_rejected(self):
        with self.assertRaises(DeviceError):
            self.device.move_right_stick(0.0, 2.0)


class HotkeyTest(unittest.TestCase):
    def setUp(self):
        self.device = RecordingDevice()

    def test_quick_save_holds_select_across_the_stick(self):
        self.device.hotkey("quick_save")
        select = BUTTONS["select"]
        self.assertEqual(self.device.events[0], f"1 {select} 1")
        self.assertEqual(self.device.events[-2:], [f"1 {select} 0", "0 0 0"])
        self.assertIn("3 5 32767", self.device.events, "quick save is stick down")

    def test_quick_load_is_the_opposite_direction(self):
        self.device.hotkey("quick_load")
        self.assertIn("3 5 -32767", self.device.events)

    def test_speed_toggle_is_select_plus_r1(self):
        self.device.hotkey("speed_toggle")
        self.assertIn(f"1 {BUTTONS['r1']} 1", self.device.events)

    def test_unknown_hotkey_lists_the_real_ones(self):
        with self.assertRaises(DeviceError) as caught:
            self.device.hotkey("rewind")
        self.assertIn("quick_save", str(caught.exception))


class ContentionTest(unittest.TestCase):
    def test_busy_count_parses_the_device_reply(self):
        class Busy(RecordingDevice):
            def shell(self, command, timeout=30.0):
                return "2"

        self.assertEqual(Busy().busy_emulators(), 2)

    def test_non_numeric_reply_is_treated_as_idle(self):
        class Noisy(RecordingDevice):
            def shell(self, command, timeout=30.0):
                return "error: device offline"

        self.assertEqual(Noisy().busy_emulators(), 0)


class ScreenshotTest(unittest.TestCase):
    def test_non_png_output_is_rejected(self):
        class Broken(RecordingDevice):
            def run_binary(self, args, timeout=30.0):
                return b"error: closed"

        with self.assertRaises(DeviceError):
            Broken().screenshot()

    def test_png_passes_through(self):
        payload = b"\x89PNG\r\n\x1a\n" + b"rest"

        class Good(RecordingDevice):
            def run_binary(self, args, timeout=30.0):
                return payload

        self.assertEqual(Good().screenshot(), payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
