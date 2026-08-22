#!/bin/bash
#
# Verifies this fork's Android hotkeys on a connected device, without a human
# needing to hold buttons: controller input is synthesized with sendevent on the
# gamepad's own event node, so the emulator sees ordinary hardware input.
#
# Usage:  Tools/verify-android-hotkeys.sh [adb-serial]
#
# The Thor this fork targets is shared with other emulator projects, and a
# competing session will happily force-stop Dolphin mid-run. Two things follow,
# and both are baked in here: the script refuses to start while another emulator
# is burning CPU, and it prefers evidence that survives being killed - a
# savestate is a file on disk, so it still proves the hotkey fired even if the
# app is gone by the time we look.

# Prevent MingW MSYS from turning the device-side paths below into Windows paths
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

set -u

SERIAL="${1:-}"
ADB="adb"
[ -n "$SERIAL" ] && ADB="adb -s $SERIAL"

PKG=org.dolphinemu.dolphinemu
FILES="/storage/emulated/0/Android/data/$PKG/files"
CFG="$FILES/Config"
STATES="$FILES/StateSaves"
BACKUP=/storage/emulated/0/dolphin_verify_backup
WORK=/sdcard/dolphin_verify

# Evdev codes. BTN_SELECT and BTN_TR are the fork's Select and R1; ABS_RZ is the
# right stick's vertical axis on this pad - see the verified axis table in
# AGENTS.md, which also explains why it is not AXIS_RY.
BTN_SELECT=314
BTN_TR=311
ABS_RZ=5

RIVALS='armsx2|eden_emulator|rpcsx|rpcs3|vita3k|azahar|citra|yuzu|cemu|xenia|pcsx|ppsspp|melon|duckstation|retroarch'

