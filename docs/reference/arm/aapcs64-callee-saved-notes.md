# AAPCS64 — which host registers survive a call, and how JitArm64 handles it

**Source:** Arm IHI 0055, *Procedure Call Standard for the Arm 64-bit Architecture (AAPCS64)*.
Canonical text: <https://github.com/ARM-software/abi-aa/blob/main/aapcs64/aapcs64.rst>

This is the manual that governs what `JitArm64` may leave in a host register when
it calls out to C++ (MMU slow paths, interpreter fallbacks, `HLE`). It is not in
`docs/reference/arm/` as a PDF — these are the two clauses that matter plus what
this tree already does about them.

## The two clauses

**General-purpose registers — verbatim:**

> "Registers r19-r29 and SP are Callee-saved."

**SIMD/FP registers — verbatim, and this is the one that bites:**

> "Additionally, only the bottom 64 bits of each value stored in v8-v15 need to be
> `Callee-saved`; it is the responsibility of the caller to preserve larger values."

So there is **no** AArch64 register that preserves a full 128-bit value across a
call. A called C++ function may save only `d8`-`d15` in its prologue and then use
the full `q8`-`q15` freely, destroying the upper halves.

## What JitArm64 does with that

Dolphin holds a paired-single as a full 128-bit value, so the clause above is
directly load-bearing — and the tree models it correctly:

- `Source/Core/Common/Arm64Emitter.h:1074` —
  `CALLER_SAVED_FPRS = BitSet32(0xFFFF00FF)`, i.e. Q0-Q7 and Q16-Q31. Q8-Q15 are
  treated as callee-saved, which is right *for the low half only*.
- `Source/Core/Core/PowerPC/JitArm64/JitArm64_RegCache.cpp:952` — the gap is
  closed here:

  ```cpp
  if (it.IsLocked() && (IsCallerSaved(it.GetReg()) || IsTopHalfUsed(it.GetReg())))
  ```

  `Arm64FPRCache::GetCallerSavedUsed` spills a Q8-Q15 register too whenever its
  **top half** is live (`IsTopHalfUsed`, line 813). A register holding only a
  `Single`/`Duplicated` value stays resident across the call; one holding a real
  128-bit `Register`-type value gets spilled.
- `Source/Core/Core/PowerPC/JitArm64/JitAsm.cpp:39-42` — on entry to the
  dispatcher the JIT saves `ALL_CALLEE_SAVED = 0x7FF80000` (x19-x30) and
  `ALL_CALLEE_SAVED_FPR = 0x0000FF00` (Q8-Q15) on behalf of its C++ caller.

**Do not "optimize" this by widening the callee-saved FPR set.** The 128-bit
residency it looks like it buys does not exist in the ABI.

## Registers this tree has already spent

`Source/Core/Core/PowerPC/JitArm64/JitArm64_RegCache.h`: `MEM_REG = X28`,
`PPC_REG = X29`, `DISPATCHER_PC = W26`. The GPR allocation order
(`JitArm64_RegCache.cpp:444`) deliberately hands out callee-saved W19-W27 first
so guest state survives calls where possible; the FPR order
(`:752`) does the same with Q8-Q15.
