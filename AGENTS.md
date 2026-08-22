# AGENTS.md

## Scope

These instructions apply to the whole repository.

## Project Brief

This fork is an Android-focused Dolphin experiment for the AYN Thor handheld. Public-facing branding is now `Dolphin Thor Experiment`, matching the renamed fork at `git@github.com:noeldvictor/dolphin-thor-experiment.git`. The immediate feature goals are:

- Show a visible badge on game covers when cheats are available for that game.
- Add an Android hotkey layer for easy savestate actions from the built-in/controller inputs.
- Add a speed toggle hotkey.
- Build an Android APK and install it to the AYN Thor over USB.

Current product decisions from 2026-05-10:

- Prefer bundling/downloading cheats for all supported games into the repo, along with covers if practical. The Android fork currently carries a bundled Gecko-code cache generated from the RC24/GameHacking mirror, with source notes in `Data/Sys/GeckoCodes.README.txt`.
- Cheat badges should be small and visible on the mobile game grid and TV/Leanback cards.
- Save/load defaults should be Android-editable hotkeys.
- Initial save/load default: Select + right stick up/down, likely mapped to quick save/load unless changed.
- Speed toggle default: Select + R.
- Users should be able to choose the toggle speed/fast-forward percentage. Default target is 200%.
- APK target going forward is a sideload-signed release build installed to the user's AYN Thor. Use debug builds only when actively chasing crashes or JNI/debugger issues.
- Cheats should be enabled by default.
- Android in-game menu/OSD should expose a quick `Cheats: On/Off` toggle.
- Android app branding should read `Dolphin Thor Experiment` for the fork; the debug APK label is `Dolphin Thor Experiment Debug`.
- Public README tone should be clear and blunt: this is a personal-use AI/vibe-coded experiment, no stability guarantees, no support queue, and people should fork it if they want different behavior. Do not mention APK downloads in `Readme.md`.
- Project art lives in `docs/assets/`; README screenshots live in `docs/screenshots/`.
- GPU driver setup should stay easy for Thor users: the Android GPU Driver Manager has a one-tap recommended Turnip download/install from `K11MCH1/AdrenoToolsDrivers`, a refreshable selectable GitHub ZIP list, a manual local ZIP install path, and a system-driver reset.
- Optional AYN/Odin-style Android controller profiles should be available for GameCube, Wii Classic Controller, and Wii Remote + Nunchuk layouts.
- AYN Thor rumble is routed through Android's system vibrator (`Android/0/Device Sensors:Motor 0`) as game/media vibration. Android will ignore app rumble when the device-wide `vibrate_on` system setting is `0`. Current device preference is to keep OS/app haptic feedback and keyboard vibration enabled too.

The repository remote should use SSH:

```powershell
git remote set-url origin git@github.com:noeldvictor/dolphin-thor-experiment.git
```

## Git Workflow

- Work directly on the repository's primary branch unless the user explicitly asks for a separate branch.
- This fork's current primary branch is `master` (`origin/HEAD -> origin/master`). The user may casually call it "main"; treat that as the primary branch, not as permission to create a new `main` branch.
- Commit and push directly to the primary branch when changes are ready.
- Do not create `codex/` feature branches for this project unless the user specifically requests one.
- If an accidental feature branch is created, move the commits to the primary branch, push there, then delete the extra branch locally and remotely.

## Android Touch Points

- Android project: `Source/Android`
- Main APK module: `Source/Android/app`
- Mobile game grid cards:
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/adapters/GameAdapter.kt`
  - `Source/Android/app/src/main/res/layout/card_game.xml`
- Android TV/Leanback game cards:
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/adapters/GameRowPresenter.kt`
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/viewholders/TvGameViewHolder.kt`
- Game metadata model:
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/model/GameFile.kt`
  - Useful calls include `getGameId()`, `getRevision()`, `getPath()`, and `customCoverPath`.
- Cheat UI/model:
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/features/cheats/model/CheatsViewModel.kt`
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/features/cheats/model/ARCheat.kt`
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/features/cheats/model/GeckoCheat.kt`
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/features/cheats/model/PatchCheat.kt`
  - Native loaders live under `Source/Android/jni/Cheats`.
