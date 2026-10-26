#!/usr/bin/env bash
#
# setup.sh -- one-shot kiosk setup for the Vedic Ghadi (Panchang Clock) Pi.
#
# Run it ON THE PI, from the project folder, as your normal user (it asks for
# your password once, for the steps that need sudo):
#
#       cd ~/VedicGhadi && bash setup.sh
#
# Options:
#       --keep-desktop   start the clock ON TOP of the normal desktop instead of
#                        the silent, desktop-free start (see step 6)
#       --skip-install   skip the apt/pip steps (quick re-run after a change)
#
# It is safe to run again: every step checks what is already done first.
#
# What it does
#   1. Installs the system packages and the Python environment.
#   2. Turns on I2C (for the RTC) and desktop auto-login, hides the boot
#      splash, and stops the screen from blanking.
#   3. Hides the Raspberry Pi logos and boot messages (config.txt +
#      cmdline.txt, backed up first).
#   4. Writes ONE sudoers file with the few passwordless-sudo rules the app
#      needs (RTC clock sync, Wi-Fi setup, reboot, shutdown), validated with
#      visudo before it is installed -- and retires the two hand-made files
#      from earlier testing.
#   5. Cuts SD-card writes (logs kept in RAM, swap file off).
#   6. Makes the clock start silently. On Raspberry Pi OS a per-user
#      ~/.config/labwc/autostart runs IN ADDITION to the system autostart
#      (/etc/xdg/labwc/autostart), and the system one is what starts the
#      desktop wallpaper and the taskbar. So the clock is started from the
#      per-user file, and the two desktop lines in the system file are
#      commented out (each marked "#VEDICGHADI# ", so they can be put back
#      exactly). The screen stays black until the clock is up. With
#      --keep-desktop those lines are put back and the clock is started by
#      an XDG autostart entry on top of the normal desktop instead.
#
# What it deliberately does NOT do
#   - Switch the desktop to X11. The app already runs correctly on the Pi's
#     current desktop, so that is left alone.
#   - Touch any other system file in /etc/xdg. The ONLY one it edits is
#     /etc/xdg/labwc/autostart (two lines commented out, original saved as
#     autostart.bak-vedicghadi). An OS upgrade can overwrite that file and
#     bring the desktop back -- just run this script again with --skip-install.
#   - Make the SD card read-only (overlay filesystem). That is a separate,
#     later step -- see the project notes.
#
set -euo pipefail

# --- locations (the defaults are right for Raspberry Pi OS; tests override them) ---
CONFIG_TXT="${CONFIG_TXT:-/boot/firmware/config.txt}"
CMDLINE_TXT="${CMDLINE_TXT:-/boot/firmware/cmdline.txt}"
SUDOERS_FILE="${SUDOERS_FILE:-/etc/sudoers.d/vedicghadi}"
JOURNALD_DROPIN="${JOURNALD_DROPIN:-/etc/systemd/journald.conf.d/vedicghadi.conf}"
SUDO="${SUDO-sudo}"      # tests set SUDO= (empty) to run without privileges

KEEP_DESKTOP="${KEEP_DESKTOP:-0}"    # 1 = start the clock on top of the normal desktop
SKIP_INSTALL="${SKIP_INSTALL:-0}"    # 1 = skip the apt/pip steps
AUTOSTART_MARKER="Written by VedicGhadi setup.sh"
# The system autostart file, and the prefix put on the lines that start the
# desktop when they are switched off. launch.sh looks for the same prefix.
SYSTEM_LABWC_AUTOSTART="${SYSTEM_LABWC_AUTOSTART:-/etc/xdg/labwc/autostart}"
DISABLED_MARK="#VEDICGHADI# "

WARNINGS=0

step() { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }
info() { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; WARNINGS=$((WARNINGS + 1)); }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

# Run one command; if it fails, warn and carry on. Used for raspi-config
# settings, whose exact flags can differ between OS releases -- one odd flag
# must not abort the whole setup.
try() {
    local description="$1"; shift
    if "$@"; then
        info "$description"
    else
        warn "$description -- FAILED (command: $*). Continuing."
    fi
}

# Keep the FIRST backup only (never overwrite it with an already-edited copy).
# A plain existence check, because `cp -n` is changing behaviour in newer coreutils.
backup_once() { [ -e "$1.bak-vedicghadi" ] || $SUDO cp "$1" "$1.bak-vedicghadi"; }

