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
- GPU driver setup should stay easy for Thor users: the Android GPU Driver menu fetches Turnip ZIP assets from `K11MCH1/AdrenoToolsDrivers`, marks the newest standard Turnip ZIP as recommended, and keeps manual local ZIP install available for variants.
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
- Native input bridge:
  - `Source/Android/app/src/main/java/org/dolphinemu/dolphinemu/features/input/model/ControllerInterface.kt`
  - `Source/Core/InputCommon/ControllerInterface/Android/Android.cpp`
  - Android rumble/haptics also pass through these files plus `DolphinVibratorManager*.kt`.
- Android-bundled controller profiles:
  - `Data/Sys/Profiles/GCPad/AYN Odin Android GameCube.ini`
  - `Data/Sys/Profiles/Wiimote/AYN Odin Android Classic Controller.ini`
  - `Data/Sys/Profiles/Wiimote/AYN Odin Android Nunchuk.ini`
  - Android build configuration copies `Data/Sys` into the ignored/generated `Source/Android/app/src/main/assets/Sys` folder.
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

- If AYN Thor/Odin axis names differ from generic Android `Axis 0/1/11/14/17/18`, confirm with the input mapper and update the bundled profiles.
- Decide later whether to add a user-facing "refresh bundled cheat cache" workflow, or keep regeneration as a repo/build-time script.
