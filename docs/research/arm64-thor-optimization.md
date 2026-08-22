# ARM64 optimization review — Dolphin on the AYN Thor

Date: 2026-08-21. Host: AYN Thor (`kalama`, Snapdragon 8 Gen 2 / QCS8550),
1x Cortex-X3 + 2x A715 + 2x A710 + 3x A510, Adreno 740.

Everything below was checked against this tree and against the device over
`adb`, not against folklore. Device facts and the commands that produce them are
in `docs/reference/thor/README.md`; the manuals that settle latency/semantics
questions are in `docs/reference/arm/`.

Ranked by (expected win) / (effort x risk). Items 1, 2 and 7 are **applied**; the
rest are open, and the ones that need on-device measurement say so.

Each heading carries its status. Nothing here has been measured on a running game
yet - the applied items are the ones whose effect can be verified from the build
output itself.

---

## 1. APPLIED - the build targeted baseline ARMv8-A, so every atomic went through a dispatch stub

`CMakeLists.txt:231` sets the only ARM64 arch flag in the tree:

```cmake
check_and_add_flag(HAVE_ARCH_ARMV8 -march=armv8-a+crc)
```

The Android build inherits it verbatim — from the generated
`Source/Android/app/.cxx/RelWithDebInfo/*/arm64-v8a/build.ninja`:

```
-O2 -g -DNDEBUG -fPIC -march=armv8-a+crc
```

ARMv8.0 has no LSE atomics, so the NDK's clang falls back to **outline-atomics**:
every `std::atomic` read-modify-write becomes a call to a helper that loads a
global feature flag and branches to either an LL/SC loop or an LSE instruction.
Confirmed in the shipped library:

```
$ llvm-nm --defined-only libmain.so | grep aarch64_
t __aarch64_cas1_acq_rel   t __aarch64_cas4_acq_rel   t __aarch64_cas8_acq_rel
t __aarch64_ldadd4_relax   t __aarch64_ldadd4_rel     t __aarch64_ldadd8_acq_rel
b __aarch64_have_lse_atomics
t init_have_lse_atomics
```

The Thor's `/proc/cpuinfo` lists `atomics`, so the LSE path is always the one
taken — we pay a load, a compare, a branch and a call around an instruction that
could be inlined. Dolphin leans on atomics in exactly the hot places: the
CPU↔GPU FIFO, `Common::Flag`/`Common::Event`, and the JIT's block-exit counters.

**Change:** for `ANDROID AND _M_ARM_64`, raise the arch to something the Thor
actually is — `-march=armv8.4-a+crc+crypto+dotprod+fp16` (or `-mcpu=cortex-x3`,
which also tunes scheduling for the prime core the CPU thread should be on).
Beyond inlined LSE this exposes FP16, dotprod, FEAT_FRINTTS and RCpc loads to
the compiler.

**Applied** as `DOLPHIN_ANDROID_ARM64_CPU_TARGET` in `CMakeLists.txt`, defaulting to
`thor` = `-march=armv8.4-a+crc+crypto+dotprod+fp16`. Set it to `baseline` to get the
old portable ARMv8.0-A flag back. Verify a build actually took the flag by checking
that `__aarch64_have_lse_atomics` is gone from `libmain.so` - if it is still there,
the build fell back.

**Measured result of the change**, comparing the same object file before and after:

| | `-march=armv8-a+crc` | `-march=armv8.4-a+...` |
|---|---:|---:|
| inline LSE atomics in `VideoCommon/Fifo.cpp.o` | 0 | **17** |
| LL/SC pairs in the same object | 0 | 0 |
| outline-atomics stubs in the linked `libmain.so` | 17 | **7** |

The seven that survive are in the NDK's prebuilt `libc++_static` (`shared_ptr`
refcounting), which is compiled at the ARMv8.0 baseline and is not ours to
rebuild. Everything Dolphin itself compiles now uses the instruction directly.