# ---------------------------------------------------------------------------
preflight() {
    [ "$(id -u)" -ne 0 ] || die "Run this as your normal user, not root / not with sudo. It calls sudo itself where needed, and the kiosk must be set up for YOUR user."
    command -v raspi-config >/dev/null || die "raspi-config not found -- this script is for Raspberry Pi OS, run on the Pi itself."
    command -v apt-get >/dev/null      || die "apt-get not found -- this script is for Raspberry Pi OS."

    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [ -f "$PROJECT_DIR/ui/main_window_hi.py" ] || die "Can't find ui/main_window_hi.py next to this script ($PROJECT_DIR). Run it from the project folder."
    [ -f "$PROJECT_DIR/launch.sh" ]            || die "launch.sh is missing from $PROJECT_DIR -- run 'git pull' first."

    KIOSK_USER="$(id -un)"
    KIOSK_HOME="$HOME"
    info "Setting up the kiosk for user '$KIOSK_USER' in $PROJECT_DIR"
    sudo -v || die "sudo password needed."
}

install_packages() {
    step "System packages"
    $SUDO apt-get update
    # python3-pyqt5 comes from apt on purpose: building PyQt5 from source on a Pi 3B+ takes hours.
    $SUDO apt-get install -y python3-pyqt5 python3-venv python3-pip python3-smbus i2c-tools build-essential python3-dev git
}

setup_python_env() {
    step "Python environment"
    if [ ! -x "$PROJECT_DIR/venv/bin/python" ]; then
        python3 -m venv --system-site-packages "$PROJECT_DIR/venv"
        info "Created the virtual environment"
    else
        info "Virtual environment already exists"
    fi

    # requirements.txt lists PyQt5 for the PC. On the Pi it comes from apt
    # (--system-site-packages makes it visible here), so skip that line --
    # pip would otherwise try to compile it from source.
    local req
    req="$(mktemp)"
    grep -viE '^[[:space:]]*(pyqt5|#|$)' "$PROJECT_DIR/requirements.txt" > "$req" || true
    "$PROJECT_DIR/venv/bin/pip" install -r "$req"
    rm -f "$req"

    "$PROJECT_DIR/venv/bin/python" -c "import PyQt5, swisseph, yaml, gpiozero, flask, smbus" \
        || die "A required Python module failed to import -- see the messages above."
    info "All Python modules import correctly"
}

configure_pi() {
    step "Raspberry Pi settings"
    try "I2C enabled (for the RTC)"    $SUDO raspi-config nonint do_i2c 0
    try "Desktop auto-login enabled"   $SUDO raspi-config nonint do_boot_behaviour B4
    try "Boot splash screen disabled"  $SUDO raspi-config nonint do_boot_splash 1
    try "Screen blanking disabled"     $SUDO raspi-config nonint do_blanking 1
}

edit_config_txt() {
    step "Boot config (hide the rainbow splash)"
    if grep -q '^disable_splash=1' "$CONFIG_TXT"; then
        info "config.txt already hides the rainbow splash"
        return 0
    fi
    backup_once "$CONFIG_TXT"
    # An explicit [all] header first, so the line can never land inside a
    # model-specific section left open at the end of the file.
    printf '\n# Added by VedicGhadi setup.sh -- hide the rainbow boot splash\n[all]\ndisable_splash=1\n' \
        | $SUDO tee -a "$CONFIG_TXT" >/dev/null
    info "config.txt updated (original saved as $CONFIG_TXT.bak-vedicghadi)"
}

# Print $1 with the standalone word $2 removed (other words are left untouched).
remove_token() {
    local padded=" $1 "
    padded="${padded// $2 / }"
    padded="${padded# }"
    printf '%s' "${padded% }"
}

edit_cmdline_txt() {
    step "Kernel command line (no logos, quiet boot)"
    local line new token
    line="$(tr -d '\n' < "$CMDLINE_TXT" | sed 's/[[:space:]]*$//')"
    if [[ "$line" != *root=* ]]; then
        warn "cmdline.txt has no root= entry -- leaving it alone."
        return 0
    fi
    # 'splash' is what turns on the big Raspberry Pi logo screen (Plymouth).
    new="$(remove_token "$line" splash)"
    # quiet/loglevel: no boot text. logo.nologo: no little Pi logos in the corner.
    # vt.global_cursor_default=0: no blinking cursor. plymouth.enable=0: the
    # logo screen stays off even if something re-adds 'splash'.
    for token in quiet loglevel=3 logo.nologo vt.global_cursor_default=0 plymouth.enable=0; do
        case " $new " in
            *" $token "*) ;;                 # already there
            *) new="$new $token" ;;
        esac
    done
    if [ "$new" = "$line" ]; then
        info "cmdline.txt is already set for a silent boot"
        return 0
    fi
    backup_once "$CMDLINE_TXT"
    printf '%s\n' "$new" | $SUDO tee "$CMDLINE_TXT" >/dev/null   # cmdline.txt must stay ONE line
    info "cmdline.txt updated (original saved as $CMDLINE_TXT.bak-vedicghadi)"
}

