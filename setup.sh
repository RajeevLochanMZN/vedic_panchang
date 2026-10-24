#!/usr/bin/env bash
#
# setup.sh -- one-shot kiosk setup for the Vedic Ghadi (Panchang Clock) Pi.
#
# Run it ON THE PI, from the project folder, as your normal user (it asks for
# your password once, for the steps that need sudo):
#
#       cd ~/VedicGhadi && bash setup.sh
#
# It is safe to run again: every step checks what is already done first.
#
# What it does
#   1. Installs the system packages and the Python environment.
#   2. Turns on I2C (for the RTC) and desktop auto-login, hides the boot
#      splash, and stops the screen from blanking.
#   3. Hides the boot messages (config.txt + cmdline.txt, backed up first).
#   4. Writes ONE sudoers file with the few passwordless-sudo rules the app
#      needs (RTC clock sync, Wi-Fi setup, reboot, shutdown), validated with
#      visudo before it is installed -- and retires the two hand-made files
#      from earlier testing.
#   5. Cuts SD-card writes (logs kept in RAM, swap file off).
#   6. Registers launch.sh to start automatically when the desktop starts.
#
# What it deliberately does NOT do
#   - Switch the desktop to X11. The app already runs correctly on the Pi's
#     current desktop, so that is left alone.
#   - Hide the taskbar by editing desktop config files (risky). The app goes
#     real-fullscreen instead, which covers it.
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

edit_cmdline_txt() {
    step "Kernel command line (quiet boot)"
    local line new token
    line="$(tr -d '\n' < "$CMDLINE_TXT" | sed 's/[[:space:]]*$//')"
    if [[ "$line" != *root=* ]]; then
        warn "cmdline.txt has no root= entry -- leaving it alone."
        return 0
    fi
    new="$line"
    for token in quiet loglevel=3 logo.nologo vt.global_cursor_default=0; do
        case " $new " in
            *" $token "*) ;;                 # already there
            *) new="$new $token" ;;
        esac
    done
    if [ "$new" = "$line" ]; then
        info "cmdline.txt is already set for a quiet boot"
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

install_kiosk_launcher() {
    step "Kiosk auto-start"
    # Windows line endings would break a bash script on the Pi.
    sed -i 's/\r$//' "$PROJECT_DIR/launch.sh"
    chmod +x "$PROJECT_DIR/launch.sh" "$PROJECT_DIR/setup.sh"
    # Making the scripts executable would show up to git as a "modified" file
    # and could block a later `git pull` that updates launch.sh. Tell git on
    # this Pi to ignore permission-bit changes.
    git -C "$PROJECT_DIR" config core.fileMode false 2>/dev/null || true

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

summary() {
    step "Done"
    if [ "$WARNINGS" -gt 0 ]; then
        printf '\033[1;33m%s warning(s)\033[0m above -- read them before relying on the kiosk.\n' "$WARNINGS"
    else
        printf '\033[1;32mNo warnings.\033[0m\n'
    fi
    cat <<EOF

Next:
  1. Reboot:   sudo reboot      (the kiosk should then start by itself, fullscreen)
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
EOF
}

main() {
    preflight
    install_packages
    setup_python_env
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
