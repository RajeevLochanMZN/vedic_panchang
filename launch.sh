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

# Used by restore_desktop() below.
LABWC_USER_AUTOSTART="${LABWC_USER_AUTOSTART:-$HOME/.config/labwc/autostart}"
SYSTEM_AUTOSTART="${SYSTEM_AUTOSTART:-/etc/xdg/labwc/autostart}"
AUTOSTART_MARKER="Written by VedicGhadi setup.sh"   # same text setup.sh writes

cd "$(dirname "$(readlink -f "$0")")" || exit 1

# Only ever one copy: the app owns the GPIO pins, so a second copy would crash.
exec 9>"$KIOSK_LOCK"
flock -n 9 || { echo "launch.sh: already running -- not starting a second copy."; exit 0; }

# The app runs through the desktop's X11 compatibility layer (this is how it
# was tested on the Pi); naming it explicitly avoids any guesswork.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export DISPLAY="${DISPLAY:-:0}"

sleep "$START_DELAY"

# In the silent-kiosk start (see setup.sh) the normal desktop -- wallpaper and
# taskbar -- is deliberately NOT running, so if the clock quits there would be
# nothing but a black screen. This brings the desktop back in that case, by
# running the same system script that normally starts it. It does nothing if
# the silent start isn't in use, or if a desktop is already running (so it can
# never start a second one on top of yours).
restore_desktop() {
    grep -q "$AUTOSTART_MARKER" "$LABWC_USER_AUTOSTART" 2>/dev/null || return 0
    pgrep -x wf-panel-pi >/dev/null 2>&1 && return 0
    [ -r "$SYSTEM_AUTOSTART" ] || return 0
    echo "$(date '+%F %T') clock is not running -- bringing back the normal desktop" >> "$KIOSK_LOG"
    # 9>&- : do not pass our lock to the desktop programs
    setsid sh "$SYSTEM_AUTOSTART" 9>&- >/dev/null 2>&1 &
}

# Keep the kiosk alive: if the app crashes, start it again -- but give up
# after 5 quick crashes in a row so a real bug can't loop forever.
quick_crashes=0
while true; do
    started=$(date +%s)
    "$PYTHON" "$KIOSK_ENTRY" >> "$KIOSK_LOG" 2>&1
    code=$?

    # Stopped on purpose (Ctrl+C / SIGTERM -- e.g. at shutdown, or `pkill`):
    # stay stopped. A clean exit (code 0, e.g. the window was closed): stay
    # stopped too, but make sure there is a desktop to look at.
    case "$code" in
        130|143) exit 0 ;;
        0)       restore_desktop; exit 0 ;;
    esac

    runtime=$(( $(date +%s) - started ))
    if [ "$runtime" -lt 20 ]; then quick_crashes=$((quick_crashes + 1)); else quick_crashes=0; fi
    echo "$(date '+%F %T') app exited with code $code after ${runtime}s (quick crashes in a row: $quick_crashes)" >> "$KIOSK_LOG"
    if [ "$quick_crashes" -ge 5 ]; then
        echo "$(date '+%F %T') giving up after 5 quick crashes in a row" >> "$KIOSK_LOG"
        restore_desktop
        exit 1
    fi
    sleep "$RESTART_DELAY"
done
