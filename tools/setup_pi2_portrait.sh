#!/usr/bin/env bash
# tools/setup_pi2_portrait.sh -- set up a Pi for the 7-inch 800x480 touch panel used UPRIGHT (portrait).
#
# Does, in one go, everything that is per-device and outside git (handover 14 Nov 2026, section 5):
#   1. the per-device files in ~/.config/vedicghadi/   (through tools/set_display.sh):
#        app_rotation.txt 270 | pixel_aspect.txt 1.067 | touch_buttons.txt raw
#        touch_map.txt (empty = straight) | screen_rotation.txt normal
#   2. the udev rule for the panel's USB touch chip      (through tools/install_touch_rule.sh)
#   3. puts your user into the group "input" if it is not in it yet
#   4. checks the result and tells you what to do next
#
#   bash tools/setup_pi2_portrait.sh                  the standard Pi 2 (run it as your normal user, NOT with sudo)
#   bash tools/setup_pi2_portrait.sh --dry-run        show what it would do, change nothing
#   bash tools/setup_pi2_portrait.sh --aspect 1.05    another panel with a different pixel aspect (default 1.067)
#   bash tools/setup_pi2_portrait.sh --rotation 90    turn the picture the other way (default 270)
#   bash tools/setup_pi2_portrait.sh --force-mode 800x480
#                                                     also force the screen mode in /boot/firmware/cmdline.txt
#                                                     (only for a panel that sends no usable mode list; the
#                                                     first Pi 2 has video=HDMI-A-1:800x480@60D there)
#   bash tools/setup_pi2_portrait.sh --skip-udev      leave the udev rule and the group alone
#   then:  sudo reboot
#
# It does NOT touch: the labwc autostart, ~/.config/labwc/environment (WLR_LIBINPUT_NO_DEVICES),
# launch.sh, display_mode.txt, settings.yaml.  Safe to run again: it writes the same values again.
# Test-only overrides: the VEDICGHADI_*_FILE variables of set_display.sh, VEDICGHADI_CMDLINE,
# VEDICGHADI_UDEV_RULE, VEDICGHADI_ALLOW_ROOT=1.

set -euo pipefail

TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASPECT=1.067
ROTATION=270
FORCE_MODE=""
DO_UDEV=1
DRY=0
ME="${USER:-$(id -un)}"

APP_ROTATION_FILE="${VEDICGHADI_APP_ROTATION_FILE:-$HOME/.config/vedicghadi/app_rotation.txt}"
PIXEL_ASPECT_FILE="${VEDICGHADI_PIXEL_ASPECT_FILE:-$HOME/.config/vedicghadi/pixel_aspect.txt}"
TOUCH_FILE="${VEDICGHADI_TOUCH_FILE:-$HOME/.config/vedicghadi/touch_buttons.txt}"
TOUCH_MAP_FILE="${VEDICGHADI_TOUCH_MAP_FILE:-$HOME/.config/vedicghadi/touch_map.txt}"
ROTATION_FILE="${VEDICGHADI_ROTATION_FILE:-$HOME/.config/vedicghadi/screen_rotation.txt}"
CMDLINE="${VEDICGHADI_CMDLINE:-/boot/firmware/cmdline.txt}"
RULE="${VEDICGHADI_UDEV_RULE:-/etc/udev/rules.d/99-vedicghadi-touch.rules}"

die() { echo "ERROR: $*" >&2; exit 1; }

usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed -e '$d' -e 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --aspect)     [ $# -ge 2 ] || die "--aspect needs a number, e.g. --aspect 1.067"; ASPECT="$2"; shift 2 ;;
    --rotation)   [ $# -ge 2 ] || die "--rotation needs 90, 180, 270 or normal"; ROTATION="$2"; shift 2 ;;
    --force-mode) [ $# -ge 2 ] || die "--force-mode needs a size, e.g. --force-mode 800x480"; FORCE_MODE="$2"; shift 2 ;;
    --skip-udev)  DO_UDEV=0; shift ;;
    --dry-run)    DRY=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *)            usage; die "unknown option: $1" ;;
  esac
done

[ "$ROTATION" = "0" ] && ROTATION=normal
# check the values BEFORE anything is written, so a typo does not leave a half-done setup
case "$ROTATION" in normal|90|180|270) ;; *) die "--rotation must be normal, 90, 180 or 270 (got: $ROTATION)" ;; esac
if ! [[ "$ASPECT" =~ ^[0-9]+(\.[0-9]+)?$ ]] || ! awk -v v="$ASPECT" 'BEGIN { exit !(v >= 0.8 && v <= 1.3) }'; then
  die "--aspect must be a number from 0.8 to 1.3 (got: $ASPECT)"
fi
if [ -n "$FORCE_MODE" ] && ! [[ "$FORCE_MODE" =~ ^[0-9]+x[0-9]+$ ]]; then
  die "--force-mode must look like 800x480 (got: $FORCE_MODE)"
fi
[ -f "$TOOLS/set_display.sh" ] || die "tools/set_display.sh not found next to this script ($TOOLS)"
[ -f "$TOOLS/install_touch_rule.sh" ] || die "tools/install_touch_rule.sh not found next to this script ($TOOLS)"
if [ "$(id -u)" -eq 0 ] && [ -z "${VEDICGHADI_ALLOW_ROOT:-}" ]; then
  die "run this as your normal user (not root, not with sudo): the settings belong in YOUR home folder. The script asks for sudo itself where it is needed."