- Emulation activity and input dispatch:
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/activities/EmulationActivity.kt`
  - `dispatchKeyEvent` and `dispatchGenericMotionEvent` currently forward controller input to `ControllerInterface` when the menu is not visible.
- Motion / gyro input:
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/features/input/model/DolphinSensorEventListener.kt`
  - Device sensors surface as the `Android/0/Device Sensors` device; the gyro axes are
    `Gyro Pitch Up/Down`, `Gyro Roll Right/Left`, `Gyro Yaw Left/Right`, and the accelerometer axes are
    `Accel Right/Left/Forward/Backward/Up/Down`. Map these to the Wii Remote IMU controls for motion games.
  - The Thor has a real gyroscope (SENODIA `sh5001`) plus accelerometer and QTI rotation-vector fusion,
    but **no magnetometer**, so there is no absolute heading. Verified with `adb shell dumpsys sensorservice`.
  - Controller-attached sensors need Android 12+ (`Build.VERSION_CODES.S`); the built-in sensors do not.
- Native input bridge:
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/features/input/model/ControllerInterface.kt`
  - `Source/Core/InputCommon/ControllerInterface/Android/Android.cpp`
  - Android rumble/haptics also pass through these files plus `DolphinVibratorManager*.kt`.
- Android-bundled controller profiles:
  - `Data/Sys/Profiles/GCPad/AYN Odin Android GameCube.ini`
  - `Data/Sys/Profiles/Wiimote/AYN Odin Android Classic Controller.ini`
  - `Data/Sys/Profiles/Wiimote/AYN Odin Android Nunchuk.ini`
  - `Data/Sys/Profiles/Wiimote/AYN Thor Android Wii Remote Motion.ini` (gyro/accelerometer motion plus IMUIR pointing)
  - Android build configuration copies `Data/Sys` into the ignored/generated `Source/Android/app/src/main/assets/Sys` folder.
  - That copy is a **configure-time** `file(COPY)` in `Source/Android/jni/CMakeLists.txt`, not a build step. A new
    file under `Data/Sys` (a profile, a GameSettings INI, a regenerated `GeckoCodes.zip`) will **not** reach the APK
    from an incremental build - CMake has to re-configure first. Touch `Source/Android/jni/CMakeLists.txt` to force
    it, then check the APK actually contains the file before believing it shipped:

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path Source/Android/app/build/outputs/apk/release/app-release.apk))
$z.Entries | Where-Object { $_.FullName -like '*Profiles/Wiimote*' } | ForEach-Object { $_.FullName }
$z.Dispose()
```
- Savestate entry points:
  - Kotlin: `NativeLibrary.SaveState(slot)` and `NativeLibrary.LoadState(slot)`
  - JNI: `Source/Android/jni/MainAndroid.cpp`
  - Existing menu mapping: `EmulationActivity.handleMenuAction`
  - Quick save/load currently use slot `9`; menu slots 1-6 use slots `0` through `5`.
- Speed setting:
  - Android setting: `FloatSetting.MAIN_EMULATION_SPEED`
  - Native config: `Config::MAIN_EMULATION_SPEED`
  - `0.0f` means unlimited; `1.0f` means 100%.

## Feature Guidance

For cover cheat badges, keep the work lightweight. Avoid loading full cheat details on the UI thread for every game card if possible. Prefer a small availability provider/cache keyed by `gameId` plus `revision`, and update the mobile and TV card surfaces consistently. Badge state should come from user-local cheats plus the bundled Gecko cache; do not do synchronous per-card network checks.

For bundled Gecko codes:

- `https://codes.rc24.xyz/gecko.db` is not a real database artifact; it returns the mirror homepage.
- Use `https://codes.rc24.xyz/txt.php?txt=<GameTDBID>` for per-game Gecko text files. The RC24 homepage states those codes come from GameHacking.org.
- Regenerate the Android cache with `python Tools/update_gecko_code_cache.py`.
- Generated cache path: `Data/Sys/GeckoCodes.zip`.
- Keep source/provenance notes beside the zip in `Data/Sys/GeckoCodes.README.txt`.
- The cheat UI should load bundled codes first and fall back to the network downloader only when the bundle has no entry.
- Some GameCube games need default Action Replay INIs instead of bundled Gecko text. Example: Fire Emblem: Path of Radiance US `GFEE01` already has default AR codes, and PAL `GFEP01` is carried in `Data/Sys/GameSettings/GFEP01.ini` from GameHacking.org game 54385 because it is absent from the RC24 Gecko mirror.

