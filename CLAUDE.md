# CLAUDE.md

The instructions for this repository live in [AGENTS.md](AGENTS.md).

Read `AGENTS.md` before making changes here and follow it as if its contents
were written in this file. It is the single source of truth for project scope,
git workflow, Android touch points, build/test commands, and coding style.

## Never stall on the AYN Thor

Several Claude sessions work on emulator forks on this machine at once, and they
all share one AYN Thor over one `adb` connection. **If the device is busy, do
not wait for it — keep doing code work.** Reading, editing, building, reviewing
and writing docs never need the device. Blocking on hardware while source work
remains is always the wrong call.

Two consequences worth carrying:

- **Any timing measured while another session is using the device is void.** An
  A/B on 2026-08-21 produced 5347, 1517, 324 and 5408 emulated frames across
  identical 90-second runs — and the last two ran the *same* configuration.
  Repeat every measurement, and discard the result if the repeats disagree.
- **Leave the device as you found it**: force-stop the emulator, restore any
  config you edited, and remove anything you pushed. `Config/GFX.ini` and
  `Config/Dolphin.ini` hold the user's GPU driver choice and game paths.

See [the shared-device section of AGENTS.md](AGENTS.md) for the details,
including where the game images actually live.

## Two other things that are easy to miss

- **Host hardware and vendor manuals** — the Thor's verified core map, CPU
  feature list and sensor inventory are in
  [docs/reference/thor/README.md](docs/reference/thor/README.md). The Arm and
  Qualcomm PDFs under `docs/reference/` are gitignored and stay local; each
  directory's `README.md` says how to re-fetch them.
- **ARM64 optimization** — reviewed, with the verified evidence and one honest
  null result, in
  [docs/research/arm64-thor-optimization.md](docs/research/arm64-thor-optimization.md).
  Read it before touching build flags.