fi

# set_display.sh does its own checks of the values; show only the first line of what it says
sd() {
  if [ "$DRY" -eq 1 ]; then echo "  + bash tools/set_display.sh $*"; return 0; fi
  local out
  out="$(bash "$TOOLS/set_display.sh" "$@" 2>&1)" || { printf '%s\n' "$out"; die "set_display.sh $* failed"; }
  printf '  %s\n' "$(printf '%s\n' "$out" | sed -n '1p')"
}

echo "== 1/4  per-device files in ~/.config/vedicghadi =="
sd app-rotate "$ROTATION"
sd pixel-aspect "$ASPECT"
sd touch-buttons raw
sd touch-map none
sd rotate normal
if [ -n "$FORCE_MODE" ]; then
  echo "   (--force-mode: asks for sudo to change $CMDLINE; a backup .bak-display is kept)"
  sd force "$FORCE_MODE"
fi

echo "== 2/4  udev rule for the touch chip =="
if [ "$DO_UDEV" -eq 1 ]; then
  if [ "$DRY" -eq 1 ]; then echo "  + bash tools/install_touch_rule.sh"
  else
    echo "  (its note about the group 'input' is dealt with in step 3)"
    bash "$TOOLS/install_touch_rule.sh" || die "install_touch_rule.sh failed"
  fi
else
  echo "  skipped (--skip-udev)"
fi

echo "== 3/4  group 'input' =="
NEED_LOGIN=0
# in the group already: either this login has it, or /etc/group lists the user (added earlier, no new login yet)
in_input() {
  case " $(id -nG 2>/dev/null) " in *" input "*) return 0 ;; esac
  case ",$(getent group input 2>/dev/null | cut -d: -f4)," in *",$ME,"*) return 0 ;; esac
  return 1
}
if [ "$DO_UDEV" -eq 1 ]; then
  if in_input; then
    echo "  OK: $ME is in the group 'input'."
  elif [ "$DRY" -eq 1 ]; then
    echo "  + sudo usermod -aG input $ME"
  else
    sudo usermod -aG input "$ME" || die "could not add $ME to the group 'input'"
    echo "  added $ME to the group 'input' (takes effect after the reboot)"
    NEED_LOGIN=1
  fi
else
  echo "  skipped (--skip-udev)"
fi

if [ "$DRY" -eq 1 ]; then
  echo
  echo "Dry run: nothing was changed."
  exit 0
fi

echo "== 4/4  check =="
FAILS=0
check() {                                   # label file expected-text
  local label="$1" file="$2" want="$3" got
  if [ -f "$file" ]; then got="$(tr -d '[:space:]' < "$file")"; else got="(file missing)"; fi
  if [ "$got" = "$want" ]; then
    printf '  OK    %-16s %s\n' "$label" "${want:-(empty = straight)}"
  else
    printf '  DIFF  %-16s is "%s", should be "%s"\n' "$label" "$got" "$want"
    FAILS=$((FAILS + 1))
  fi
}
check app_rotation "$APP_ROTATION_FILE" "$ROTATION"
check pixel_aspect "$PIXEL_ASPECT_FILE" "$ASPECT"
check touch_buttons "$TOUCH_FILE" raw
check touch_map "$TOUCH_MAP_FILE" ""
check screen_rotation "$ROTATION_FILE" normal
if [ "$DO_UDEV" -eq 1 ]; then
  if [ -f "$RULE" ]; then echo "  OK    udev rule        $RULE"
  else echo "  DIFF  udev rule        $RULE is missing"; FAILS=$((FAILS + 1)); fi
fi
if [ -n "$FORCE_MODE" ]; then
  if grep -qE "video=[^ ]*:${FORCE_MODE}@60D" "$CMDLINE" 2>/dev/null; then echo "  OK    kernel video=    $(grep -oE 'video=[^ ]*' "$CMDLINE" | head -n1)"
  else echo "  DIFF  kernel video=    not found in $CMDLINE"; FAILS=$((FAILS + 1)); fi
else
  kv="$(grep -oE 'video=[^ ]*' "$CMDLINE" 2>/dev/null | head -n1 || true)"
  echo "  info  kernel video=    ${kv:-(none)}"
  echo "        (not changed by this run; use --force-mode 800x480 if the panel shows no picture or a wrong mode)"
fi

echo
if [ "$FAILS" -gt 0 ]; then
  echo "$FAILS check(s) did not match -- see the DIFF lines above."
  exit 1
fi
echo "All settings are in place. Now run:  sudo reboot"
[ "$NEED_LOGIN" -eq 1 ] && echo "(the reboot is needed: the group change only applies to a new login)"
echo "After the reboot the clock's first log lines should read:"
echo "  [display] screen 480 x 854 (program turns the picture by $ROTATION, panel is 800 x 480, pixel aspect $ASPECT) -> PORTRAIT dial page"
echo "  [touch] reading the touch chip from /dev/hidrawN"
echo "see them with:  grep -E \"\\[display\\]|\\[touch\\]\" /dev/shm/vedicghadi.log"
exit 0
