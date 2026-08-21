# AYN Thor device reference

> `ayn-thor-user-manual.pdf` is gitignored. Copy it from a sibling Thor checkout
> or re-fetch from the FCC exhibit mirror:
> `https://apps.fcc.gov/eas/GetApplicationAttachment.html?id=8915262`
> (11 pages, 879,618 bytes, SHA-256
> `8714F2F6A70646AE79C6D39BA70EF8FE83DBD9109B2C32FFAED0C129F7CB92ED`).
> The Manuals+ endpoint blocks non-browser requests; the FCC mirror does not.

## Verified device facts

Read off the device over `adb`, not from spec sheets — re-check with the commands
in the right-hand column rather than trusting this table if something looks off.

| fact | value | how to re-check |
|---|---|---|
| product / device | `kalama`, model `AYN_Thor` | `adb shell getprop ro.product.model` |
| SoC | Snapdragon 8 Gen 2 (QCS8550) | `adb shell getprop ro.board.platform` |
| core map | cpu0-2 Cortex-A510 (`0xd46`), cpu3-4 Cortex-A715 (`0xd4d`), cpu5-6 Cortex-A710 (`0xd47`), cpu7 Cortex-X3 (`0xd4e`) | `adb shell grep -E '"'"'processor|CPU part'"'"' /proc/cpuinfo` |
| GPU | Adreno 740 | `adb shell dumpsys SurfaceFlinger \| grep -i gles` |
| gyroscope | **yes** — SENODIA `sh5001`, calibrated + uncalibrated, wakeup + non-wakeup | `adb shell dumpsys sensorservice \| grep -i gyro` |
| accelerometer | yes — SENODIA `sh5001` | same command, `-i accel` |
| fused motion | QTI rotation vector, game rotation vector, linear acceleration | same command |
| magnetometer | **not present** — there is no compass, so absolute-heading sensors are AOSP/GeoMag fallbacks | `adb shell dumpsys sensorservice \| grep -i magnet` |

CPU features present (`/proc/cpuinfo` Features, identical on all eight cores):

```
fp asimd evtstrm aes pmull sha1 sha2 crc32 atomics fphp asimdhp cpuid asimdrdm
jscvt fcma lrcpc dcpop sha3 sm3 sm4 asimddp sha512 asimdfhm dit uscat ilrcpc
flagm ssbs sb paca pacg dcpodp flagm2 frint i8mm bf16 bti
```

Notable for Dolphin: `atomics` (FEAT_LSE), `frint` (FEAT_FRINTTS), `asimddp`,
`fphp`/`asimdhp` (FP16), `i8mm`, `bf16`, `lrcpc`/`ilrcpc`, `flagm2`, `crc32`.
**Absent: `afp`** (FEAT_AFP) and SVE. The missing FEAT_AFP is load-bearing — see
`docs/research/arm64-thor-optimization.md`.
