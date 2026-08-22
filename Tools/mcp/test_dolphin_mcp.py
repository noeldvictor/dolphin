#!/usr/bin/env python3
"""Tests for the Dolphin MCP server. These run without a device or an emulator.

    python Tools/mcp/test_dolphin_mcp.py

A fake stub stands in for Dolphin, which lets the protocol handling, the memory
chunking and the scan logic be checked on any machine. The one thing it cannot
check is that the real stub agrees with our reading of GDBStub.cpp.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dolphin_mcp import DolphinMcpServer  # noqa: E402
from gdb_client import (  # noqa: E402
    GdbClient,
    GdbError,
    encode_value,
    find_all,
    iter_region_chunks,
    _checksum,
)


class FakeStub:
    """The emulator side of the wire: serves `m`/`M`/`g`/`p` from a memory map."""

    def __init__(self, base: int, data: bytes):
        self.base = base
        self.data = bytearray(data)
        self.gprs = [0x1000 + i for i in range(32)]
        self.pc = 0x80003100
        self.sent = bytearray()
        self.reads: list[tuple[int, int]] = []
        self.running = False

    # socket-ish interface used by GdbClient
    def sendall(self, payload: bytes) -> None:
        # A bare 0x03 is a break request, not a packet: the stub answers it with
        # a stop reply (SendSignal in GDBStub.cpp).
        if payload == b"\x03":
            self._queue(self._frame("T05" + "40" + ":" + f"{self.pc:08x}" + ";"))
            return
        self.sent.extend(payload)
        while b"#" in self.sent:
            start = self.sent.find(b"$")
            if start < 0:
                self.sent.clear()
                return
            end = self.sent.find(b"#", start)
            if end < 0 or len(self.sent) < end + 3:
                return
            body = self.sent[start + 1 : end].decode("ascii")
            del self.sent[: end + 3]
            self._queue(b"+")
            reply = self._respond(body)
            if reply is not None:
                self._queue(self._frame(reply))

    def recv(self, _size: int) -> bytes:
        out = bytes(self._outbox)
        self._outbox = bytearray()
        return out

    def settimeout(self, _t):  # pragma: no cover - interface shim
        pass

    def close(self):  # pragma: no cover - interface shim
        pass

    _outbox = bytearray()

    def _queue(self, payload: bytes) -> None:
        self._outbox = bytearray(self._outbox) + payload

    @staticmethod
    def _frame(body: str) -> bytes:
        return f"${body}#{_checksum(body)}".encode("ascii")

    def _respond(self, body: str) -> str:
        if body.startswith("m"):
            addr_s, len_s = body[1:].split(",")
            addr, length = int(addr_s, 16), int(len_s, 16)
            self.reads.append((addr, length))
            offset = addr - self.base
            if offset < 0 or offset + length > len(self.data):
                return "E00"
            return self.data[offset : offset + length].hex()
        if body.startswith("M"):
            head, payload = body[1:].split(":")
            addr_s, len_s = head.split(",")
            addr = int(addr_s, 16)
            offset = addr - self.base
            chunk = bytes.fromhex(payload)
            self.data[offset : offset + len(chunk)] = chunk
            return "OK"
        if body == "g":
            return "".join(f"{v:08x}" for v in self.gprs)
        if body.startswith("p"):
            reg = int(body[1:], 16)
            return f"{self.pc:08x}" if reg == 64 else f"{self.gprs[reg % 32]:08x}"
        if body == "?":
            return "S05"
        if body.startswith(("Z", "z")):
            return "OK"
        if body == "s":
            return "S05"
        if body == "c":
            self.running = True
            return None  # the real stub says nothing until it stops
        return ""


def client_for(stub: FakeStub) -> GdbClient:
    client = GdbClient()
    client._sock = stub  # type: ignore[assignment]
    return client


class ChecksumTest(unittest.TestCase):
    def test_matches_the_rsp_definition(self):
        # Sum of the payload bytes, modulo 256, as two lowercase hex digits.
        self.assertEqual(_checksum("m80000000,4"), f"{sum(b'm80000000,4') & 0xFF:02x}")

    def test_empty_payload(self):
        self.assertEqual(_checksum(""), "00")


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.stub = FakeStub(0x80000000, bytes(range(256)) * 64)  # 16 KiB
        self.client = client_for(self.stub)

    def test_reads_exact_bytes(self):
        self.assertEqual(self.client.read_memory(0x80000010, 4), bytes([16, 17, 18, 19]))

    def test_splits_large_reads_into_stub_sized_chunks(self):
        data = self.client.read_memory(0x80000000, 10000)
        self.assertEqual(len(data), 10000)
        # The stub refuses anything over 4998 bytes, so every request must be under it.
        self.assertTrue(self.stub.reads, "expected at least one read")
        self.assertTrue(all(length <= 4096 for _, length in self.stub.reads))

    def test_reassembles_chunks_in_order(self):
        self.assertEqual(
            self.client.read_memory(0x80000000, 8192),
            (bytes(range(256)) * 64)[:8192],
        )

    def test_write_round_trips(self):
        self.client.write_memory(0x80000020, b"\xde\xad\xbe\xef")
        self.assertEqual(self.client.read_memory(0x80000020, 4), b"\xde\xad\xbe\xef")

    def test_error_reply_raises(self):
        with self.assertRaises(GdbError):
            self.client.read_memory(0x90000000, 4)  # outside the fake's map


class RegisterTest(unittest.TestCase):
    def test_reads_all_32_gprs(self):
        stub = FakeStub(0x80000000, b"\x00" * 16)
        gprs = client_for(stub).read_gprs()
        self.assertEqual(len(gprs), 32)
        self.assertEqual(gprs[0], 0x1000)
        self.assertEqual(gprs[31], 0x101F)

    def test_reads_pc_by_id(self):
        stub = FakeStub(0x80000000, b"\x00" * 16)
        self.assertEqual(client_for(stub).read_register(64), 0x80003100)


class EncodingTest(unittest.TestCase):
    def test_guest_is_big_endian(self):
        # The detail that catches people used to little endian scanners.
        self.assertEqual(encode_value(1, "u32"), b"\x00\x00\x00\x01")
        self.assertEqual(encode_value(0x1234, "u16"), b"\x12\x34")

    def test_float_encoding(self):
        self.assertEqual(encode_value(1.0, "f32"), b"\x3f\x80\x00\x00")

    def test_rejects_unknown_type(self):
        with self.assertRaises(ValueError):
            encode_value(1, "u128")


class ScanHelperTest(unittest.TestCase):
    def test_finds_every_occurrence(self):
        blob = b"\x00\x01\x00\x01\x00\x01"
        self.assertEqual(find_all(blob, b"\x00\x01", 0x80000000, 1),
                         [0x80000000, 0x80000002, 0x80000004])

    def test_alignment_filters_hits(self):
        blob = b"\xff\x00\x00\x00\x01"
        # The u32 1 sits at offset 1, which is not 4-byte aligned.
        self.assertEqual(find_all(blob, b"\x00\x00\x00\x01", 0x80000000, 4), [])
        self.assertEqual(find_all(blob, b"\x00\x00\x00\x01", 0x80000000, 1), [0x80000001])

    def test_chunks_cover_the_whole_region(self):
        covered = bytearray(1000)
        for address, length in iter_region_chunks(0, 1000, 256, 3):
            for i in range(address, address + length):
                covered[i] = 1
        self.assertTrue(all(covered), "every byte of the region must be scanned")

    def test_chunks_overlap_so_straddling_matches_are_not_missed(self):
        windows = list(iter_region_chunks(0, 1000, 256, 3))
        for (a_start, a_len), (b_start, _) in zip(windows, windows[1:]):
            self.assertEqual(b_start, a_start + a_len - 3)

    def test_chunk_must_exceed_overlap(self):
        with self.assertRaises(ValueError):
            list(iter_region_chunks(0, 100, 4, 4))


class McpProtocolTest(unittest.TestCase):
    def setUp(self):
        self.server = DolphinMcpServer("127.0.0.1", 2159)
        self.stub = FakeStub(0x80000000, b"\x00\x00\x00\x2a" + b"\x00" * 4092)
        self.server._client = client_for(self.stub)

    def call(self, method, params=None, msg_id=1):
        return self.server.handle(
            {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
        )

    def test_initialize_echoes_protocol_version(self):
        reply = self.call("initialize", {"protocolVersion": "2024-11-05"})
        self.assertEqual(reply["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(reply["result"]["serverInfo"]["name"], "dolphin")

    def test_initialized_notification_gets_no_reply(self):
        self.assertIsNone(self.call("notifications/initialized", msg_id=None))

    def test_tools_list_is_well_formed(self):
        tools = self.call("tools/list")["result"]["tools"]
        self.assertTrue(tools)
        for tool in tools:
            self.assertIn("name", tool)
            self.assertTrue(tool["description"], f"{tool['name']} needs a description")
            self.assertEqual(tool["inputSchema"]["type"], "object")
        names = {t["name"] for t in tools}
        self.assertIn("search_memory", names)
        self.assertIn("filter_candidates", names)

    def test_read_value_decodes_big_endian(self):
        reply = self.call(
            "tools/call",
            {"name": "read_value", "arguments": {"address": 0x80000000, "type": "u32"}},
        )
        self.assertNotIn("isError", reply["result"])
        self.assertIn("= 42", reply["result"]["content"][0]["text"])

    def test_unknown_tool_is_reported_as_a_tool_error(self):
        reply = self.call("tools/call", {"name": "nope", "arguments": {}})
        self.assertEqual(reply["error"]["code"], -32602)

    def test_bad_arguments_do_not_kill_the_server(self):
        reply = self.call("tools/call", {"name": "read_value", "arguments": {"address": 1}})
        self.assertTrue(reply["result"]["isError"])

    def test_read_memory_rejects_absurd_lengths(self):
        reply = self.call(
            "tools/call",
            {"name": "read_memory", "arguments": {"address": 0x80000000, "length": 999999}},
        )
        self.assertTrue(reply["result"]["isError"])

    def test_unknown_method_errors(self):
        self.assertEqual(self.call("tools/nope")["error"]["code"], -32601)

    def test_scanning_an_unmapped_region_says_so_clearly(self):
        # The fake stub only maps mem1, so a mem2 scan is the GameCube case.
        reply = self.call(
            "tools/call",
            {"name": "search_memory",
             "arguments": {"value": 42, "type": "u32", "region": "mem2"}},
        )
        text = reply["result"]["content"][0]["text"]
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("mem2 only exists on Wii", text)

    def test_search_finds_a_known_value(self):
        # Scope mem1 to what the fake stub actually maps; the real region is 24 MiB
        # and scanning it here would only be measuring the fake.
        import dolphin_mcp

        small = {"mem1": (0x80000000, 4096), "mem2": (0x90000000, 4096)}
        with unittest.mock.patch.dict(dolphin_mcp.REGIONS, small, clear=True):
            reply = self.call(
                "tools/call",
                {"name": "search_memory", "arguments": {"value": 42, "type": "u32"}},
            )
        self.assertNotIn("isError", reply["result"])
        self.assertIn("0x80000000", reply["result"]["content"][0]["text"])

    def test_search_respects_alignment_by_default(self):
        import dolphin_mcp

        # 42 as a u32 also appears unaligned at 0x80000001 in the seeded data.
        self.stub.data[0:8] = b"\x00\x00\x00\x00\x00\x2a\x00\x00"
        small = {"mem1": (0x80000000, 4096), "mem2": (0x90000000, 4096)}
        with unittest.mock.patch.dict(dolphin_mcp.REGIONS, small, clear=True):
            aligned = self.call(
                "tools/call",
                {"name": "search_memory", "arguments": {"value": 42, "type": "u32"}},
            )["result"]["content"][0]["text"]
            unaligned = self.call(
                "tools/call",
                {"name": "search_memory",
                 "arguments": {"value": 42, "type": "u32", "aligned": False}},
            )["result"]["content"][0]["text"]
        self.assertIn("no matches", aligned)
        self.assertIn("0x80000002", unaligned)

    def test_serve_handles_a_full_line_oriented_session(self):
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ]
        out = io.StringIO()
        self.server.serve(io.StringIO("\n".join(lines) + "\n"), out)
        replies = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2])

    def test_malformed_json_is_skipped_not_fatal(self):
        out = io.StringIO()
        session = "not json\n" + json.dumps(
            {"jsonrpc": "2.0", "id": 7, "method": "ping"}
        ) + "\n"
        self.server.serve(io.StringIO(session), out)
        self.assertEqual(json.loads(out.getvalue())["id"], 7)


class ExecutionStateTest(unittest.TestCase):
    """resume/pause must not desynchronise the connection.

    The stub acks the `c` packet and then says nothing until the guest stops.
    If that ack is left unread, the next command takes it as its own and then
    reads the following stop reply as its result - and every reply after that
    is off by one, silently returning the previous command's answer.
    """

    def setUp(self):
        self.stub = FakeStub(0x80000000, bytes(range(256)))
        self.client = client_for(self.stub)

    def test_resume_consumes_its_ack(self):
        self.client.resume()
        # The ack must have been taken off the wire, not left sitting in the
        # stub's outbox for the next command to mistake for its own.
        self.assertEqual(
            bytes(self.stub._outbox), b"", "resume left its ack unread on the wire"
        )

    def test_command_while_running_is_refused_not_hung(self):
        self.client.resume()
        with self.assertRaises(GdbError) as caught:
            self.client.read_memory(0x80000000, 4)
        self.assertIn('pause', str(caught.exception))

    def test_pause_reads_the_stop_reply_and_resyncs(self):
        self.client.resume()
        reply = self.client.interrupt()
        self.assertTrue(reply.startswith('T05'), reply)
        # The connection must be usable again, and give the right answer.
        self.assertEqual(self.client.read_memory(0x80000010, 4), bytes([16, 17, 18, 19]))

    def test_interrupt_when_already_stopped_is_a_no_op(self):
        self.assertEqual(self.client.interrupt(), 'already stopped')
        self.assertEqual(self.client.read_memory(0x80000000, 2), bytes([0, 1]))


class ConnectionErrorTest(unittest.TestCase):
    def test_unreachable_stub_gives_actionable_advice(self):
        server = DolphinMcpServer("127.0.0.1", 1)  # nothing listens on port 1
        reply = server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": "status", "arguments": {}}}
        )
        text = reply["result"]["content"][0]["text"]
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("adb forward", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
