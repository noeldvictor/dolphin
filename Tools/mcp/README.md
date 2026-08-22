# Dolphin MCP server

An MCP server that gives an AI client direct access to the running game's
memory and CPU state: read and write values, scan RAM for a value and narrow
the candidates down, set watchpoints, step. It is aimed at the thing this fork
is actually for - finding and testing cheats - but it is just as useful for
answering "what is this game doing" without guesswork.

## Why it lives here and not in `Source/`

It talks to Dolphin's **existing** GDB stub
(`Source/Core/Core/PowerPC/GDBStub.cpp`) over TCP. The emulator needs no
modification at all. That is deliberate: this fork has to keep merging
upstream, and every line added under `Source/` is merge tax forever - the last
sync was 390 commits with four conflicts. A host-side tool costs nothing at
merge time.

## Setup

**1. Turn on the stub.** It is off by default (`GDBPort` defaults to `-1`).
On Android, with the app closed:

```powershell
$cfg = "/storage/emulated/0/Android/data/org.dolphinemu.dolphinemu/files/Config/Dolphin.ini"
adb shell "grep -q '^\[General\]' $cfg && sed -i '/^\[General\]/a GDBPort = 2159' $cfg"
```

On desktop, set `GDBPort = 2159` under `[General]` in `Dolphin.ini`.

**2. Forward the port** (Android only):

```powershell
adb forward tcp:2159 tcp:2159
```

**3. Boot a game.** It will hang on the loading screen until something
connects - see the caveats below. That is expected.

**4. Register the server:**

```powershell
claude mcp add dolphin -- python <repo>/Tools/mcp/dolphin_mcp.py
```

Then call `status`, and `resume` to let the game run.

## Caveats that will otherwise waste your afternoon

- **The stub blocks the boot until a client connects.** `GDBStub::Init` calls
  `accept()` synchronously from `Core.cpp`, so a game booted with `GDBPort` set
  sits there until you attach. This is not a hang.
- **The game starts paused.** `Core.cpp` passes `force_paused = true` when the
  stub is enabled, so nothing runs until you call `resume`.
- **It is disabled under RetroAchievements hardcore mode**, by design upstream.
- **Set `GDBPort` back to `-1` for normal play**, or every boot will wait for a
  debugger.

## Tools

| tool | what it does |
|---|---|
| `status` | Is the stub reachable, what is the CPU doing, where is PC |
| `read_memory` / `read_value` / `write_value` | Raw bytes, or one typed value |
| `search_memory` | Scan MEM1 (or Wii MEM2) for a value, return every address holding it |
| `filter_candidates` | Keep only the addresses that *now* hold a value |
| `read_registers` | The 32 GPRs plus PC, LR, CTR |
| `set_watchpoint` / `clear_watchpoint` | Break when the guest reads or writes an address |
| `resume` / `pause` / `step` | Run, break in, single-step |

### Finding a cheat

The classic scanner loop, with the AI driving it:

1. `search_memory` for the value you can see in game - rupees, HP, a timer.
   Expect hundreds of hits.
2. Change it in game, then `filter_candidates` with the new value.
3. Repeat two or three times and you are down to one or two addresses.
4. `write_value` to confirm you have the right one.
5. `set_watchpoint` on it to find the code that writes it, which is what you
   need for a stable Gecko/AR code rather than a one-shot poke.

**The guest is big endian.** `search_memory` handles that for you, but it is
the reason a value found with a little-endian scanner will not match here.

## Notes on the protocol

MCP over stdio is newline-delimited JSON-RPC 2.0, so this is dependency-free -
no SDK to install, nothing to keep in step with a package release. The GDB side
implements only what Dolphin's stub actually supports, which is documented at
the top of `gdb_client.py` with the details read out of `GDBStub.cpp`: a 10000
byte packet buffer capping `m` at 4998 bytes, and a `g` reply that carries only
the 32 GPRs, so everything else goes through `p`.

## Tests

```powershell
python Tools/mcp/test_dolphin_mcp.py     # 31 tests - the server itself
python Tools/mcp/test_stub_contract.py   # 12 tests - our assumptions about Dolphin
```

Neither needs a device or a running emulator.

`test_dolphin_mcp.py` runs the server against a fake stub, covering the packet
framing, read chunking, big-endian encoding, scan-window overlap (a value
straddling a window boundary must still be found) and the full JSON-RPC round
trip including malformed input.

`test_stub_contract.py` is the one that earns its keep over time. `gdb_client.py`
hardcodes facts read out of `GDBStub.cpp` - the packet buffer size that caps a
read, the register ids behind `p`, which commands exist, and the fact that
enabling the stub forces a paused boot. Upstream owns all of that, and this fork
merges upstream regularly; a sync has already deleted a method out from under
code that needed it. So these tests parse the stub and fail if it stops matching.
**A failure there is not a bug in this server** - it means upstream changed the
stub and the client needs updating to match.

What no test here can check is that the live stub agrees with our reading of it.
That needs a game running on hardware.
