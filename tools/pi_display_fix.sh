#!/usr/bin/env bash
# tools/pi_display_fix.sh -- the Pi-side display settings of the VedicGhadi kiosk.
#
#   1. BOOT WITHOUT KEYBOARD / MOUSE
#        adds  WLR_LIBINPUT_NO_DEVICES=1  to ~/.config/labwc/environment
#        (without it the compositor shows a blank screen when no keyboard/mouse is plugged in)
#   2. SCREEN MODE HOOK
#        adds one line to ~/.config/labwc/autostart, just BEFORE the launch.sh line, that runs
#        tools/apply_display_mode.sh.  That script reads ~/.config/vedicghadi/display_mode.txt:
#        "auto" (default) = use the screen's own preferred mode, or e.g. "1440x900" to force one.
#        => the SAME image works on every display; only that one file differs per device.
#
# USE (on the Pi, after setup.sh -- setup.sh rewrites ~/.config/labwc/autostart):
#     bash ~/VedicGhadi/tools/pi_display_fix.sh                      both, mode "auto"
#     bash ~/VedicGhadi/tools/pi_display_fix.sh --display-mode 1440x900   both, force 1440x900 here
#     bash ~/VedicGhadi/tools/pi_display_fix.sh --no-mode            only 1
#     bash ~/VedicGhadi/tools/pi_display_fix.sh --remove-mode        take the hook (or an old hand-made
#                                                                    wlr-randr line) out of autostart
#   then:  sudo reboot
# Safe to run more than once; keeps a backup of autostart as autostart.bak-mode.

set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="${LABWC_CONFIG_DIR:-$HOME/.config/labwc}"
ENVF="$CFG/environment"
AUTO="$CFG/autostart"
MODEF="${VEDICGHADI_DISPLAY_FILE:-$HOME/.config/vedicghadi/display_mode.txt}"
MARK="# VEDICGHADI-MODE"

do_env=1; do_mode=1; remove=0; want=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-mode)      do_mode=0 ;;
    --remove-mode)  remove=1; do_env=0 ;;
    --display-mode) shift; want="$1" ;;
    *) echo "unknown option: $1"; exit 1 ;;
  esac
  shift
done

mkdir -p "$CFG"

if [ "$remove" = 1 ]; then
  if [ -f "$AUTO" ] && grep -qE "VEDICGHADI-MODE|^wlr-randr --output|apply_display_mode" "$AUTO"; then
    cp "$AUTO" "$AUTO.bak-mode"
    sed -i -e '/VEDICGHADI-MODE/,+1d' -e '/^# Monitor: native/d' -e '/^wlr-randr --output/d' "$AUTO"
    echo "mode line removed from $AUTO (backup: $AUTO.bak-mode)"
  else
    echo "no mode line found in $AUTO"
  fi
  exit 0
fi

if [ "$do_env" = 1 ]; then
  touch "$ENVF"
  if grep -q '^WLR_LIBINPUT_NO_DEVICES=1' "$ENVF"; then
    echo "environment: boot-without-keyboard line already present"
  else
    printf '\nWLR_LIBINPUT_NO_DEVICES=1\n' >> "$ENVF"
    echo "environment: added WLR_LIBINPUT_NO_DEVICES=1 to $ENVF"
  fi
fi

if [ "$do_mode" = 1 ]; then
  mkdir -p "$(dirname "$MODEF")"
  if [ -n "$want" ]; then
    echo "$want" > "$MODEF"; echo "display mode for this device set to: $want  ($MODEF)"
  elif [ ! -f "$MODEF" ]; then
    echo "auto" > "$MODEF"; echo "display mode for this device: auto  ($MODEF)"
  else
    echo "display mode for this device stays: $(cat "$MODEF")"
  fi
  if [ ! -f "$AUTO" ]; then
    echo "ERROR: $AUTO not found -- run setup.sh first (it writes this file), then run this script again."
    exit 1
  fi
  if grep -qE "VEDICGHADI-MODE|^wlr-randr --output" "$AUTO"; then
    echo "autostart: a mode line is already present (left as it is; use --remove-mode first to replace it)"
  elif ! grep -q "launch.sh" "$AUTO"; then
    echo "ERROR: no launch.sh line in $AUTO -- not touching it."
    exit 1
  else
    cp "$AUTO" "$AUTO.bak-mode"
    L1="$MARK: set the screen mode (if this device needs one) BEFORE the clock starts"
    L2="bash $HERE/apply_display_mode.sh"
    awk -v l1="$L1" -v l2="$L2" '/launch\.sh/ && !done { print l1; print l2; done=1 } { print }' "$AUTO" > "$AUTO.new"
    mv "$AUTO.new" "$AUTO"
    echo "autostart: added the mode hook before the launch.sh line (backup: $AUTO.bak-mode)"
  fi
fi
echo "done -- now run:  sudo reboot"