say() { printf '%s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*"; exit 1; }

# -- preflight ---------------------------------------------------------------

$ADB get-state >/dev/null 2>&1 || fail "no device (try: adb devices)"

active=$($ADB shell "
  pids=\$(ps -A -o PID,NAME | grep -iE '$RIVALS' | awk '{print \$1}')
  n=0
  for p in \$pids; do
    a=\$(awk '{print \$14+\$15}' /proc/\$p/stat 2>/dev/null) || continue
    sleep 2
    b=\$(awk '{print \$14+\$15}' /proc/\$p/stat 2>/dev/null) || continue
    [ \$((b-a)) -gt 8 ] && n=\$((n+1))
  done
  echo \$n" | tr -d '\r')

if [ "${active:-0}" != "0" ]; then
    say "SKIP: $active other emulator(s) are using the device."
    say "      Timings and in-game results taken now are worthless, and this run"
    say "      would likely be force-stopped part way through. Try again later."
    exit 2
fi

EVENT_NODE=$($ADB shell "getevent -pl 2>/dev/null | grep -B3 -i 'Odin Controller' | grep -o '/dev/input/event[0-9]*' | head -1" | tr -d '\r')
[ -n "$EVENT_NODE" ] || fail "could not find the gamepad's event node"
say "gamepad: $EVENT_NODE"

# -- run ---------------------------------------------------------------------

$ADB shell "mkdir -p $BACKUP $WORK && cp $CFG/Dolphin.ini $CFG/GFX.ini $BACKUP/ 2>/dev/null"
trap '$ADB shell "am force-stop $PKG; cp $BACKUP/Dolphin.ini $CFG/Dolphin.ini 2>/dev/null; cp $BACKUP/GFX.ini $CFG/GFX.ini 2>/dev/null; rm -rf $BACKUP $WORK" >/dev/null 2>&1' EXIT

STATES_BEFORE=$($ADB shell "ls -1 $STATES 2>/dev/null | wc -l" | tr -d '\r')

# Boot at half speed on purpose. toggleSpeed() flips to 1.0 whenever the current
# speed is not already ~1.0, so the toggle must double the frame rate - a signal
# that does not depend on the device having spare GPU headroom, which a plain
# "did it get faster than 60fps" test would.
$ADB shell "
  sed -i '/^EmulationSpeed *=/d' $CFG/Dolphin.ini
  sed -i '/^\[Core\]/a EmulationSpeed = 0.5' $CFG/Dolphin.ini
  grep -q '^LogRenderTimeToFile' $CFG/GFX.ini || sed -i '/^\[Settings\]/a LogRenderTimeToFile = True' $CFG/GFX.ini
  rm -f $FILES/Logs/vblank_times.txt
"

DEVICE_OUT=$($ADB shell "
set -u
DEV=$EVENT_NODE
syn()  { sendevent \$DEV 0 0 0; }
key()  { sendevent \$DEV 1 \$1 \$2; syn; }
axis() { sendevent \$DEV 3 $ABS_RZ \$1; syn; }

am force-stop $PKG
am start -n $PKG/.ui.main.MainActivity >/dev/null 2>&1
sleep 12
# Boot the first game in the grid.
input tap 479 517
sleep 40
# The in-game menu is shown on boot and pauses emulation, so dismiss it before
# injecting anything - while it is up, EmulationActivity deliberately bypasses
# the hotkey manager entirely.
input tap 200 540
sleep 4

frames() { wc -l < $FILES/Logs/vblank_times.txt 2>/dev/null || echo 0; }

echo '-- speed toggle: measuring against the 50% baseline --'
a=\$(frames); sleep 12; b=\$(frames); base=\$((b-a))
echo \"baseline frames in 12s: \$base\"
key $BTN_SELECT 1; sleep 0.3; key $BTN_TR 1; sleep 0.2; key $BTN_TR 0; sleep 0.3; key $BTN_SELECT 0
sleep 2
a=\$(frames); sleep 12; b=\$(frames); fast=\$((b-a))
echo \"SPEEDRESULT \$base \$fast\"
# Toggle back so the quick save below happens at normal speed.
key $BTN_SELECT 1; sleep 0.3; key $BTN_TR 1; sleep 0.2; key $BTN_TR 0; sleep 0.3; key $BTN_SELECT 0
sleep 2

echo '-- quick save: Select + right stick down --'
key $BTN_SELECT 1; sleep 0.4; axis 32767; sleep 0.6; axis 0; sleep 0.3; key $BTN_SELECT 0
sleep 6

echo '-- quick load: Select + right stick up --'
key $BTN_SELECT 1; sleep 0.4; axis -32767; sleep 0.6; axis 0; sleep 0.3; key $BTN_SELECT 0
sleep 6
")
printf '%s\n' "$DEVICE_OUT"

STATES_AFTER=$($ADB shell "ls -1 $STATES 2>/dev/null | wc -l" | tr -d '\r')
STILL_UP=$($ADB shell "ps -A -o NAME | grep -cx $PKG" | tr -d '\r')
KILLED=$($ADB shell "logcat -d -t 400 | grep -c 'forceStopPackage: $PKG'" | tr -d '\r')

SPEED_LINE=$(printf '%s\n' "$DEVICE_OUT" | grep SPEEDRESULT | tail -1)
BASE_FRAMES=$(echo "$SPEED_LINE" | awk '{print $2}')
FAST_FRAMES=$(echo "$SPEED_LINE" | awk '{print $3}')

say ""
say "savestates before: ${STATES_BEFORE:-0}   after: ${STATES_AFTER:-0}"
say "app still running: $STILL_UP"
say "speed toggle: ${BASE_FRAMES:-?} frames at 50%, ${FAST_FRAMES:-?} after toggling"

# One forceStop is our own at the start of the run; more than that came from
# somewhere else.
if [ "${KILLED:-0}" -gt 1 ]; then
    say ""
    say "INCONCLUSIVE: another session force-stopped Dolphin during the run."
    say "              Re-run when the device is genuinely idle."
    exit 2
fi

RESULT=0

say ""
if [ -n "${BASE_FRAMES:-}" ] && [ "${BASE_FRAMES:-0}" -gt 50 ] 2>/dev/null; then
    if [ "$((FAST_FRAMES * 100 / BASE_FRAMES))" -ge 150 ]; then
        say "PASS: the speed toggle took the game from 50% to full speed."
    else
        say "FAIL: the speed toggle did not change the frame rate."
        RESULT=1
    fi
else
    say "INCONCLUSIVE: too few baseline frames to judge the speed toggle."
    say "              Did a game actually boot, and was the menu dismissed?"
fi

if [ "${STATES_AFTER:-0}" -gt "${STATES_BEFORE:-0}" ]; then
    say "PASS: the quick-save hotkey produced a savestate."
    say "      Quick load leaves no durable trace; that it did not crash the app"
    say "      is the only automatic signal for it."
    exit $RESULT
fi

say ""
say "FAIL: no savestate appeared, so the quick-save hotkey did not fire."
say "      Check that a game actually booted - the tap coordinates assume the"
say "      first card of the grid at 1080x1920."
exit 1
