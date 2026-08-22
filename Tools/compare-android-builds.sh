#!/bin/bash
#
# Compares the emulation throughput of two APKs by installing them alternately
# and measuring each, so the answer does not depend on which was tested first.
#
# Usage:  Tools/compare-android-builds.sh <a.apk> <b.apk> [rounds] [serial]
#
# Interleaving is the point. Measuring a block of A and then a block of B lets
# the device warm up during the run and hands the second build a slower score
# that has nothing to do with the build. Alternating spreads that across both.
#
# Each measurement is delegated to benchmark-android-throughput.sh, which
# refuses to run while another emulator is using the device, retries a failed
# boot, and discards a run that another session force-stopped.

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

set -u

APK_A="${1:-}"
APK_B="${2:-}"
ROUNDS="${3:-2}"
SERIAL="${4:-}"

HERE="$(cd "$(dirname "$0")" && pwd)"
MEASURE="$HERE/benchmark-android-throughput.sh"

say() { printf '%s\n' "$*"; }

if [ -z "$APK_A" ] || [ -z "$APK_B" ]; then
    say "usage: $0 <a.apk> <b.apk> [rounds] [serial]"
    exit 1
fi
for apk in "$APK_A" "$APK_B"; do
    [ -f "$apk" ] || { say "FAIL: no such file: $apk"; exit 1; }
done

ADB="adb"
[ -n "$SERIAL" ] && ADB="adb -s $SERIAL"

A_NAME=$(basename "$APK_A")
B_NAME=$(basename "$APK_B")
A_RESULTS=""
B_RESULTS=""

measure() {
    # Runs one measurement, echoes its output so the caller can watch, and
    # returns just the frame count from the summary line.
    local label="$1" output
    output=$("$MEASURE" "$SERIAL" 1 "$label" 2>&1)
    printf '%s\n' "$output" >&2
    printf '%s\n' "$output" | grep "median" | awk '{print $NF}'
}

for round in $(seq 1 "$ROUNDS"); do
    for side in A B; do
        if [ "$side" = "A" ]; then apk="$APK_A"; name="$A_NAME"; else apk="$APK_B"; name="$B_NAME"; fi

        say ""
        say "== round $round, installing $name =="
        $ADB install -r "$apk" >/dev/null 2>&1 || { say "FAIL: could not install $apk"; exit 1; }

        frames=$(measure "$name")
        if [ -z "$frames" ]; then
            say "ABORT: measurement did not complete (device busy, or no valid run)."
            exit 2
        fi

        if [ "$side" = "A" ]; then A_RESULTS="$A_RESULTS $frames"; else B_RESULTS="$B_RESULTS $frames"; fi
    done
done

median() {
    printf '%s\n' $1 | sort -n | awk '{v[NR]=$1} END {print (NR%2) ? v[(NR+1)/2] : int((v[NR/2]+v[NR/2+1])/2)}'
}

A_MED=$(median "$A_RESULTS")
B_MED=$(median "$B_RESULTS")

say ""
say "$A_NAME: $A_RESULTS   median $A_MED"
say "$B_NAME: $B_RESULTS   median $B_MED"

if [ "${A_MED:-0}" -le 0 ]; then
    say "INCONCLUSIVE: no valid measurements for $A_NAME"
    exit 2
fi

DELTA=$(( (B_MED - A_MED) * 100 / A_MED ))
say "difference: ${DELTA}% for $B_NAME against $A_NAME"

# Run to run spread on this device is around 1%, so anything under a couple of
# percent is not a result.
if [ "$DELTA" -ge 2 ]; then
    say "$B_NAME is faster."
elif [ "$DELTA" -le -2 ]; then
    say "$B_NAME is slower."
else
    say "No meaningful difference - inside the run to run spread."
fi
