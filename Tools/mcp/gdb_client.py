#!/usr/bin/env python3
"""Minimal GDB Remote Serial Protocol client for Dolphin's built-in stub.

Dolphin ships a GDB stub (`Source/Core/Core/PowerPC/GDBStub.cpp`, enabled with
the `GDBPort` setting). It speaks enough of the protocol to read and write
emulated memory and registers, set breakpoints and watchpoints, and step or
resume the guest CPU - which is everything memory-inspection tooling needs.

Talking to it directly avoids adding any remote-control surface to the emulator
itself, which matters for a fork that has to keep merging upstream.

Stub-specific details this client depends on, all read out of GDBStub.cpp:

- `GDB_BFR_MAX` is 10000, and `ReadMemory` replies into a `GDB_BFR_MAX - 4`
  buffer as two hex characters per byte, so a single `m` may ask for at most
  4998 bytes. We use a smaller chunk for headroom.
- `g` returns *only* the 32 general purpose registers, 8 hex characters each.
  Everything else has to go through `p` with the register ids below.
- `qSupported` reports `swbreak+;hwbreak+` and no `PacketSize`, so we do not
  try to negotiate a larger packet.
"""

from __future__ import annotations

import socket
from typing import Iterable

# Register ids accepted by the stub's `p` command. See ReadRegister() in
# GDBStub.cpp: 0-31 are GPRs, 32-63 are paired-single FPRs, and the named
# registers below follow.
REG_PC = 64
REG_MSR = 65
REG_CR = 66
REG_LR = 67
REG_CTR = 68
REG_XER = 69
REG_FPSCR = 70

NAMED_REGISTERS = {
    "pc": REG_PC,
    "msr": REG_MSR,
    "cr": REG_CR,
    "lr": REG_LR,
    "ctr": REG_CTR,
    "xer": REG_XER,
    "fpscr": REG_FPSCR,
}

# Well under the stub's 4998 byte ceiling for a single `m`.
MAX_READ_CHUNK = 4096

# Guest memory regions. MEM1 exists on both GameCube and Wii; MEM2 is Wii only.
MEM1_START = 0x80000000
MEM1_SIZE = 0x01800000  # 24 MiB
MEM2_START = 0x90000000
MEM2_SIZE = 0x04000000  # 64 MiB

REGIONS = {
    "mem1": (MEM1_START, MEM1_SIZE),
    "mem2": (MEM2_START, MEM2_SIZE),
}


class GdbError(RuntimeError):
    """The stub replied with an error, or the connection misbehaved."""


def _checksum(payload: str) -> str:
    return f"{sum(payload.encode('ascii')) & 0xFF:02x}"