For covers, GameTDB region misses are common. Prefer trying the game's primary region first, then reasonable fallbacks such as `EN`, `US`, `JA`, and `KO` before falling back to the no-banner art.

For Android hotkeys, prefer a small `EmulationActivity` helper that sees key and motion events before they are passed to `ControllerInterface`. It should be edge-triggered and debounced so holding a combo does not spam savestates. It should only consume events when an exact hotkey combo fires; otherwise normal controller input should keep flowing to the emulator. The requested default mapping is Select plus right stick up/down for save/load and Select + R for speed toggle, but confirm the exact Android key/axis codes on the AYN Thor before hardcoding. Right-stick axes can vary by device.

For speed toggle, prefer toggling between normal speed (`FloatSetting.MAIN_EMULATION_SPEED = 1.0f`) and a user-configurable fast-forward percentage. Default fast-forward target is 200% (`2.0f`). If changing runtime config directly, make sure the core sees the updated value and the Settings object is saved only when persistence is intended.

## Host Hardware And Reference Manuals

The Thor is a Snapdragon 8 Gen 2 (`kalama`, QCS8550): 1x Cortex-X3 (cpu7), 2x Cortex-A715 (cpu3-4),
2x Cortex-A710 (cpu5-6), 3x Cortex-A510 (cpu0-2), Adreno 740. Verified core map, CPU feature list and
sensor inventory live in `docs/reference/thor/README.md` with the `adb` commands that reproduce them.
Re-check the device rather than trusting a spec sheet.

Vendor manuals are kept in `docs/reference/` and are **gitignored** — the PDFs are ~95MB and stay local:

- `docs/reference/arm/` — Arm ARM (DDI 0487) plus the Cortex-X3/A715/A710/A510 software optimization guides,
  and AAPCS64 notes. Architecture questions (instruction semantics, FP/NaN behaviour) go to the Arm ARM;
  performance questions (latency, throughput, issue pipes) go to the SWOGs.
- `docs/reference/snapdragon/` — Adreno game developer guide, 8 Gen 2 product brief, OpenCL and kernel guides.
- `docs/reference/thor/` — AYN Thor user manual and the verified device facts.

Each directory's `README.md` records provenance and how to re-fetch. Copy the PDFs from a sibling Thor
checkout (for example `psvita/Vita3K-Thor/docs/reference/`) rather than re-downloading.

Thread placement: `Config::MAIN_PERFORMANCE_CORE_AFFINITY` (`Pin To Performance Cores` in Android's general
settings, off by default) pins the CPU and Video threads to the host's fastest CPU cluster.
`Common::GetPerformanceCoreAffinityMask` derives that cluster from cpufreq rather than hardcoding a
topology, so on the Thor it selects the X3 plus the A715/A710 cores and drops the A510s. **This has not
been benchmarked against a running game.** Treat it as something to A/B per title, not as a default.

Host-side ARM64 optimization opportunities in this tree are reviewed in
`docs/research/arm64-thor-optimization.md`. Nothing in that review is applied yet; read it before changing
build flags, and note that raising `-march` past ARMv8.0 makes the APK Thor-only.

## Build And Deploy

Use the Android project from `Source/Android`.

```powershell
git submodule update --init --recursive
cd Source/Android
.\gradlew.bat :app:assembleRelease `
  -Pkeystore="$env:USERPROFILE\.android\debug.keystore" `
  -Pstorepass=android `
  -Pkeyalias=androiddebugkey `
  -Pkeypass=android
adb install -r app\build\outputs\apk\release\app-release.apk
```

Native build settings that are deliberately Thor-specific:

- `abiFilters` builds `arm64-v8a` only. Add `x86_64` back temporarily if you need the Android emulator.
- The `release` build type configures CMake as `Release` (`-O3`); `debug` uses `RelWithDebInfo` (`-O2 -g`).
  Chase native crashes with the debug build, where the symbols are.
