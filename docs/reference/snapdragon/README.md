# Qualcomm reference material (Adreno 740 / Snapdragon 8 Gen 2)

> **The PDFs here are gitignored** (~24MB). Copy them from a sibling Thor
> checkout (`psvita/Vita3K-Thor/docs/reference/snapdragon/`) or re-fetch from
> Qualcomm's developer site. Only this README is tracked.

| file | what | why it matters to Dolphin |
|---|---|---|
| `adreno-game-developer-guide.pdf` | Adreno GPU developer guide | tiling/binning behaviour, render-pass and load/store costs — the Vulkan backend runs on an Adreno 740, and Thor users run Turnip via the GPU Driver Manager |
| `snapdragon-8-gen-2-product-brief.pdf` | SoC product brief | official core/clock/memory figures for the `kalama` platform |
| `snapdragon-opencl-optimization-guide.pdf` | OpenCL optimization guide | closest public description of Adreno wave/occupancy behaviour; useful background for shader cost, not for the API Dolphin uses |
| `qualcomm-linux-kernel-guide.pdf` | Qualcomm Linux kernel guide | scheduler/cpufreq behaviour behind big-core placement |

Adreno-specific driver notes for Turnip live with the GPU Driver Manager, not
here — see `AGENTS.md`.
