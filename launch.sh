#!/usr/bin/env bash
# launch.sh -- starts the Vedic Ghadi kiosk app.
#
# >>> THIS IS THE ONE PLACE that decides which page/variant this kiosk runs. <<<
# The auto-start entry (made by setup.sh) always runs THIS script, and this
# script runs the file named on the KIOSK_ENTRY line below. To switch the kiosk
# to a different main page later (e.g. a Kashi Vishwanath variant), change that
# one line and reboot -- nothing else needs touching. To try another entry
# once, without editing anything:
#       KIOSK_ENTRY=ui/some_other_page.py ./launch.sh
KIOSK_ENTRY="${KIOSK_ENTRY:-ui/main_window_hi.py}"

# Optional overrides -- the defaults are right for the real kiosk.
PYTHON="${PYTHON:-venv/bin/python}"
KIOSK_LOG="${KIOSK_LOG:-/dev/shm/vedicghadi.log}"      # /dev/shm lives in RAM: no SD-card writes
KIOSK_LOCK="${KIOSK_LOCK:-/dev/shm/vedicghadi.lock}"
START_DELAY="${KIOSK_START_DELAY:-2}"                  # let the desktop finish starting up
RESTART_DELAY="${KIOSK_RESTART_DELAY:-3}"

cd "$(dirname "$(readlink -f "$0")")" || exit 1

# Only ever one copy: the app owns the GPIO pins, so a second copy would crash.
exec 9>"$KIOSK_LOCK"
flock -n 9 || { echo "launch.sh: already running -- not starting a second copy."; exit 0; }

# The app runs through the desktop's X11 compatibility layer (this is how it
# was tested on the Pi); naming it explicitly avoids any guesswork.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export DISPLAY="${DISPLAY:-:0}"

sleep "$START_DELAY"

# Keep the kiosk alive: if the app crashes, start it again -- but give up
# after 5 quick crashes in a row so a real bug can't loop forever.
quick_crashes=0
while true; do
    started=$(date +%s)
    "$PYTHON" "$KIOSK_ENTRY" >> "$KIOSK_LOG" 2>&1
    code=$?

    # Clean exit, or stopped on purpose (Ctrl+C / SIGTERM -- e.g. at shutdown,
    # or `pkill`): stay stopped.
    case "$code" in 0|130|143) exit 0 ;; esac

    runtime=$(( $(date +%s) - started ))
    if [ "$runtime" -lt 20 ]; then quick_crashes=$((quick_crashes + 1)); else quick_crashes=0; fi
    echo "$(date '+%F %T') app exited with code $code after ${runtime}s (quick crashes in a row: $quick_crashes)" >> "$KIOSK_LOG"
    if [ "$quick_crashes" -ge 5 ]; then
        echo "$(date '+%F %T') giving up after 5 quick crashes in a row" >> "$KIOSK_LOG"
        exit 1
    fi
    sleep "$RESTART_DELAY"
done
