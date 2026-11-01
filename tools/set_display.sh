#!/usr/bin/env bash
# tools/set_display.sh -- change the screen resolution of a VedicGhadi Pi for a NEW display.
#
#   bash tools/set_display.sh show             what the Pi sees and which settings are in effect
#   bash tools/set_display.sh auto             use the screen's own preferred mode (the normal case)
#   bash tools/set_display.sh 1440x900         use one of the modes the screen offers (see `show`)
#   bash tools/set_display.sh force 1280x720   the screen gives NO mode list ("(null) (null)" in
#                                              wlr-randr, only 1024x768 / 800x600 ...): force a mode
#                                              in the kernel line instead
#   then:  sudo reboot
#
# How it works:
#   "auto" / "WxH" write ~/.config/vedicghadi/display_mode.txt, read by apply_display_mode.sh
#          (hook in ~/.config/labwc/autostart, installed by tools/pi_display_fix.sh).
#   "force" adds  video=<output>:WxH@60D  to /boot/firmware/cmdline.txt (needs sudo, keeps a backup
#          cmdline.txt.bak-display).  Needed only when the screen sends no EDID.
#   "auto" also removes any forced video= part again.

set -e
DISPLAY_FILE="${VEDICGHADI_DISPLAY_FILE:-$HOME/.config/vedicghadi/display_mode.txt}"
CMDLINE="${VEDICGHADI_CMDLINE:-/boot/firmware/cmdline.txt}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

LIST="$(wlr-randr 2>/dev/null || true)"
OUT_AUTO="$(printf '%s\n' "$LIST" | awk '/^[^ ]/ { print $1; exit }')"
OUT="${VEDICGHADI_OUTPUT:-$OUT_AUTO}"
OUT="${OUT:-HDMI-A-1}"
SUDO=""; [ -w "$CMDLINE" ] || SUDO="sudo"

cmd="${1:-show}"

remove_forced() {                       # take a forced video= part out of cmdline.txt
  [ -f "$CMDLINE" ] || return 0
  if grep -qE 'video=HDMI-A-[0-9]+:' "$CMDLINE"; then
    $SUDO cp "$CMDLINE" "$CMDLINE.bak-display"
    $SUDO sed -i -E 's/ ?video=HDMI-A-[0-9]+:[^ ]*//g' "$CMDLINE"
    echo "cmdline: forced video= part removed (backup: $CMDLINE.bak-display)"
  fi
}

case "$cmd" in
  show)
    echo "== what the Pi sees (wlr-randr) =="
    if [ -n "$LIST" ]; then
      printf '%s\n' "$LIST" | awk '/^[^ ]/ {print} /current/ {print "   current mode:" $0} /Modes:/ {m=1; next} m && /px/ {n++} END {print "   modes offered: " n+0}'
      printf '%s\n' "$LIST" | grep -q '(null) (null)' && echo "   NOTE: make/model are (null): the screen sends no EDID -> use:  force WxH"
    else
      echo "   wlr-randr gave nothing (run this over SSH after the clock has started)"
    fi
    echo "== EDID bytes per HDMI port (0 = none) =="
    for f in /sys/class/drm/*HDMI*/edid; do [ -e "$f" ] && echo "   $f: $(wc -c < "$f") bytes"; done
    echo "== settings in effect =="
    echo "   display_mode.txt : $( [ -f "$DISPLAY_FILE" ] && cat "$DISPLAY_FILE" || echo '(none = auto)')"
    echo "   kernel video=    : $(grep -oE 'video=HDMI-A-[0-9]+:[^ ]*' "$CMDLINE" 2>/dev/null || echo '(none)')"
    ;;
  auto)
    mkdir -p "$(dirname "$DISPLAY_FILE")"; echo auto > "$DISPLAY_FILE"
    echo "display_mode.txt: auto"
    remove_forced
    echo "done -- now run:  sudo reboot"
    ;;
  force)
    want="${2:-}"
    [[ "$want" =~ ^[0-9]+x[0-9]+$ ]] || { echo "usage: set_display.sh force 1280x720"; exit 1; }
    [ -f "$CMDLINE" ] || { echo "ERROR: $CMDLINE not found"; exit 1; }
    mkdir -p "$(dirname "$DISPLAY_FILE")"; echo auto > "$DISPLAY_FILE"
    $SUDO cp "$CMDLINE" "$CMDLINE.bak-display"
    $SUDO sed -i -E 's/ ?video=HDMI-A-[0-9]+:[^ ]*//g' "$CMDLINE"
    $SUDO sed -i "1 s/\$/ video=$OUT:${want}@60D/" "$CMDLINE"
    if [ "$(wc -l < "$CMDLINE")" -gt 1 ]; then                 # must stay ONE line
      $SUDO cp "$CMDLINE.bak-display" "$CMDLINE"; echo "ERROR: cmdline.txt would have more than one line -- restored the backup."; exit 1
    fi
    echo "cmdline: added video=$OUT:${want}@60D (backup: $CMDLINE.bak-display)"
    echo "$(cat "$CMDLINE")"
    echo "done -- now run:  sudo reboot      (undo: bash tools/set_display.sh auto)"
    ;;
  *)
    want="$cmd"
    [[ "$want" =~ ^[0-9]+x[0-9]+$ ]] || { echo "usage: set_display.sh show | auto | WxH | force WxH"; exit 1; }
    if ! printf '%s\n' "$LIST" | awk '/px/ {print $1}' | grep -qx "$want"; then
      echo "ERROR: this screen does not offer $want. Offered sizes:"
      printf '%s\n' "$LIST" | awk '/px/ {print "   " $1}' | sort -u
      echo "If the screen gives no real list (EDID), use:  bash tools/set_display.sh force $want"
      exit 1
    fi
    mkdir -p "$(dirname "$DISPLAY_FILE")"; echo "$want" > "$DISPLAY_FILE"
    remove_forced
    echo "display_mode.txt: $want   (applied at the next start, before the clock opens)"
    echo "done -- now run:  sudo reboot"
    ;;
esac
