# Arm reference manuals (AArch64 host side)

> **The PDFs here are gitignored** (~71MB). They exist in a working checkout but
> are never committed. Copy them from a sibling Thor checkout
> (`psvita/Vita3K-Thor/docs/reference/arm/`, `melonds_HD/reference/arm/`, or
> `cemu-thor-experiment/docs/reference/arm/`), or re-fetch with the IDs below.
> Only this README and the AAPCS64 notes are tracked.

These describe the **host** the Thor runs Dolphin on. Dolphin's guest side is
PowerPC (Gekko/Broadway) — for guest semantics use the 750CL manual, not these.

| file | what | role | pages |
|---|---|---|---|
| `arm-architecture-reference-manual-a-profile.pdf` | Arm ARM, DDI 0487 | the architecture — exact instruction semantics, NaN/flag/memory-ordering rules | ~11,500 |
| `cortex-x3-software-optimization-guide.pdf` | Cortex-X3 SWOG | 1x prime (cpu7) | 66 |
| `cortex-a715-software-optimization-guide.pdf` | Cortex-A715 SWOG | 2x mid | 73 |
| `cortex-a710-software-optimization-guide.pdf` | Cortex-A710 SWOG | 2x mid | 92 |
| `cortex-a510-software-optimization-guide.pdf` | Cortex-A510 SWOG | 3x little | 54 |
| `aapcs64-callee-saved-notes.md` | AAPCS64 (Arm IHI 0055) notes | which registers survive a call — **tracked, not a PDF** | — |

Re-fetch: `https://documentation-service.arm.com/static/<id>` — A715 =
`6419bb9a8df5201251be08c3`, A510 = `61c2fb9eb691546d37bd2c05`. The X3 and A710
guides are served as direct PDFs from developer.arm.com.

**Which one answers which question.** The Arm ARM is the *architecture*: what an
instruction is defined to do. Reach for it on correctness questions — the ones
that matter for `JitArm64`, e.g. how PowerPC's non-IEEE flush-to-zero mode maps
onto `FPCR.FZ`/FEAT_AFP, or whether an ARM `FMAX` propagates NaN the way the
Gekko's `ps_max` does. The SWOGs are the *microarchitecture*: latency,
throughput, and issue pipes on these specific cores. Reach for those when asking
why emitted JIT code is slow. Neither answers the other's question.

The Thor's Snapdragon 8 Gen 2 (`kalama`, QCS8550) is 1x X3 + 2x A715 + 2x A710 +
3x A510. See `../thor/README.md` for the verified core map and feature list.

## Reading them

The `Read` tool cannot render these. Use pypdf:

```python
import pypdf
r = pypdf.PdfReader("docs/reference/arm/cortex-x3-software-optimization-guide.pdf")
print(r.pages[13].extract_text())   # 0-indexed
```
