#!/usr/bin/env python3
"""Check the MCP client's assumptions against Dolphin's actual GDB stub source.

    python Tools/mcp/test_stub_contract.py

`gdb_client.py` hardcodes facts read out of `Source/Core/Core/PowerPC/GDBStub.cpp`:
the packet buffer size that caps a memory read, the register ids behind `p`, and
which commands exist at all. Those are upstream's to change, and this fork merges
upstream regularly - a sync already deleted `DirectoryInitialization.getSysDirectory`
out from under code that needed it.

So rather than trusting a one-time reading, these tests parse the stub and fail
loudly if it stops matching. A failure here is not a bug in the MCP server; it
means upstream changed the stub and the client needs updating to match.
"""

from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gdb_client import (  # noqa: E402
    MAX_READ_CHUNK,
    NAMED_REGISTERS,
    GdbClient,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
STUB_PATH = os.path.join(REPO_ROOT, "Source", "Core", "Core", "PowerPC", "GDBStub.cpp")


def stub_source() -> str:
    with open(STUB_PATH, encoding="utf-8", errors="replace") as handle:
        return handle.read()


class StubPresenceTest(unittest.TestCase):
    def test_the_stub_still_exists(self):
        self.assertTrue(
            os.path.isfile(STUB_PATH),
            f"{STUB_PATH} is gone. Upstream removed or moved the GDB stub, and the MCP "
            f"server has no transport without it.",
        )


class PacketSizeTest(unittest.TestCase):
    def test_read_chunk_fits_the_stub_reply_buffer(self):
        source = stub_source()
        match = re.search(r"#define\s+GDB_BFR_MAX\s+(\d+)", source)
        self.assertIsNotNone(match, "GDB_BFR_MAX is gone from GDBStub.cpp")
        bfr_max = int(match.group(1))

        # ReadMemory replies into a `GDB_BFR_MAX - 4` buffer, two hex chars per byte.
        max_bytes_per_read = (bfr_max - 4) // 2
        self.assertLessEqual(
            MAX_READ_CHUNK,
            max_bytes_per_read,
            f"MAX_READ_CHUNK ({MAX_READ_CHUNK}) exceeds what the stub can reply with "
            f"({max_bytes_per_read} bytes with GDB_BFR_MAX={bfr_max}). Lower it.",
        )

    def test_reply_buffer_is_still_sized_off_gdb_bfr_max(self):
        # If this changes shape, the arithmetic above is no longer the right model.
        self.assertIn("static u8 reply[GDB_BFR_MAX - 4];", stub_source())


class RegisterIdTest(unittest.TestCase):
    """The `p` command's register ids, which `gdb_client` hardcodes."""

    EXPECTED = {
        64: "ppc_state.pc",
        65: "ppc_state.msr.Hex",
        66: "ppc_state.cr.Get()",
        67: "LR(ppc_state)",
        68: "CTR(ppc_state)",
        69: "ppc_state.spr[SPR_XER]",
        70: "ppc_state.fpscr.Hex",
    }

    def setUp(self):
        self.source = stub_source()

    def test_named_register_ids_still_map_where_we_think(self):
        for reg_id, expression in self.EXPECTED.items():
            with self.subTest(register=reg_id):
                pattern = re.compile(
                    rf"case\s+{reg_id}:\s*\n\s*wbe(?:32|64)hex\(reply,\s*"
                    + re.escape(expression),
                )
                self.assertRegex(
                    self.source,
                    pattern,
                    f"register id {reg_id} no longer reads {expression}",
                )

    def test_client_constants_agree_with_the_stub(self):
        self.assertEqual(NAMED_REGISTERS["pc"], 64)
        self.assertEqual(NAMED_REGISTERS["lr"], 67)
        self.assertEqual(NAMED_REGISTERS["ctr"], 68)

    def test_gprs_are_still_the_first_32_ids(self):
        self.assertRegex(self.source, r"if\s*\(id\s*<\s*32\)")


class ReadRegistersTest(unittest.TestCase):
    def test_g_still_returns_only_the_32_gprs(self):
        source = stub_source()
        body = source[source.index("static void ReadRegisters()") :]
        body = body[: body.index("\nstatic void ")]
        self.assertIn("for (i = 0; i < 32; i++)", body)
        self.assertIn("ppc_state.gpr[i]", body)
        # If upstream starts appending FPRs or PC to the `g` reply, read_gprs()
        # would still work but the client should learn to use the extra data.
        self.assertNotIn("ppc_state.pc", body, "the `g` reply now carries more than the GPRs")


class CommandCoverageTest(unittest.TestCase):
    """Every RSP command the MCP server issues must still be handled."""

    def setUp(self):
        source = stub_source()
        # The dispatch switch near the end of ProcessCommands().
        self.cases = set(re.findall(r"case '(.)':", source))

    def test_commands_the_client_sends_are_handled(self):
        for command, purpose in [
            ("m", "read_memory"),
            ("M", "write_memory"),
            ("g", "read_gprs"),
            ("p", "read_register"),
            ("c", "resume"),
            ("s", "step"),
            ("Z", "add_breakpoint"),
            ("z", "remove_breakpoint"),
            ("?", "halt_reason"),
        ]:
            with self.subTest(command=command):
                self.assertIn(
                    command,
                    self.cases,
                    f"the stub no longer handles '{command}', which {purpose}() depends on",
                )

    def test_breakpoint_kinds_are_still_numeric_zZ_types(self):
        source = stub_source()
        self.assertIn("HandleAddBreakpoint", source)
        self.assertIn("HandleRemoveBreakpoint", source)
        for name, code in GdbClient.BREAKPOINT_KINDS.items():
            with self.subTest(kind=name):
                self.assertIsInstance(code, int)
                self.assertTrue(0 <= code <= 4)


class InterruptTest(unittest.TestCase):
    def test_raw_0x03_still_breaks_into_the_stub(self):
        # GdbClient.interrupt() sends a bare 0x03 rather than a packet.
        source = stub_source()
        self.assertRegex(
            source,
            r"c\s*==\s*0x03",
            "the stub no longer treats a raw 0x03 as a break; interrupt() will not work",
        )


class BootBehaviourTest(unittest.TestCase):
    """The two surprises documented in the README, asserted rather than assumed."""

    def setUp(self):
        core_path = os.path.join(REPO_ROOT, "Source", "Core", "Core", "Core.cpp")
        with open(core_path, encoding="utf-8", errors="replace") as handle:
            self.core = handle.read()

    def test_enabling_the_stub_still_forces_a_paused_boot(self):
        # README tells users the game starts paused and needs `resume`.
        self.assertRegex(
            self.core,
            r"GDBStub::Init\(gdb_port\);\s*\n\s*CPUSetInitialExecutionState\(system,\s*true\);",
            "the stub no longer forces a paused boot; the README's `resume` advice is stale",
        )

    def test_gdb_port_setting_is_still_the_switch(self):
        self.assertIn("Config::MAIN_GDB_PORT", self.core)


if __name__ == "__main__":
    unittest.main(verbosity=2)