render_sudoers_rules() {
    cat <<EOF
# Written by VedicGhadi setup.sh. These are the only commands the kiosk app
# may run as root without a password:
#   nmcli     -- Wi-Fi Setup page (hardware/wifi_setup.py)
#   date -s   -- set the system clock from the RTC (hardware/rtc.py)
#   reboot    -- Wi-Fi Setup page, after saving a change
#   shutdown  -- the Panchang + Calendar safe-shutdown combo
$KIOSK_USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli *
$KIOSK_USER ALL=(ALL) NOPASSWD: /usr/bin/date -s *
$KIOSK_USER ALL=(ALL) NOPASSWD: /usr/sbin/reboot
$KIOSK_USER ALL=(ALL) NOPASSWD: /usr/sbin/shutdown -h now
EOF
}

setup_sudoers() {
    step "Passwordless sudo for the few commands the app needs"
    local bin tmp
    for bin in /usr/bin/nmcli /usr/bin/date /usr/sbin/reboot /usr/sbin/shutdown; do
        [ -x "$bin" ] || warn "$bin not found -- its sudo rule will have no effect"
    done
    tmp="$(mktemp)"
    render_sudoers_rules > "$tmp"
    # A broken sudoers file can lock you out of sudo entirely, so it is
    # validated BEFORE it is installed.
    if ! $SUDO visudo -cf "$tmp" >/dev/null; then
        rm -f "$tmp"
        die "The generated sudoers rules failed validation -- nothing was installed."
    fi
    $SUDO install -m 0440 -o root -g root "$tmp" "$SUDOERS_FILE"
    rm -f "$tmp"
    # The two hand-made files from earlier testing are now redundant.
    $SUDO rm -f /etc/sudoers.d/rtc-sync /etc/sudoers.d/wifi-setup
    info "Installed $SUDOERS_FILE"
}

reduce_sd_writes() {
    step "Fewer SD-card writes"

    # System logs in RAM instead of on the card. Trade-off: `journalctl`
    # only shows the current boot, and a log is gone after a reboot.
    $SUDO mkdir -p "$(dirname "$JOURNALD_DROPIN")"
    printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=20M\n' | $SUDO tee "$JOURNALD_DROPIN" >/dev/null
    info "System logs kept in RAM (undo: delete $JOURNALD_DROPIN)"

    if [ -n "$(systemctl list-unit-files --no-legend dphys-swapfile.service 2>/dev/null)" ]; then
        try "Swap file disabled" $SUDO systemctl disable --now dphys-swapfile.service
    else
        info "No dphys-swapfile service on this OS -- swap left as it is"
    fi

    if findmnt -no OPTIONS / | grep -q noatime; then
        info "Root filesystem is already mounted noatime"
    else
        warn "Root filesystem is not mounted noatime -- add it in /etc/fstab by hand if you want."
    fi
}

# Switch off the desktop wallpaper (pcmanfm) and taskbar (wf-panel-pi) by
# commenting out their lines in the system autostart. Each commented line is
# prefixed with DISABLED_MARK so show_desktop() can put back exactly those.
hide_desktop() {
    local f="$SYSTEM_LABWC_AUTOSTART"
    if [ ! -f "$f" ]; then
        warn "$f not found -- cannot hide the desktop (is this the labwc desktop?)."
        return 0
    fi
    if grep -qE '^[[:space:]]*[^#[:space:]].*(pcmanfm|wf-panel-pi)' "$f"; then
        backup_once "$f"
        $SUDO sed -i -E "/^[[:space:]]*[^#[:space:]].*(pcmanfm|wf-panel-pi)/ s/^/$DISABLED_MARK/" "$f"
        info "Desktop wallpaper and taskbar switched off (original saved as $f.bak-vedicghadi)"
    elif grep -q "^$DISABLED_MARK" "$f"; then
        info "Desktop wallpaper and taskbar are already switched off"
    else
        warn "No pcmanfm / wf-panel-pi lines found in $f -- nothing to switch off. If the desktop still shows, send me that file."
    fi
}

show_desktop() {
    local f="$SYSTEM_LABWC_AUTOSTART"
    if [ -f "$f" ] && grep -q "^$DISABLED_MARK" "$f"; then
        $SUDO sed -i "s/^$DISABLED_MARK//" "$f"
        info "Desktop wallpaper and taskbar switched back on"
    fi
}

# Silent start: a per-user labwc autostart that runs the clock.
write_silent_autostart() {
    local target="$KIOSK_HOME/.config/labwc/autostart"
    mkdir -p "$KIOSK_HOME/.config/labwc"
    if [ -e "$target" ] && ! grep -q "$AUTOSTART_MARKER" "$target"; then
        [ -e "$target.bak-vedicghadi" ] || cp "$target" "$target.bak-vedicghadi"
        warn "You already had $target -- saved as $target.bak-vedicghadi and replaced."
    fi
    cat > "$target" <<EOF
# $AUTOSTART_MARKER
# Runs at login IN ADDITION to /etc/xdg/labwc/autostart. setup.sh has
# commented out that file's wallpaper and taskbar lines, so only the clock
# appears: the screen stays black until it is up.
# To get the normal desktop back, run:
#       bash setup.sh --skip-install --keep-desktop
KIOSK_START_DELAY=0 $PROJECT_DIR/launch.sh &
EOF
    info "Silent start written: $target"
}

