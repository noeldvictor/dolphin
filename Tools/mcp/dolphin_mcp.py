#!/usr/bin/env python3
"""An MCP server exposing Dolphin's guest memory and CPU state to an AI client.

It speaks MCP over stdio on one side and Dolphin's GDB stub on the other, so
the emulator needs no modification - which is the point. This fork tracks
upstream, and anything added under `Source/` is merge tax forever.

Run it with no arguments; it connects lazily, on the first tool call that needs
the emulator. See README.md for the Dolphin-side setup and the `claude mcp add`
line.

The protocol implementation here is deliberately dependency-free: MCP stdio is
newline-delimited JSON-RPC 2.0, which is little enough code to own outright
rather than pull a package in for.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any, Callable

from gdb_client import (
    NAMED_REGISTERS,
    REGIONS,
    GdbClient,
    GdbError,
    encode_value,
    find_all,
    iter_region_chunks,
)

SERVER_NAME = "dolphin"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

# How much guest memory to pull per scanning window. Larger windows mean fewer
# round trips; the client splits them into stub-sized reads internally.
SCAN_WINDOW = 64 * 1024

# A scan that matches this much is almost certainly the wrong query (scanning
# for a byte value of 0, say), and returning it all would bury the caller.
MAX_HITS = 500


class ToolError(Exception):
    """A tool failed in a way the model should see and can act on."""


class DolphinMcpServer:
    def __init__(self, host: str, port: int):
        self._client = GdbClient(host=host, port=port)
        self._tools: dict[str, tuple[dict[str, Any], Callable[..., str]]] = {}
        self._register_tools()

    # -- emulator access ----------------------------------------------------

    def _gdb(self) -> GdbClient:
        if not self._client.connected:
            try:
                self._client.connect()
            except OSError as exc:
                raise ToolError(
                    f"cannot reach Dolphin's GDB stub at {self._client.host}:{self._client.port} "
                    f"({exc}). Check that the game was booted with GDBPort set, and on Android "
                    f"that `adb forward tcp:{self._client.port} tcp:{self._client.port}` is active."
                ) from exc
        return self._client

    # -- tools --------------------------------------------------------------

    def _register_tools(self) -> None:
        def tool(name: str, description: str, schema: dict[str, Any]):
            def decorate(fn: Callable[..., str]) -> Callable[..., str]:
                self._tools[name] = (
                    {"name": name, "description": description, "inputSchema": schema},
                    fn,
                )
                return fn

            return decorate

        obj = lambda props, required: {  # noqa: E731 - terse schema helper
            "type": "object",
            "properties": props,
            "required": required,
        }
        addr = {"type": "integer", "description": "Guest address, e.g. 2147483648 for 0x80000000"}
        value_type = {
            "type": "string",
            "enum": ["u8", "s8", "u16", "s16", "u32", "s32", "u64", "s64", "f32", "f64"],
            "description": "How to interpret the value. The guest is big endian.",
        }

        @tool(
            "status",
            "Report whether Dolphin's GDB stub is reachable and what the CPU is doing.",
            obj({}, []),
        )
        def status() -> str:
            gdb = self._gdb()
            reason = gdb.halt_reason()
            pc = gdb.read_register(NAMED_REGISTERS["pc"])
            return (
                f"Connected to {gdb.host}:{gdb.port}.\n"
                f"Stop reply: {reason}\n"
                f"PC: {pc:#010x}"
            )

        @tool(
            "read_memory",
            "Read raw bytes of guest memory and show them as hex.",
            obj(
                {
                    "address": addr,
                    "length": {"type": "integer", "description": "Bytes to read (max 4096)."},
                },
                ["address", "length"],
            ),
        )
        def read_memory(address: int, length: int) -> str:
            if not 0 < length <= 4096:
                raise ToolError("length must be between 1 and 4096")
            data = self._gdb().read_memory(address, length)
            return f"{address:#010x} ({len(data)} bytes)\n{data.hex()}"

        @tool(
            "read_value",
            "Read a single typed value from guest memory.",
            obj({"address": addr, "type": value_type}, ["address", "type"]),
        )
        def read_value(address: int, type: str) -> str:
            import struct

            sizes = {"u8": 1, "s8": 1, "u16": 2, "s16": 2, "u32": 4, "s32": 4,
                     "u64": 8, "s64": 8, "f32": 4, "f64": 8}
            fmts = {"u8": ">B", "s8": ">b", "u16": ">H", "s16": ">h", "u32": ">I",
                    "s32": ">i", "u64": ">Q", "s64": ">q", "f32": ">f", "f64": ">d"}
            if type not in sizes:
                raise ToolError(f"unknown type {type!r}")
            data = self._gdb().read_memory(address, sizes[type])
            (value,) = struct.unpack(fmts[type], data)
            return f"{address:#010x} {type} = {value} (raw {data.hex()})"

        @tool(
            "write_value",
            "Write a single typed value to guest memory. This changes the running game.",
            obj(
                {"address": addr, "type": value_type, "value": {"type": "number"}},
                ["address", "type", "value"],
            ),
        )
        def write_value(address: int, type: str, value: float) -> str:
            payload = encode_value(value, type)
            self._gdb().write_memory(address, payload)
            return f"wrote {type} {value} ({payload.hex()}) to {address:#010x}"

        @tool(
            "search_memory",
            "Scan guest memory for a value and return the addresses holding it. "
            "This is the first step of finding a cheat: search for a value you can "
            "see in game, change it in game, then narrow with filter_candidates.",
            obj(
                {
                    "value": {"type": "number", "description": "The value to look for."},
                    "type": value_type,
                    "region": {
                        "type": "string",
                        "enum": ["mem1", "mem2"],
                        "description": "mem1 is main RAM on both consoles; mem2 is Wii only. "
                        "Defaults to mem1.",
                    },
                    "aligned": {
                        "type": "boolean",
                        "description": "Only report naturally aligned addresses. Default true, "
                        "which is right for almost all game data and much less noisy.",
                    },
                },
                ["value", "type"],
            ),
        )
        def search_memory(
            value: float, type: str, region: str = "mem1", aligned: bool = True
        ) -> str:
            needle = encode_value(value, type)
            hits = self._scan(needle, region, len(needle) if aligned else 1)
            if not hits:
                return f"no matches for {type} {value} in {region}"
            shown = hits[:MAX_HITS]
            listing = "\n".join(f"  {a:#010x}" for a in shown)
            note = "" if len(hits) <= MAX_HITS else f"\n(showing {MAX_HITS} of {len(hits)})"
            return f"{len(hits)} match(es) for {type} {value} in {region}:\n{listing}{note}"

        @tool(
            "filter_candidates",
            "Given addresses from an earlier search, keep only those that now hold "
            "the given value. Repeat this after changing the value in game and you "
            "converge on the real address in a few passes.",
            obj(
                {
                    "addresses": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Addresses from a previous search_memory call.",
                    },
                    "value": {"type": "number"},
                    "type": value_type,
                },
                ["addresses", "value", "type"],
            ),
        )
        def filter_candidates(addresses: list[int], value: float, type: str) -> str:
            needle = encode_value(value, type)
            gdb = self._gdb()
            survivors = []
            for address in addresses:
                try:
                    if gdb.read_memory(address, len(needle)) == needle:
                        survivors.append(address)
                except GdbError:
                    continue  # address stopped being readable; it is not our value
            if not survivors:
                return f"none of the {len(addresses)} candidates now hold {type} {value}"
            listing = "\n".join(f"  {a:#010x}" for a in survivors[:MAX_HITS])
            return (
                f"{len(survivors)} of {len(addresses)} candidates still hold "
                f"{type} {value}:\n{listing}"
            )

        @tool(
            "read_registers",
            "Read the 32 general purpose registers plus PC, LR and CTR.",
            obj({}, []),
        )
        def read_registers() -> str:
            gdb = self._gdb()
            gprs = gdb.read_gprs()
            lines = [
                "  ".join(f"r{i + j:<2}={gprs[i + j]:08x}" for j in range(4) if i + j < 32)
                for i in range(0, 32, 4)
            ]
            named = "  ".join(
                f"{name}={gdb.read_register(rid):08x}"
                for name, rid in (("pc", 64), ("lr", 67), ("ctr", 68))
            )
            return "\n".join(lines) + "\n" + named

        @tool(
            "set_watchpoint",
            "Break when the guest touches an address. Use this to find the code that "
            "writes a value you have located.",
            obj(
                {
                    "address": addr,
                    "kind": {
                        "type": "string",
                        "enum": ["write", "read", "access", "software", "hardware"],
                    },
                    "length": {"type": "integer", "description": "Bytes to watch. Default 4."},
                },
                ["address", "kind"],
            ),
        )
        def set_watchpoint(address: int, kind: str, length: int = 4) -> str:
            self._gdb().add_breakpoint(kind, address, length)
            return f"{kind} breakpoint set at {address:#010x} for {length} byte(s)"

        @tool(
            "clear_watchpoint",
            "Remove a breakpoint or watchpoint previously set at an address.",
            obj(
                {
                    "address": addr,
                    "kind": {
                        "type": "string",
                        "enum": ["write", "read", "access", "software", "hardware"],
                    },
                    "length": {"type": "integer"},
                },
                ["address", "kind"],
            ),
        )
        def clear_watchpoint(address: int, kind: str, length: int = 4) -> str:
            self._gdb().remove_breakpoint(kind, address, length)
            return f"{kind} breakpoint cleared at {address:#010x}"

        @tool(
            "resume",
            "Let the game run. The stub starts the game paused, so call this after connecting.",
            obj({}, []),
        )
        def resume() -> str:
            return self._gdb().resume()

        @tool("pause", "Break into the debugger, pausing the game.", obj({}, []))
        def pause() -> str:
            gdb = self._gdb()
            gdb.interrupt()
            return f"paused; {gdb.halt_reason()}"

        @tool("step", "Execute a single guest instruction.", obj({}, []))
        def step() -> str:
            gdb = self._gdb()
            reply = gdb.step()
            return f"stepped; stop reply {reply}, PC now {gdb.read_register(64):#010x}"

    def _scan(self, needle: bytes, region: str, alignment: int) -> list[int]:
        if region not in REGIONS:
            raise ToolError(f"unknown region {region!r}; expected mem1 or mem2")
        start, size = REGIONS[region]
        gdb = self._gdb()

        # Fail fast on a region that is not mapped at all, rather than grinding
        # through thousands of rejected reads and reporting a bland "no matches".
        # The usual cause is scanning mem2 while a GameCube game is running.
        try:
            gdb.read_memory(start, 4)
        except GdbError as exc:
            hint = (
                " mem2 only exists on Wii; a GameCube game has mem1 only."
                if region == "mem2"
                else ""
            )
            raise ToolError(
                f"{region} is not readable at {start:#010x} ({exc}).{hint} "
                f"Is a game actually running?"
            ) from exc

        overlap = max(len(needle) - 1, 0)
        hits: list[int] = []
        seen: set[int] = set()
        for address, length in iter_region_chunks(start, size, SCAN_WINDOW, overlap):
            try:
                block = gdb.read_memory(address, length)
            except GdbError:
                # Unmapped holes inside an otherwise valid region are normal;
                # skip them rather than aborting a scan that is otherwise fine.
                continue
            for hit in find_all(block, needle, address, alignment):
                if hit not in seen:
                    seen.add(hit)
                    hits.append(hit)
        return sorted(hits)

    # -- MCP plumbing -------------------------------------------------------

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        if method == "initialize":
            requested = params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
            return self._result(
                msg_id,
                {
                    "protocolVersion": requested,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            )
        if method in ("notifications/initialized", "initialized"):
            return None
        if method == "ping":
            return self._result(msg_id, {})
        if method == "tools/list":
            return self._result(msg_id, {"tools": [spec for spec, _ in self._tools.values()]})
        if method == "tools/call":
            return self._call_tool(msg_id, params)
        if msg_id is None:
            return None
        return self._error(msg_id, -32601, f"unknown method {method!r}")

    def _call_tool(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        entry = self._tools.get(name)
        if entry is None:
            return self._error(msg_id, -32602, f"unknown tool {name!r}")
        _, fn = entry
        try:
            text = fn(**arguments)
            return self._result(msg_id, {"content": [{"type": "text", "text": text}]})
        except (ToolError, GdbError, ValueError) as exc:
            return self._result(
                msg_id,
                {"content": [{"type": "text", "text": f"{exc}"}], "isError": True},
            )
        except TypeError as exc:
            return self._result(
                msg_id,
                {"content": [{"type": "text", "text": f"bad arguments for {name}: {exc}"}],
                 "isError": True},
            )
        except Exception:  # pragma: no cover - unexpected, but must not kill the server
            return self._result(
                msg_id,
                {"content": [{"type": "text", "text": traceback.format_exc()}], "isError": True},
            )

    @staticmethod
    def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}

    def serve(self, stdin=None, stdout=None) -> None:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # not addressed to us in any form we can answer
            response = self.handle(message)
            if response is not None:
                stdout.write(json.dumps(response) + "\n")
                stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2159)
    args = parser.parse_args()
    DolphinMcpServer(args.host, args.port).serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
