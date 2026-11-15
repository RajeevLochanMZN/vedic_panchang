# tools/setup_pi2_portrait.sh  (14 Nov 2026)

One script that sets up a Pi for the 7-inch 800x480 touch panel used upright (portrait): the five per-device
files in ~/.config/vedicghadi, the udev rule for the touch chip, and the group `input`. It calls your existing
tools/set_display.sh and tools/install_touch_rule.sh (not changed), so there is no second copy of their logic.

## Install

Copy `tools/setup_pi2_portrait.sh` into the project's tools folder on the PC, commit, push, then on the Pi:

    cd ~/VedicGhadi && git pull

## Use (as your normal user, NOT with sudo; over SSH is best)

    bash tools/setup_pi2_portrait.sh --dry-run     # shows what it would do, changes nothing
    bash tools/setup_pi2_portrait.sh               # does it, then checks every value
    sudo reboot

Options: `--aspect 1.05` (other panel, default 1.067), `--rotation 90` (default 270),
`--force-mode 800x480` (also forces the screen mode in /boot/firmware/cmdline.txt), `--skip-udev`, `--help`.
The values are checked before anything is written, so a typo leaves nothing half done.

## Written / not touched

Writes: app_rotation 270, pixel_aspect 1.067, touch_buttons raw, touch_map (empty), screen_rotation normal,
/etc/udev/rules.d/99-vedicghadi-touch.rules, group `input` for your user.
Does not touch: labwc autostart, ~/.config/labwc/environment (WLR_LIBINPUT_NO_DEVICES), launch.sh,
display_mode.txt, settings.yaml. Safe to run again (it writes the same values again).

## Your first Pi 2 has one more setting

`bash tools/set_display.sh show` on the first Pi 2 (14 Nov) lists `kernel video=HDMI-A-1:800x480@60D`: the
screen mode is forced in cmdline.txt. The handover section 5 does not list it. This script leaves it alone
unless you pass `--force-mode 800x480`. For an exact copy of the first Pi 2, pass it.

## Check it on the working Pi 2 first (nothing should change)

    bash tools/set_display.sh show > /tmp/before.txt
    bash tools/setup_pi2_portrait.sh
    bash tools/set_display.sh show > /tmp/after.txt
    diff /tmp/before.txt /tmp/after.txt && echo "identical"

Expected: step 4 prints OK on all six lines, and `identical`. Re-running `install_touch_rule.sh` can re-create
the touch device while the clock runs, so touch may stop until the reboot: that is why the script asks for one.

## What was tested where

Sandbox only: `bash -n`, shellcheck (clean), a fake home folder with a fake sudo: dry run (writes nothing), full
run, second run, bad values (nothing written), refusal as root, `--rotation 0`, `--aspect 1.05`, `--force-mode`
(stays one line, twice), and a setting that did not take is reported as DIFF with exit 1.
NOT tested on a real Pi: the real sudo/udev/group steps, the real touch chip, a fresh image.
