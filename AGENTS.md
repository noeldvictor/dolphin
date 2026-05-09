# AGENTS.md

## Scope

These instructions apply to the whole repository.

## Project Brief

This fork is being prepared for Android-focused Dolphin work, with an AYN Thor handheld as the main target test device. The immediate feature goals are:

- Show a visible badge on game covers when cheats are available for that game.
- Add an Android hotkey layer for easy savestate actions from the built-in/controller inputs.
- Add a speed toggle hotkey.
- Build an Android APK and install it to the AYN Thor over USB.

Current product decisions from 2026-05-09:

- Prefer bundling/downloading cheats for all supported games into the repo, along with covers if practical. Before committing third-party data, verify licensing, attribution, and repo-size impact.
- Cheat badges should be small and visible on the mobile game grid and TV/Leanback cards.
- Save/load defaults should be Android-editable hotkeys.
- Initial save/load default: Select + right stick up/down, likely mapped to quick save/load unless changed.
- Speed toggle default: Select + R.
- Users should be able to choose the toggle speed/fast-forward percentage. Default target is 200%.
- APK target for now is a debug build installed to the user's AYN Thor.

The repository remote should use SSH:

```powershell
git remote set-url origin git@github.com:noeldvictor/dolphin.git
```

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

For cover cheat badges, keep the work lightweight. Avoid loading full cheat details on the UI thread for every game card if possible. Prefer a small availability provider/cache keyed by `gameId` plus `revision`, and update the mobile and TV card surfaces consistently. If a bundled cheat index is added, derive badge state from that index plus any user-local cheats, not from synchronous per-card cheat parsing.

For Android hotkeys, prefer a small `EmulationActivity` helper that sees key and motion events before they are passed to `ControllerInterface`. It should be edge-triggered and debounced so holding a combo does not spam savestates. It should only consume events when an exact hotkey combo fires; otherwise normal controller input should keep flowing to the emulator. The requested default mapping is Select plus right stick up/down for save/load and Select + R for speed toggle, but confirm the exact Android key/axis codes on the AYN Thor before hardcoding. Right-stick axes can vary by device.

For speed toggle, prefer toggling between normal speed (`FloatSetting.MAIN_EMULATION_SPEED = 1.0f`) and a user-configurable fast-forward percentage. Default fast-forward target is 200% (`2.0f`). If changing runtime config directly, make sure the core sees the updated value and the Settings object is saved only when persistence is intended.

## Build And Deploy

Use the Android project from `Source/Android`.

```powershell
git submodule update --init --recursive
cd Source/Android
.\gradlew.bat :app:assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

Or use Gradle's install task once the device is visible:

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
- Build at least `:app:assembleDebug` before claiming the APK is ready.
- Install to the AYN Thor with `adb install -r` or `:app:installDebug`.
- On device, verify mobile grid cover badges, TV/Leanback cards if relevant, and games with no cheats.
- In game, verify save/load hotkeys do not fire repeatedly while held.
- Verify the Select button still works normally when no hotkey combo is completed.
- Verify the right stick still reaches the emulated controller outside the hotkey combo.
- Verify speed toggle switches both ways and does not leave config in an unexpected state.

## Remaining Questions Before Implementation

- Which slot should Select + right stick up/down use: quick slot `9`, slot 1, or current/last selected slot?
- Should speed toggle be session-only during emulation, or should the selected fast-forward percentage persist into Dolphin settings?
- What source should be used for bundled cheats and covers, and what licensing/attribution files are required?
