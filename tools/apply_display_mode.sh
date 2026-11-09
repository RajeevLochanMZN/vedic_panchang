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
# It also ROTATES the screen, if this device needs it (e.g. Pi 2: the 7-inch panel used upright).
# That setting is a second per-device file, also outside git:
#       ~/.config/vedicghadi/screen_rotation.txt
#   normal      (default) no rotation
#   90 | 270    quarter turn, one way or the other (try the other one if the picture is upside down)
#   180         upside down
# The clock then sees a 480x800 screen and picks its PORTRAIT dial page by itself.
# Change it with:   bash tools/set_display.sh rotate 90      (then sudo reboot)
#
# Change it on a device:   echo 1920x1080 > ~/.config/vedicghadi/display_mode.txt ; sudo reboot
#                          echo auto      > ~/.config/vedicghadi/display_mode.txt ; sudo reboot
# See what the screen offers:   WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) wlr-randr

CFGF="${VEDICGHADI_DISPLAY_FILE:-$HOME/.config/vedicghadi/display_mode.txt}"
ROTF="${VEDICGHADI_ROTATION_FILE:-$HOME/.config/vedicghadi/screen_rotation.txt}"

WANT=""
[ -f "$CFGF" ] && WANT="$(tr -d ' \r\n' < "$CFGF")"
[ "$WANT" = "auto" ] && WANT=""

ROT=""
[ -f "$ROTF" ] && ROT="$(tr -d ' \r\n' < "$ROTF")"
case "$ROT" in
  ""|auto|normal|0) ROT="" ;;
  90|180|270) ;;
  *) echo "[display] screen_rotation.txt: '$ROT' is not normal, 90, 180 or 270 -- rotation ignored"; ROT="" ;;
esac

# nothing wanted -> do nothing (the usual case)
if [ -z "$WANT" ] && [ -z "$ROT" ]; then exit 0; fi

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

LIST="$(wlr-randr 2>/dev/null)" || { echo "[display] wlr-randr not available -- screen left as it is"; exit 0; }
OUT="$(printf '%s\n' "$LIST" | awk '/^[^ ]/ { print $1; exit }')"
if [ -z "$OUT" ]; then
  echo "[display] no screen found by wlr-randr -- screen left as it is"
  exit 0
fi

# 1. the mode: the offered refresh rate closest to 60 Hz for the wanted size
if [ -n "$WANT" ]; then
  RATE="$(printf '%s\n' "$LIST" | awk -v want="$WANT" '
    $1 == want { r = $3 + 0; d = (r > 60 ? r - 60 : 60 - r);
                 if (best == "" || d < bd) { best = $3; bd = d } }
    END { print best }')"
  if [ -z "$RATE" ]; then
    echo "[display] $WANT is not offered by this screen -- mode left as it is"
  else
    wlr-randr --output "$OUT" --mode "${WANT}@${RATE}Hz" || wlr-randr --output "$OUT" --mode "$WANT" \
      || echo "[display] could not set $WANT -- mode left as it is"
  fi
fi

# 2. the rotation (lasts until the next start, so this runs at every start)
if [ -n "$ROT" ]; then
  wlr-randr --output "$OUT" --transform "$ROT" \
    && echo "[display] $OUT rotated: transform $ROT" \
    || echo "[display] could not rotate $OUT -- rotation left as it is"
fi
exit 0
