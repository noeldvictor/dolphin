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

$ADB shell "
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

echo '-- quick save: Select + right stick down --'
key $BTN_SELECT 1; sleep 0.4; axis 32767; sleep 0.6; axis 0; sleep 0.3; key $BTN_SELECT 0
sleep 6

echo '-- speed toggle: Select + R1, twice --'
key $BTN_SELECT 1; sleep 0.3; key $BTN_TR 1; sleep 0.2; key $BTN_TR 0; sleep 0.3; key $BTN_SELECT 0
sleep 3
key $BTN_SELECT 1; sleep 0.3; key $BTN_TR 1; sleep 0.2; key $BTN_TR 0; sleep 0.3; key $BTN_SELECT 0
sleep 2

echo '-- quick load: Select + right stick up --'
key $BTN_SELECT 1; sleep 0.4; axis -32767; sleep 0.6; axis 0; sleep 0.3; key $BTN_SELECT 0
sleep 6
"

STATES_AFTER=$($ADB shell "ls -1 $STATES 2>/dev/null | wc -l" | tr -d '\r')
STILL_UP=$($ADB shell "ps -A -o NAME | grep -cx $PKG" | tr -d '\r')
KILLED=$($ADB shell "logcat -d -t 400 | grep -c 'forceStopPackage: $PKG'" | tr -d '\r')

say ""
say "savestates before: ${STATES_BEFORE:-0}   after: ${STATES_AFTER:-0}"
say "app still running: $STILL_UP"

# One forceStop is our own at the start of the run; more than that came from
# somewhere else.
if [ "${KILLED:-0}" -gt 1 ]; then
    say ""
    say "INCONCLUSIVE: another session force-stopped Dolphin during the run."
    say "              Re-run when the device is genuinely idle."
    exit 2
fi

if [ "${STATES_AFTER:-0}" -gt "${STATES_BEFORE:-0}" ]; then
    say ""
    say "PASS: the quick-save hotkey produced a savestate."
    say "      Quick load and the speed toggle leave no durable trace, so check"
    say "      the on-screen FPS by hand if you need those confirmed."
    exit 0
fi

say ""
say "FAIL: no savestate appeared, so the quick-save hotkey did not fire."
say "      Check that a game actually booted - the tap coordinates assume the"
say "      first card of the grid at 1080x1920."
exit 1
