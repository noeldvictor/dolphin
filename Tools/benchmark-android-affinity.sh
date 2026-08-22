#!/bin/bash
#
# Measures whether pinning the emulation threads to the performance cores
# actually helps, by booting the same game with the setting off and on and
# comparing throughput.
#
# Usage:  Tools/benchmark-android-affinity.sh [adb-serial] [iterations]
#
# Two design choices make the numbers mean something:
#
#   * Emulation runs UNCAPPED (EmulationSpeed = 0), so the frame rate is a raw
#     throughput measure rather than a flat 60 that hides every difference.
#   * Runs are INTERLEAVED (off, on, off, on...) rather than grouped, so a
#     thermal drift part way through cannot be mistaken for an effect.
#
# It refuses to run while another emulator is using the device, and treats a
# run that got force-stopped by another session as spoiled rather than as data.
# That is not paranoia: three earlier attempts at this measurement were
# invalidated exactly that way.

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

set -u

SERIAL="${1:-}"
ITERATIONS="${2:-2}"
ADB="adb"
[ -n "$SERIAL" ] && ADB="adb -s $SERIAL"

PKG=org.dolphinemu.dolphinemu
FILES="/storage/emulated/0/Android/data/$PKG/files"
CFG="$FILES/Config"
BACKUP=/storage/emulated/0/dolphin_bench_backup
MEASURE_SECONDS=20
# Below this, the run did not boot a game rather than running one slowly.
MIN_VALID_FRAMES=200

RIVALS='armsx2|eden_emulator|rpcsx|rpcs3|vita3k|azahar|citra|yuzu|cemu|xenia|pcsx|ppsspp|melon|duckstation|retroarch'

say() { printf '%s\n' "$*"; }

$ADB get-state >/dev/null 2>&1 || { say "FAIL: no device"; exit 1; }

busy() {
    $ADB shell "
      pids=\$(ps -A -o PID,NAME | grep -iE '$RIVALS' | awk '{print \$1}')
      n=0
      for p in \$pids; do
        a=\$(awk '{print \$14+\$15}' /proc/\$p/stat 2>/dev/null) || continue
        sleep 2
        b=\$(awk '{print \$14+\$15}' /proc/\$p/stat 2>/dev/null) || continue
        [ \$((b-a)) -gt 8 ] && n=\$((n+1))
      done
      echo \$n" | tr -d '\r' | tail -1
}

if [ "$(busy)" != "0" ]; then
    say "SKIP: another emulator is using the device; any timing taken now is noise."
    exit 2
fi

$ADB shell "mkdir -p $BACKUP && cp $CFG/Dolphin.ini $CFG/GFX.ini $BACKUP/ 2>/dev/null"
trap '$ADB shell "am force-stop $PKG; cp $BACKUP/Dolphin.ini $CFG/Dolphin.ini 2>/dev/null; cp $BACKUP/GFX.ini $CFG/GFX.ini 2>/dev/null; rm -rf $BACKUP" >/dev/null 2>&1' EXIT

run_once() {
    local affinity="$1"
    $ADB shell "
      sed -i '/^EmulationSpeed *=/d;/^PerformanceCoreAffinity *=/d' $CFG/Dolphin.ini
      sed -i '/^\[Core\]/a EmulationSpeed = 0' $CFG/Dolphin.ini
      sed -i '/^\[Core\]/a PerformanceCoreAffinity = $affinity' $CFG/Dolphin.ini
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
    " | tr -d '\r' | tail -1
}

spoiled() {
    local n
    n=$($ADB shell "logcat -d -t 300 | grep -c 'forceStopPackage: $PKG'" | tr -d '\r')
    # Our own start and end force-stops account for two.
    [ "${n:-0}" -gt 2 ]
}

OFF_RESULTS=""
ON_RESULTS=""

for i in $(seq 1 "$ITERATIONS"); do
    for affinity in False True; do
        $ADB logcat -c >/dev/null 2>&1
        frames=$(run_once "$affinity")
        if spoiled; then
            say "SPOILED: another session force-stopped Dolphin during run $i/$affinity."
            say "         Discarding the whole benchmark rather than reporting noise."
            exit 2
        fi

        # A run with (almost) no frames did not measure a slow emulator, it
        # failed to boot one. Folding that into the median would invent an
        # enormous difference out of nothing, so retry instead of recording it.
        attempt=1
        while [ "${frames:-0}" -lt "$MIN_VALID_FRAMES" ] && [ "$attempt" -lt 3 ]; do
            say "run $i, affinity=$affinity: only ${frames:-0} frames - the game did not boot, retrying"
            attempt=$((attempt + 1))
            $ADB logcat -c >/dev/null 2>&1
            frames=$(run_once "$affinity")
        done
        if [ "${frames:-0}" -lt "$MIN_VALID_FRAMES" ]; then
            say "FAILED: could not get a valid run for affinity=$affinity after $attempt attempts."
            say "        Reporting nothing rather than half a comparison."
            exit 2
        fi

        say "run $i, affinity=$affinity: $frames frames in ${MEASURE_SECONDS}s"
        if [ "$affinity" = "False" ]; then
            OFF_RESULTS="$OFF_RESULTS $frames"
        else
            ON_RESULTS="$ON_RESULTS $frames"
        fi
    done
done

median() {
    printf '%s\n' $1 | sort -n | awk '{v[NR]=$1} END {print (NR%2) ? v[(NR+1)/2] : int((v[NR/2]+v[NR/2+1])/2)}'
}

OFF_MED=$(median "$OFF_RESULTS")
ON_MED=$(median "$ON_RESULTS")

say ""
say "affinity off: $OFF_RESULTS   median $OFF_MED"
say "affinity on : $ON_RESULTS   median $ON_MED"

if [ "${OFF_MED:-0}" -le 0 ]; then
    say "INCONCLUSIVE: no frames measured; did a game boot?"
    exit 2
fi

DELTA=$(( (ON_MED - OFF_MED) * 100 / OFF_MED ))
say "difference: ${DELTA}% with pinning on"

if [ "$DELTA" -ge 5 ]; then
    say "Pinning helps on this title. Worth enabling."
elif [ "$DELTA" -le -5 ]; then
    say "Pinning HURTS on this title. Leave it off."
else
    say "No meaningful difference. Leave the default off - a setting that does"
    say "nothing is worse than no setting, because it invites fiddling."
fi