**Cost:** the APK stops running on pre-ARMv8.4 arm64 devices — it will `SIGILL`,
not degrade. That is consistent with the project brief ("a personal-use AYN Thor
Android fork, not a general Android compatibility promise") but it must be said
out loud in `Readme.md` if we take it.

## 2. APPLIED - the release build was `-O2 -g`, not `-O3`

`Source/Android/app/build.gradle.kts:105` passes
`-DCMAKE_BUILD_TYPE=RelWithDebInfo`, which is CMake's `-O2 -g -DNDEBUG`. A
`Release` build is `-O3 -DNDEBUG` with no debug info. `-O3` mostly buys
vectorization and more aggressive inlining, which matters for the software
renderer paths, the audio mixer and `VideoCommon` vertex loaders more than for
JIT-generated code.

**Applied:** `CMAKE_BUILD_TYPE` moved out of `defaultConfig` and set per build type -
`release` is now `Release`, `debug` stays `RelWithDebInfo`.

Keep `RelWithDebInfo` available for crash chasing — this should be a switch, not
a replacement. AGENTS.md already says release builds are the normal Thor path.

## 3. OPEN - LTO is available and off

`CMakeLists.txt:108` — `option(ENABLE_LTO "Enables Link Time Optimization" OFF)`,
wired to `CMAKE_INTERPROCEDURAL_OPTIMIZATION` at line 384. ThinLTO across
`Core`/`VideoCommon`/`Common` is a plausible low-single-digit win for a large
link-time cost. Worth one measured experiment, not a default.

## 4. IMPLEMENTED but unmeasured - thread affinity was compiled out on Android, and unused anyway

`Source/Core/Common/Thread.cpp:122`:

```cpp
#elif (defined __linux__ || defined BSD4_4 || ...) && !(defined ANDROID)
```

`SetThreadAffinity` is a no-op on Android, and nothing in `Source/Core` or
`Source/Android/jni` calls it or `SetCurrentThreadAffinity` on any platform.

On a 3+2+2+1 big.LITTLE part this is the largest available runtime lever. The
threads that matter are named at `Source/Core/Core/Core.cpp:327` (`CPU thread`),
`:329` (`CPU-GPU thread`) and `:473` (`Video thread`). Nothing stops the kernel
from parking the CPU thread on a Cortex-A510, which is roughly a third of X3
throughput on this workload.

**Implemented, opt-in.** `Common::SetCurrentThreadAffinity` now works on Android - it goes
through `sched_setaffinity(0, ...)` rather than `pthread_setaffinity_np`, which bionic only
gained at API 26 while Dolphin's `minSdk` is 24. `Common::GetPerformanceCoreAffinityMask`
reads each CPU's `cpufreq/cpuinfo_max_freq` and keeps the cores within 25% of the fastest,
which on the Thor selects the X3 and the A715/A710s and drops the A510s without hardcoding a
topology. `Config::MAIN_PERFORMANCE_CORE_AFFINITY` (Android: `Pin To Performance Cores`)
applies it to the CPU and Video threads. **Default off, and not yet benchmarked** - see the
caveats below, which are the reason it is not on.

Note it pins to the whole performance cluster rather than to one core each, which leaves the
scheduler room to move threads between the X3 and the A715/A710s.

Original analysis:

**Change:** drop the `!(defined ANDROID)` exclusion (bionic has
`sched_setaffinity`/`pthread_setaffinity_np` and a process may always re-affine
its own threads), then pin the CPU thread to cpu7 and the video thread to
cpu5/cpu6 behind a setting, defaulting off until measured. Two caveats worth
respecting: the vendor scheduler and thermal governor will fight a hard pin, and
a wrong pin is *worse* than none. This needs on-device measurement per game, not
a guess.

## 5. WON'T FIX in software - FEAT_AFP is absent on this SoC, so the FP slow path is permanent here

The Thor's feature list has no `afp` (and no SVE). So `cpu_info.bAFP` is false,
and three places take the slower branch:

- `Source/Core/Core/PowerPC/JitArm64/JitArm64_FloatingPoint.cpp:500` — falls back
  whenever an operand is not known store-safe.
- `Source/Core/Core/PowerPC/JitArm64/JitAsm.cpp:576` — skips the fast FPCR setup.
- `Source/Core/Common/ArmFPURoundMode.cpp:54` — this is the device that shows the
  non-IEEE-mode warning.

There is no software fix; FEAT_AFP is hardware. The useful consequence is that
**`js.fpr_is_store_safe` inference is load-bearing on the Thor** in a way it is
not on an AFP-capable phone. Any improvement to that analysis is worth more here
than the same work upstream would be worth on newer silicon. That is a real
optimization target, and it is a JIT-correctness-sensitive one — the Arm ARM in
`docs/reference/arm/` is the manual that settles it.

## 6. OPEN, low priority - the emitter has no LSE or FRINTTS encodings

`Source/Core/Common/Arm64Emitter.h` exposes `LDAXR`/`STLXR` and no `CAS*`,
`LDADD*` or `SWP*`. The Thor supports all of them (`atomics`), but the JIT only
needs exclusives for PowerPC `lwarx`/`stwcx.`, which is not hot in GameCube/Wii
titles. Similarly `frint` (FEAT_FRINTTS) is present, but `FRINT32Z`/`FRINT64Z`
saturate differently from PowerPC `fctiwz`, so it is not a drop-in for the
float→int conversion path. Both are "correct but probably not worth it".

## 7. APPLIED - build hygiene: we compiled a second ABI we cannot run

`Source/Android/app/build.gradle.kts:108` builds `arm64-v8a` **and** `x86_64`.
The Thor is arm64. **Applied:** `abiFilters` is now `arm64-v8a` only.

The release APK also drops from 23.9MB to 16.7MB.

A full `:app:assembleRelease` from clean was ~23 minutes here;
roughly half of that is an ABI that never gets installed. No runtime effect —
but it halves the edit/build/test loop, which is why it is on this list.

---

## Not a problem

- `cpu_info.bCRC32` is detected correctly on this device and already used by
  `Common/Hash.cpp:421` and `DiscIO/VolumeVerifier.cpp:378`.
- AAPCS64 register residency is handled correctly. AArch64 preserves only the low
  64 bits of `v8`-`v15` across a call, and `Arm64FPRCache::GetCallerSavedUsed`
  (`JitArm64_RegCache.cpp:952`) already spills a Q8-Q15 register whenever its top
  half is live. Widening `CALLER_SAVED_FPRS` would be a correctness regression,
  not an optimization — see `docs/reference/arm/aapcs64-callee-saved-notes.md`.
- GPU-side work is already covered by the fork's GPU Driver Manager (Turnip).
  Adreno 740 tiling/binning behaviour is in
  `docs/reference/snapdragon/adreno-game-developer-guide.pdf`.

## Status

Applied, verifiable from the build itself:

1. `abiFilters` is `arm64-v8a` only.
2. The release path configures CMake as `Release` (`-O3`), debug as `RelWithDebInfo`.
3. Android arm64 compiles for ARMv8.4-A by default, documented in `Readme.md` as a
   Thor-only build.

Verified on the device, not just at build time: the ARMv8.4 binary installs and
runs on the Thor, and Dolphin's own aarch64 unit-test suite passes **1031 of 1031**
on it. That includes the five `JitArm64` emitter tests (`ConvertSingleDouble`, `FPRF`,
`Fres`, `Frsqrte`, `MovI2R`), which assemble and execute JIT output, so the emitter does
run on this hardware. No game has been booted, so the JIT has not been exercised against
real guest code and the video backend has not been exercised at all.

### First timing run: no measurable difference

The pre-change binary (`-O2 -g`, `-march=armv8-a+crc`) and the post-change one (`-O3`,
`-march=armv8.4-a+...`) were both run on the Thor, pinned to the performance cores with
`taskset f8`, five alternating runs of the PowerPC/JIT/VertexLoader/Hash subset:

| | runs (ms) | median |
|---|---|---:|
| before | 3918, 3962, 3939, 4074, 3909 | **3939** |
| after | 3914, 3920, 4197, 4034, 3981 | **3981** |

That is a null result - the 1% gap sits well inside the ~7% run-to-run spread. **Better
codegen has not been shown to be faster.**

This does not refute section 1, but it does not support it either, and the distinction
matters. The unit suite is dominated by vertex-loader table churn, DSP assembly text
handling and filesystem tests. It barely touches the CPU/GPU FIFO, `Common::Flag` or
`Common::Event` - the atomic-heavy paths where inlined LSE was supposed to pay off - and it
runs no guest code beyond a handful of JIT emitter tests. It is the wrong workload to detect
the thing that was changed.

So the ARMv8.4 build is justified by what it demonstrably does to the generated code, and by
nothing more than that so far. A real title is still the only way to know whether it matters.

### The device is shared, which makes on-device timing hard

A first attempt at timing the affinity setting against a real game was thrown away: identical
90-second runs produced 5347, 1517, 324 and 5408 emulated frames, and two of those ran the same
configuration as each other. Other Claude sessions share this Thor, so a run can be competing
with another emulator for the same cores. Any future measurement here needs repeated runs of
each configuration, interleaved, with the result discarded when repeats of one configuration
disagree. See the shared-device section of `AGENTS.md`.

Open, in the order worth doing them:

4. **Measure.** Nothing here has been timed against a running game - there were no game
   images on the device. This is the blocking item for everything below.
5. Thread affinity (section 4) is now implemented and off by default. Turning it on is a
   one-tap A/B once a game is available; it stays off until it earns its place.
6. LTO (section 3) - one measured experiment.
7. `js.fpr_is_store_safe` inference (section 5) - worth more on this device than upstream,
   and the only item here that touches JIT correctness.
