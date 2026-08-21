# CLAUDE.md

The instructions for this repository live in [AGENTS.md](AGENTS.md).

Read `AGENTS.md` before making changes here and follow it as if its contents
were written in this file. It is the single source of truth for project scope,
git workflow, Android touch points, build/test commands, and coding style.

Two things in `AGENTS.md` are easy to miss and worth naming here:

- **Host hardware and vendor manuals** — the AYN Thor's verified core map, CPU
  feature list and sensor inventory are in
  [docs/reference/thor/README.md](docs/reference/thor/README.md). The Arm and
  Qualcomm PDFs under `docs/reference/` are gitignored and stay local; each
  directory's `README.md` says how to re-fetch them.
- **ARM64 optimization** — reviewed, with the verified evidence, in
  [docs/research/arm64-thor-optimization.md](docs/research/arm64-thor-optimization.md).
  None of it is applied. Read it before touching build flags.