- `DOLPHIN_ANDROID_ARM64_CPU_TARGET` defaults to `thor`, which compiles for ARMv8.4-A
  (`-march=armv8.4-a+crc+crypto+dotprod+fp16`) so atomics inline as LSE instead of going through clang's
  outline-atomics stubs. This makes the APK Thor-class-only - it SIGILLs on older arm64 devices. Pass
  `-DDOLPHIN_ANDROID_ARM64_CPU_TARGET=baseline` for a portable build.
- Verify the arch flag actually took effect by disassembling one of our own objects and looking for
  inline LSE atomics (`cas*`, `ldadd*`, `swp*`) rather than calls out to a stub:

```powershell
$o = "Source/Android/app/.cxx/Release/*/arm64-v8a/Source/Core/VideoCommon/CMakeFiles/videocommon.dir/Fifo.cpp.o"
llvm-objdump -d --no-show-raw-insn (Resolve-Path $o) | Select-String '\s(casal|cas|ldaddal|ldadd|swpal|swp)\s'
```

  A `thor` build gives 17 hits in `Fifo.cpp.o`; a `baseline` build gives none. Do **not** use
  `llvm-nm ... __aarch64_have_lse_atomics` on the linked `libmain.so` as the test - the NDK's prebuilt
  `libc++_static` is compiled at the ARMv8.0 baseline and keeps about seven outline-atomics stubs alive
  (`shared_ptr` refcounting) no matter what we pass. The useful signal is that the count drops from 17 to 7,
  not that it reaches zero.

The command above is a release build type signed with the local Android debug keystore for Thor sideloading. It is not a Play Store production signing key. Use Gradle's release install task once the device is visible:

```powershell
cd Source/Android
.\gradlew.bat :app:installRelease `
  -Pkeystore="$env:USERPROFILE\.android\debug.keystore" `
  -Pstorepass=android `
  -Pkeyalias=androiddebugkey `
  -Pkeypass=android
```

Debug build fallback for crash/debug work:

```powershell
cd Source/Android
.\gradlew.bat :app:installDebug
```

Environment notes from this workspace on 2026-05-09:

