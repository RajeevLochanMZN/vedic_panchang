#!/usr/bin/env bash
# tools/apply_display_mode.sh -- sets the screen resolution BEFORE the clock starts, if this
# device needs it.  Called from ~/.config/labwc/autostart (installed by pi_display_fix.sh).
#
# The setting lives in ONE small per-device file, NOT in the image and NOT in git:
#       ~/.config/vedicghadi/display_mode.txt
#   auto        (default) do nothing: the screen's own preferred mode is used.  Right for almost
#               every HDMI panel / TV, so ONE image works on all of them.
#   1440x900    force this size (for odd screens, e.g. a VGA converter that reports a wrong
#               preferred mode).  Of the refresh rates offered, the one closest to 60 Hz is used.
# If the wanted size is not offered by the screen, nothing is changed.
#
# Change it on a device:   echo 1920x1080 > ~/.config/vedicghadi/display_mode.txt ; sudo reboot
#                          echo auto      > ~/.config/vedicghadi/display_mode.txt ; sudo reboot
# See what the screen offers:   WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) wlr-randr

CFGF="${VEDICGHADI_DISPLAY_FILE:-$HOME/.config/vedicghadi/display_mode.txt}"
[ -f "$CFGF" ] || exit 0
WANT="$(tr -d ' \r\n' < "$CFGF")"
if [ -z "$WANT" ] || [ "$WANT" = "auto" ]; then exit 0; fi

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

LIST="$(wlr-randr 2>/dev/null)" || { echo "[display] wlr-randr not available -- mode left as it is"; exit 0; }
OUT="$(printf '%s\n' "$LIST" | awk '/^[^ ]/ { print $1; exit }')"
# the offered refresh rate closest to 60 Hz for the wanted size
RATE="$(printf '%s\n' "$LIST" | awk -v want="$WANT" '
  $1 == want { r = $3 + 0; d = (r > 60 ? r - 60 : 60 - r);
               if (best == "" || d < bd) { best = $3; bd = d } }
  END { print best }')"

if [ -z "$OUT" ] || [ -z "$RATE" ]; then
  echo "[display] $WANT is not offered by this screen -- mode left as it is"
  exit 0
fi
wlr-randr --output "$OUT" --mode "${WANT}@${RATE}Hz" || wlr-randr --output "$OUT" --mode "$WANT" \
  || echo "[display] could not set $WANT -- mode left as it is"
exit 0
