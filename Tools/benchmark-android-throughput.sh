#!/bin/bash
#
# Measures the emulation throughput of whatever Dolphin build is installed, so
# two builds can be compared: LTO against no LTO, one GPU driver against
# another, a JIT change against its parent.
#
# Usage:  Tools/benchmark-android-throughput.sh [adb-serial] [runs] [label]
#
# Emulation runs UNCAPPED (EmulationSpeed = 0), so the frame count is raw
# throughput rather than a flat 60 that would hide any difference. It refuses to
# run while another emulator is using the device, retries a run that failed to
# boot rather than recording a zero, and restores the config afterwards.
#
# Comparing two builds:
#     adb install -r build-a.apk && Tools/benchmark-android-throughput.sh "" 3 A
#     adb install -r build-b.apk && Tools/benchmark-android-throughput.sh "" 3 B
#
# Interleave those if you can - back to back runs of one build then the other
# let thermal drift masquerade as a difference.

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

set -u

SERIAL="${1:-}"
RUNS="${2:-3}"
LABEL="${3:-build}"
ADB="adb"
[ -n "$SERIAL" ] && ADB="adb -s $SERIAL"

PKG=org.dolphinemu.dolphinemu
FILES="/storage/emulated/0/Android/data/$PKG/files"
CFG="$FILES/Config"
BACKUP=/storage/emulated/0/dolphin_tp_backup
MEASURE_SECONDS=20
MIN_VALID_FRAMES=200

RIVALS='armsx2|eden_emulator|rpcsx|rpcs3|vita3k|azahar|citra|yuzu|cemu|xenia|pcsx|ppsspp|melon|duckstation|retroarch'

say() { printf '%s\n' "$*"; }

$ADB get-state >/dev/null 2>&1 || { say "FAIL: no device"; exit 1; }

busy=$($ADB shell "
  pids=\$(ps -A -o PID,NAME | grep -iE '$RIVALS' | awk '{print \$1}')
  n=0
  for p in \$pids; do
    a=\$(awk '{print \$14+\$15}' /proc/\$p/stat 2>/dev/null) || continue
    sleep 2
    b=\$(awk '{print \$14+\$15}' /proc/\$p/stat 2>/dev/null) || continue
    [ \$((b-a)) -gt 8 ] && n=\$((n+1))
  done
  echo \$n" | tr -d '\r' | tail -1)

if [ "${busy:-0}" != "0" ]; then
    say "SKIP: another emulator is using the device; any timing taken now is noise."
    exit 2
fi

$ADB shell "mkdir -p $BACKUP && cp $CFG/Dolphin.ini $CFG/GFX.ini $BACKUP/ 2>/dev/null"
trap '$ADB shell "am force-stop $PKG; cp $BACKUP/Dolphin.ini $CFG/Dolphin.ini 2>/dev/null; cp $BACKUP/GFX.ini $CFG/GFX.ini 2>/dev/null; rm -rf $BACKUP" >/dev/null 2>&1' EXIT

run_once() {
    $ADB shell "
      sed -i '/^EmulationSpeed *=/d' $CFG/Dolphin.ini
      sed -i '/^\[Core\]/a EmulationSpeed = 0' $CFG/Dolphin.ini
      grep -q '^LogRenderTimeToFile' $CFG/GFX.ini || sed -i '/^\[Settings\]/a LogRenderTimeToFile = True' $CFG/GFX.ini
      rm -f $FILES/Logs/vblank_times.txt
      am force-stop $PKG
      am start -n $PKG/.ui.main.MainActivity >/dev/null 2>&1
      sleep 12
      input tap 479 517
      sleep 40
      input tap 200 540
      sleep 5
      a=\$(wc -l < $FILES/Logs/vblank_times.txt 2>/dev/null || echo 0)
      sleep $MEASURE_SECONDS
      b=\$(wc -l < $FILES/Logs/vblank_times.txt 2>/dev/null || echo 0)
      echo \$((b-a))
      am force-stop $PKG
    " 2>/dev/null | tr -d '\r' | tail -1
}

RESULTS=""
for i in $(seq 1 "$RUNS"); do
    $ADB logcat -c >/dev/null 2>&1
    frames=$(run_once)

    attempt=1
    while [ "${frames:-0}" -lt "$MIN_VALID_FRAMES" ] && [ "$attempt" -lt 3 ]; do
        say "run $i: only ${frames:-0} frames - the game did not boot, retrying"
        attempt=$((attempt + 1))
        frames=$(run_once)
    done
    if [ "${frames:-0}" -lt "$MIN_VALID_FRAMES" ]; then
        say "FAILED: no valid run after $attempt attempts. Reporting nothing."
        exit 2
    fi

    killed=$($ADB shell "logcat -d -t 300 | grep -c 'forceStopPackage: $PKG'" | tr -d '\r')
    if [ "${killed:-0}" -gt 2 ]; then
        say "SPOILED: another session force-stopped Dolphin during run $i. Discarding."
        exit 2
    fi

    say "$LABEL run $i: $frames frames in ${MEASURE_SECONDS}s"
    RESULTS="$RESULTS $frames"
done

MEDIAN=$(printf '%s\n' $RESULTS | sort -n | awk '{v[NR]=$1} END {print (NR%2) ? v[(NR+1)/2] : int((v[NR/2]+v[NR/2+1])/2)}')
say ""
say "$LABEL: $RESULTS   median $MEDIAN"