- `adb` is available from the scrcpy WinGet package.
- `adb devices -l` showed `c3ca0370 device product:kalama model:AYN_Thor device:kalama`.
- Android SDK files exist under `%LOCALAPPDATA%\Android\Sdk`.
- Microsoft OpenJDK 17 was installed with `winget install --id Microsoft.OpenJDK.17 --exact`.
- Machine `JAVA_HOME` is `C:\Program Files\Microsoft\jdk-17.0.19.10-hotspot\`.
- User `ANDROID_HOME` and `ANDROID_SDK_ROOT` were set to `%LOCALAPPDATA%\Android\Sdk`.
- The already-running Codex app may not see the new machine PATH until restart. For commands in the current session, prepend:

```powershell
$env:JAVA_HOME = ([Environment]::GetEnvironmentVariable('JAVA_HOME','Machine')).TrimEnd('\')
$env:ANDROID_HOME = [Environment]::GetEnvironmentVariable('ANDROID_HOME','User')
$env:ANDROID_SDK_ROOT = [Environment]::GetEnvironmentVariable('ANDROID_SDK_ROOT','User')
$env:Path = "$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;$env:Path"
```

- Verified `.\gradlew.bat help` succeeds when the environment is refreshed.
- This clone was shallow and submodules were not initialized yet.

Do not commit generated build outputs from `Source/Android/app/build`.

## MCP Server For Memory Access

`Tools/mcp/` is an MCP server that gives an AI client the running game's memory and CPU state - read and
write values, scan RAM and narrow candidates down, set watchpoints, step. It is the practical way to find
cheats for this fork instead of hand-scraping mirrors.

It drives Dolphin's **existing** GDB stub (`Source/Core/Core/PowerPC/GDBStub.cpp`, off by default via
`GDBPort`) over TCP, so the emulator is unmodified. Keep it that way: a control surface added under
`Source/` would be re-merged against upstream forever, and this fork already pays that cost.

Setup, the tool list and the cheat-finding loop are in `Tools/mcp/README.md`. Three things bite if you have
not read it: enabling `GDBPort` makes a boot **block until a client attaches**, the game then starts
**paused** until `resume`, and the stub is disabled under RetroAchievements hardcore mode.

Run `python Tools/mcp/test_dolphin_mcp.py` after touching it - 28 tests, no device needed.

## Verified Input Axes On The Thor

The Thor's built-in gamepad enumerates as **`Odin Controller`** (`adb shell dumpsys input`). Its Android
motion ranges are exactly:

| Android axis | id | raw evdev | role |
|---|---:|---|---|
| `AXIS_X` / `AXIS_Y` | 0 / 1 | `ABS_X` / `ABS_Y` | left stick |
| `AXIS_Z` / `AXIS_RZ` | 11 / 14 | `ABS_Z` / `ABS_RZ` | right stick |
| `AXIS_HAT_X` / `AXIS_HAT_Y` | 15 / 16 | `ABS_HAT0X` / `ABS_HAT0Y` | d-pad |
| `AXIS_GAS` / `AXIS_BRAKE` | 22 / 23 | `ABS_GAS` / `ABS_BRAKE` | analog triggers |

**There is no `AXIS_LTRIGGER` (17) or `AXIS_RTRIGGER` (18) on this device.** Dolphin names Android axes as
`Axis <Android constant><sign>` (`ConstructAxisName`, `Source/Core/InputCommon/ControllerInterface/Android/`
`Android.cpp`), so a profile binding `Axis 17+`/`Axis 18+` here binds to nothing at all. Both bundled AYN
profiles did exactly that until 2026-08-21, which left the GameCube analog triggers dead - only the digital
`Button L2`/`Button R2` fallbacks worked. They now use `Axis 23+` for L and `Axis 22+` for R.

Left/right on the trigger pair follows the usual Android convention (brake = left, gas = right) and has not
been confirmed by physically pressing them. If L and R come out swapped in game, swap 22 and 23 in
`Data/Sys/Profiles/GCPad/AYN Odin Android GameCube.ini` and the Classic Controller profile.

Every other control name in the bundled AYN profiles was audited against this pad's real capabilities on
2026-08-21 (`getevent -pl` for buttons, `dumpsys input` for axes) and all of them resolve. The trigger axes
were the only dead bindings. The gyro profile's 13 sensor bindings were likewise checked against the names
`DolphinSensorEventListener` actually registers, and all match.

The Android hotkey layer does not use these bindings - it reads `MotionEvent` axes directly.
`AndroidHotkeyManager.rightStickY` takes whichever of `AXIS_RZ`/`AXIS_RY` has the larger magnitude, and since
this pad has no `AXIS_RY` that resolves to `AXIS_RZ`, which is the correct right-stick vertical here.

Rumble: the Thor reports a single vibrator with `mId=0` on SDK 33, so it takes the
`DolphinVibratorManagerPassthrough` path and `Motor 0` is the right binding. It advertises
`AMPLITUDE_CONTROL`, so the fork's strength-scaled rumble is genuinely active rather than falling back to
`DEFAULT_AMPLITUDE`.

## The AYN Thor Is A Shared Device

Several Claude sessions work on emulator forks on this machine at the same time, and they all reach the same
AYN Thor over the same `adb` connection. Treat the device as a contended resource.

- **Never stall waiting for the device.** If the Thor is busy, keep doing code work - reading, editing,
  building, reviewing, writing docs. Blocking on hardware while there is source work left is always wrong.
- **Timings taken while another session is using the device are worthless.** This is not theoretical: an A/B
  of the performance-core affinity setting on 2026-08-21 produced 5347, 1517, 324 and 5408 emulated frames
  over identical 90-second runs, and the last two used the *same* configuration as each other. A 16x spread
  between two identical runs is the other sessions, not the setting. Before trusting any measurement, run the
  same configuration at least twice and throw the whole result away if the repeats disagree.
- **Leave the device as you found it.** `adb shell am force-stop org.dolphinemu.dolphinemu` when finished,
  restore any config you edited (back it up first - `Config/Dolphin.ini` and `Config/GFX.ini` carry the user's
  GPU driver choice and game paths), and delete anything you pushed to `/sdcard` or `/data/local/tmp`.
- Installing the APK is fine and does not disturb another session; running a game does.

**Check for contention properly before any on-device run.** Looking for a foreground activity is not enough -
a competing emulator can be mid-run while its process looks ordinary. The sibling projects on this machine
install as `com.armsx2`, `dev.eden.eden_emulator.nightly`, `net.rpcsx.easy`, `org.vita3k.emulator.debug` and
friends. Check for all of them, and check `logcat` for their output:

```powershell
adb -s <serial> shell "ps -A -o NAME | grep -iE 'armsx2|eden|rpcs|vita3k|azahar|citra|yuzu|cemu|xenia|pcsx|ppsspp|retroarch'"
```

**Another session can force-stop your app mid-run.** On 2026-08-21 a Dolphin run went 60fps for eight
seconds, collapsed to 6fps as `com.armsx2` loaded a PS2 title, and was then killed outright -
`ActivityManager: Force stopping org.dolphinemu.dolphinemu ... from pid 2601`. So a run that ends with the
process gone is **not** evidence of a crash in our build. Always check `logcat` for `forceStopPackage`
before investigating a supposed crash, and re-run when the device is quiet.

Game images live on the SD card at `/storage/2664-21DE/Roms/gc` and `/Roms/wii`, already registered in
Dolphin's library as SAF content URIs. They are **not** under `/storage/emulated/0/Emulation/ROMs`, which is
empty - search the SD card before concluding there is nothing to boot.

`EmulationActivity` is `exported="false"`, so a game cannot be booted with `am start` from adb. Launch
`MainActivity` and drive the grid with `input tap` instead.

## Running The C++ Unit Tests On The Thor

The Android build already produces an aarch64 gtest binary, so the native suite can be run on the real
device - useful whenever build flags or the JIT change, and the only real check available when no game
images are on the device.

**Push the `Sys` directory too.** The binary resolves the Sys path relative to its working directory, and
several tests (`PatchAllowlist.VerifyHashes` in particular) silently compute the wrong answer and fail if it
is missing. A run without `Sys` is not a valid run.

```powershell
$build = Resolve-Path Source/Android/app/.cxx/Release/*/arm64-v8a/Binaries/Tests
llvm-strip -o $env:TEMP/dolphin_tests_arm64 "$build/tests"   # 248MB -> 10MB
adb -s <serial> push $env:TEMP/dolphin_tests_arm64 /data/local/tmp/
adb -s <serial> push "$build/Sys" /data/local/tmp/
adb -s <serial> shell 'chmod 755 /data/local/tmp/dolphin_tests_arm64 && cd /data/local/tmp && ./dolphin_tests_arm64'
adb -s <serial> shell 'rm -rf /data/local/tmp/dolphin_tests_arm64 /data/local/tmp/Sys'
```

Expected on 2026-08-21, on the Thor, with the ARMv8.4 build: **1031 of 1031 pass** in about 8 seconds.

That total includes the five `JitArm64` emitter tests, which assemble and execute JIT output, so a green run
does prove the emitter works on the device. It does **not** prove anything about emulation speed - see the
timing section of `docs/research/arm64-thor-optimization.md`, where this suite failed to detect the ARMv8.4
build change at all because it is the wrong workload for it.

## Verification Checklist

- Run Kotlin/Android formatting for edited Java/Kotlin files using the Dolphin code style from `Source/Android/code-style-java.xml`.
- Build at least `:app:assembleRelease` before claiming the APK is ready for daily Thor testing.
- Install the release package to the AYN Thor with `adb install -r app\build\outputs\apk\release\app-release.apk` or `:app:installRelease`.
- On device, verify mobile grid cover badges, TV/Leanback cards if relevant, and games with no cheats.
- In game, verify save/load hotkeys do not fire repeatedly while held.
- Verify the Select button still works normally when no hotkey combo is completed.
- Verify the right stick still reaches the emulated controller outside the hotkey combo.
- Verify speed toggle switches both ways and does not leave config in an unexpected state.
- Verify rumble with Android system vibration enabled on the Thor; `adb shell settings get system vibrate_on`, `adb shell settings get system haptic_feedback_enabled`, and `adb shell settings get system keyboard_vibration_enabled` should all return `1`.

## Remaining Questions Before Implementation

- ~~If AYN Thor/Odin axis names differ from generic Android `Axis 0/1/11/14/17/18`, confirm with the input
  mapper and update the bundled profiles.~~ **Answered 2026-08-21.** See the input axis section below.
- Decide later whether to add a user-facing "refresh bundled cheat cache" workflow, or keep regeneration as a repo/build-time script.