# Undo the silent start (and put back any autostart file that was replaced).
remove_silent_autostart() {
    local target="$KIOSK_HOME/.config/labwc/autostart"
    if [ -e "$target" ] && grep -q "$AUTOSTART_MARKER" "$target"; then
        rm -f "$target"
        if [ -e "$target.bak-vedicghadi" ]; then
            mv "$target.bak-vedicghadi" "$target"
            info "Restored your original $target"
        fi
        info "Silent start removed -- the normal desktop will start again"
    fi
}

# Alternative start: an XDG entry that runs after the normal desktop is up.
write_xdg_autostart() {
    mkdir -p "$KIOSK_HOME/.config/autostart"
    cat > "$KIOSK_HOME/.config/autostart/vedicghadi.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Vedic Ghadi
Comment=Panchang clock kiosk
Exec=$PROJECT_DIR/launch.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
    info "Auto-start entry written: $KIOSK_HOME/.config/autostart/vedicghadi.desktop"
}

install_kiosk_launcher() {
    step "Kiosk auto-start"
    # Windows line endings would break a bash script on the Pi.
    sed -i 's/\r$//' "$PROJECT_DIR/launch.sh"
    chmod +x "$PROJECT_DIR/launch.sh" "$PROJECT_DIR/setup.sh"
    # Making the scripts executable would show up to git as a "modified" file
    # and could block a later `git pull` that updates launch.sh. Tell git on
    # this Pi to ignore permission-bit changes.
    git -C "$PROJECT_DIR" config core.fileMode false 2>/dev/null || true

    # Exactly ONE of the two start methods is active, so the clock never
    # starts twice and never needs the lock to sort it out.
    if [ "$KEEP_DESKTOP" = "1" ]; then
        remove_silent_autostart
        show_desktop
        write_xdg_autostart
    else
        rm -f "$KIOSK_HOME/.config/autostart/vedicghadi.desktop"
        write_silent_autostart
        hide_desktop
    fi
}

summary() {
    step "Done"
    if [ "$WARNINGS" -gt 0 ]; then
        printf '\033[1;33m%s warning(s)\033[0m above -- read them before relying on the kiosk.\n' "$WARNINGS"
    else
        printf '\033[1;32mNo warnings.\033[0m\n'
    fi
    cat <<EOF

Next:
  1. Reboot:   sudo reboot      (the screen stays black, then the clock appears, fullscreen)
  2. Safe shutdown: hold Panchang + Calendar together for 3 seconds. Wait until
     the screen goes blank AND the green LED on the Pi stops flickering before
     you remove power.

Handy commands:
  Try it now, in a normal window:   VEDICGHADI_WINDOWED=1 ./launch.sh
  See what the app printed:         cat /dev/shm/vedicghadi.log
  Stop the kiosk (over SSH):        pkill -f launch.sh; pkill -f main_window_hi.py
  Change the kiosk's main page:     edit the KIOSK_ENTRY line in launch.sh, then reboot
  Quiet boot hides boot messages. To undo it:
        sudo cp $CMDLINE_TXT.bak-vedicghadi $CMDLINE_TXT
  Get the normal desktop back (e.g. to open a terminal on the Pi itself):
        bash setup.sh --skip-install --keep-desktop   then reboot
     (or, by hand:  sudo sed -i 's/^#VEDICGHADI# //' $SYSTEM_LABWC_AUTOSTART )
  If the screen stays black and you have no way in: plug in a keyboard and
  press Ctrl+Alt+F2 for a text login (usually works), or SSH in, then run the
  command above.
  After an OS upgrade the desktop may come back (the upgrade can overwrite
  $SYSTEM_LABWC_AUTOSTART). Just run:  bash setup.sh --skip-install
EOF
}

parse_args() {
    local arg
    for arg in "$@"; do
        case "$arg" in
            --keep-desktop) KEEP_DESKTOP=1 ;;
            --skip-install) SKIP_INSTALL=1 ;;
            -h|--help)      sed -n '3,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
            *)              die "Unknown option: $arg (try --help)" ;;
        esac
    done
}

main() {
    parse_args "$@"
    preflight
    if [ "$SKIP_INSTALL" != "1" ]; then
        install_packages
        setup_python_env
    fi
    configure_pi
    edit_config_txt
    edit_cmdline_txt
    setup_sudoers
    reduce_sd_writes
    install_kiosk_launcher
    summary
}

# Only run when executed, not when sourced (the sandbox tests source this file).
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