class GdbClient:
    """A blocking RSP client. Not thread safe; one request at a time."""

    def __init__(self, host: str = "127.0.0.1", port: int = 2159, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buf = bytearray()
        # True between a resume and the next stop: the stub owes us nothing until
        # then, so issuing a command would block forever.
        self._running = False

    # -- connection ---------------------------------------------------------

    def connect(self) -> None:
        if self._sock is not None:
            return
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        self._sock = sock
        self._buf.clear()
        self._running = False

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
                self._buf.clear()
                self._running = False

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def _require_socket(self) -> socket.socket:
        if self._sock is None:
            raise GdbError("not connected to Dolphin's GDB stub")
        return self._sock

    # -- framing ------------------------------------------------------------

    def _read_byte(self) -> int:
        sock = self._require_socket()
        while not self._buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise GdbError("Dolphin closed the GDB connection")
            self._buf.extend(chunk)
        return self._buf.pop(0)

    def _send_raw(self, data: bytes) -> None:
        self._require_socket().sendall(data)

    def _send_packet(self, payload: str) -> None:
        self._send_raw(f"${payload}#{_checksum(payload)}".encode("ascii"))

    def _read_packet(self) -> str:
        # Skip anything up to the start of a packet. The stub tolerates stray
        # bytes in both directions, so we do the same rather than erroring on
        # an unexpected ack.
        while True:
            byte = self._read_byte()
            if byte == ord("$"):
                break
        payload = bytearray()
        while True:
            byte = self._read_byte()
            if byte == ord("#"):
                break
            payload.append(byte)
        received = chr(self._read_byte()) + chr(self._read_byte())
        text = payload.decode("ascii", errors="replace")
        if received.lower() != _checksum(text):
            self._send_raw(b"-")
            raise GdbError(f"checksum mismatch on reply {text!r}")
        self._send_raw(b"+")
        return text

    def _expect_ack(self) -> None:
        """Consume the stub's `+` for a packet we sent, tolerating a stray NAK."""
        byte = self._read_byte()
        if byte in (ord("+"), ord("-")):
            return
        # Not an ack: hand it back for whoever reads next.
        self._buf.insert(0, byte)

    def command(self, payload: str) -> str:
        """Send one packet and return the reply, retrying once on a NAK."""
        if self._running:
            raise GdbError(
                "the guest is running, so the stub will not answer until it stops. "
                "Call pause first."
            )
        for attempt in (0, 1):
            self._send_packet(payload)
            byte = self._read_byte()
            if byte == ord("+"):
                return self._read_packet()
            if byte == ord("-"):
                continue
            # Some replies arrive without an ack; treat the byte as the start
            # of the packet we were waiting for.
            if byte == ord("$"):
                self._buf.insert(0, byte)
                return self._read_packet()
            raise GdbError(f"unexpected byte {byte:#04x} while awaiting an ack")
        raise GdbError(f"stub kept rejecting the packet {payload!r}")

    @staticmethod
    def _check_error(reply: str, what: str) -> str:
        if reply.startswith("E"):
            raise GdbError(f"{what} failed: stub replied {reply}")
        return reply

    # -- memory -------------------------------------------------------------

    def read_memory(self, address: int, length: int) -> bytes:
        """Read `length` bytes of guest memory, transparently chunked."""
        if length < 0:
            raise ValueError("length must not be negative")
        out = bytearray()
        remaining = length
        cursor = address
        while remaining > 0:
            want = min(remaining, MAX_READ_CHUNK)
            reply = self.command(f"m{cursor:x},{want:x}")
            self._check_error(reply, f"reading {want} bytes at {cursor:#010x}")
            chunk = bytes.fromhex(reply)
            if not chunk:
                raise GdbError(f"empty reply reading {want} bytes at {cursor:#010x}")
            out.extend(chunk)
            cursor += len(chunk)
            remaining -= len(chunk)
        return bytes(out)

    def write_memory(self, address: int, data: bytes) -> None:
        cursor = address
        for offset in range(0, len(data), MAX_READ_CHUNK):
            chunk = data[offset : offset + MAX_READ_CHUNK]
            reply = self.command(f"M{cursor:x},{len(chunk):x}:{chunk.hex()}")
            self._check_error(reply, f"writing {len(chunk)} bytes at {cursor:#010x}")
            cursor += len(chunk)

    # -- registers ----------------------------------------------------------

    def read_gprs(self) -> list[int]:
        reply = self._check_error(self.command("g"), "reading registers")
        if len(reply) < 32 * 8:
            raise GdbError(f"short register reply ({len(reply)} chars)")
        return [int(reply[i * 8 : i * 8 + 8], 16) for i in range(32)]

    def read_register(self, reg_id: int) -> int:
        reply = self._check_error(self.command(f"p{reg_id:x}"), f"reading register {reg_id}")
        return int(reply[:8], 16)

    # -- execution ----------------------------------------------------------

    def halt_reason(self) -> str:
        return self.command("?")

    def resume(self) -> str:
        """Let the guest run.

        The stub acks the packet and then says nothing until the guest stops, so
        the ack has to be consumed here. Leaving it in the buffer would make the
        *next* command read it as its own ack and then take the following stop
        reply as its result, desynchronising the connection for good.
        """
        self._send_packet("c")
        self._expect_ack()
        self._running = True
        return "resumed"

    def interrupt(self) -> str:
        """Break into the stub with a raw 0x03, the way gdb's ^C does.

        The stub answers a break with a `T05` stop reply (`SendSignal` in
        GDBStub.cpp), which must be read here for the same reason.
        """
        if not self._running:
            return "already stopped"
        self._send_raw(b"\x03")
        reply = self._read_packet()
        self._running = False
        return reply

    def step(self) -> str:
        return self.command("s")

    # -- breakpoints --------------------------------------------------------

    #: `Z`/`z` kinds, per the RSP spec and the stub's HandleAddBreakpoint.
    BREAKPOINT_KINDS = {
        "software": 0,
        "hardware": 1,
        "write": 2,
        "read": 3,
        "access": 4,
    }

    def add_breakpoint(self, kind: str, address: int, length: int = 4) -> str:
        code = self._kind_code(kind)
        return self._check_error(
            self.command(f"Z{code},{address:x},{length:x}"), f"adding {kind} breakpoint"
        )

    def remove_breakpoint(self, kind: str, address: int, length: int = 4) -> str:
        code = self._kind_code(kind)
        return self._check_error(
            self.command(f"z{code},{address:x},{length:x}"), f"removing {kind} breakpoint"
        )

    @classmethod
    def _kind_code(cls, kind: str) -> int:
        try:
            return cls.BREAKPOINT_KINDS[kind]
        except KeyError:
            valid = ", ".join(sorted(cls.BREAKPOINT_KINDS))
            raise ValueError(f"unknown breakpoint kind {kind!r}; expected one of {valid}") from None


# The one place that knows how guest scalars are laid out. Everything big
# endian, because GameCube and Wii are - the detail that trips up anyone coming
# from a little endian memory scanner.
VALUE_FORMATS = {
    "u8": ">B",
    "s8": ">b",
    "u16": ">H",
    "s16": ">h",
    "u32": ">I",
    "s32": ">i",
    "u64": ">Q",
    "s64": ">q",
    "f32": ">f",
    "f64": ">d",
}


def _format_for(value_type: str) -> str:
    try:
        return VALUE_FORMATS[value_type]
    except KeyError:
        valid = ", ".join(VALUE_FORMATS)
        raise ValueError(
            f"unknown value type {value_type!r}; expected one of {valid}"
        ) from None


def value_size(value_type: str) -> int:
    """How many bytes the guest uses for this type."""
    import struct

    return struct.calcsize(_format_for(value_type))


def encode_value(value: int | float, value_type: str) -> bytes:
    """Encode a scalar the way the guest stores it."""
    import struct

    fmt = _format_for(value_type)
    if value_type.startswith("f"):
        return struct.pack(fmt, float(value))
    return struct.pack(fmt, int(value))


def decode_value(data: bytes, value_type: str) -> int | float:
    """Read a scalar back out of guest bytes."""
    import struct

    fmt = _format_for(value_type)
    expected = struct.calcsize(fmt)
    if len(data) != expected:
        raise ValueError(f"{value_type} needs {expected} bytes, got {len(data)}")
    return struct.unpack(fmt, data)[0]


def find_all(haystack: bytes, needle: bytes, base_address: int, alignment: int = 1) -> list[int]:
    """Every address in `haystack` holding `needle`, respecting `alignment`."""
    hits: list[int] = []
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return hits
        if alignment <= 1 or (base_address + index) % alignment == 0:
            hits.append(base_address + index)
        start = index + 1


def iter_region_chunks(
    start: int, size: int, chunk: int, overlap: int
) -> Iterable[tuple[int, int]]:
    """Yield (address, length) windows covering a region, with overlap.

    The overlap keeps a pattern that straddles a chunk boundary from being
    missed. Callers must dedupe hits, since the overlap can report one twice.
    """
    if chunk <= overlap:
        raise ValueError("chunk must be larger than overlap")
    address = start
    end = start + size
    while address < end:
        length = min(chunk, end - address)
        yield address, length
        if address + length >= end:
            return
        address += length - overlap
