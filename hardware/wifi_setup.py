"""
hardware/wifi_setup.py

Wi-Fi Setup / hotspot mode, triggered by physical Button 4
(hardware/buttons.py's wifi_setup_pressed signal).

WHAT THIS IS FOR: the DS3231 RTC (hardware/rtc.py) can only stay
accurate through power-offs of a few months at most on its own
stock accuracy -- for genuinely long stretches with home Wi-Fi down,
the Pi needs SOME way back online to NTP-resync. This module lets
the user press Button 4, connect their phone to a temporary hotspot
the Pi broadcasts, and enter different Wi-Fi credentials (e.g. a
mobile hotspot) through a small web form -- no keyboard/monitor
needed on the Pi itself.

DESIGN (agreed with the user):
  - Only triggered by the explicit Button 4 press, NEVER
    automatically on connection failure -- the Pi's normal Wi-Fi
    connection (NetworkManager's own default behavior) keeps quietly
    retrying known networks in the background at all times regardless
    of this module.
  - Language switching was explicitly DROPPED from this page's scope
    (conflicts with the project's separate "no runtime language
    switching" decision) -- this form only collects Wi-Fi credentials
    and a location name/latitude/longitude.
  - After a successful submission, the Pi REBOOTS to apply everything
    cleanly (new Wi-Fi profile + new location) rather than trying to
    hot-apply network changes while the app keeps running -- much
    simpler and more robust than juggling live state.
  - Uses Flask (simpler, more readable code) rather than Python's
    bare http.server -- explicit trade-off the user chose, given
    basic Python fluency.

PREREQUISITES the future setup script still needs to add (same
pattern as hardware/rtc.py's sudoers requirement):
  1. `pip install flask` inside the venv (added to requirements.txt).
  2. Passwordless sudo rules for the specific commands this module
     runs non-interactively, e.g. via
     `sudo visudo -f /etc/sudoers.d/wifi-setup`:
        rajeevlochan ALL=(ALL) NOPASSWD: /usr/bin/nmcli *
        rajeevlochan ALL=(ALL) NOPASSWD: /usr/sbin/reboot
  Until these are added, entering setup mode / submitting the form
  will fail -- errors are logged to the console, not silently
  swallowed, so this should be obvious rather than a mystery.

WHY THE RESPONSE-THEN-DELAY DANCE IN _finish_setup_and_reboot():
the Pi's own Wi-Fi radio can only be in ONE mode at a time --
broadcasting the setup hotspot, OR connected to a real network,
never both. The instant NetworkManager is told to connect to the
newly-entered network, the hotspot the phone is connected through
disappears -- which would normally cut the phone off before it ever
receives the "success" page. To avoid that, the actual network
switch + reboot happens a few seconds AFTER the HTTP response is
already sent, on a background thread, giving the phone's browser
time to actually display the success message first.

SETTINGS.YAML EDITING: uses a targeted find-and-replace on just the
`location:` block's name/latitude/longitude lines (NOT a full
yaml.safe_load()+yaml.safe_dump() rewrite of the whole file) -- a
full rewrite would silently DELETE every explanatory comment already
in that file (PyYAML doesn't preserve comments on a round trip).
This is more fragile to a manual reformatting of settings.yaml than
a full parser would be, but safe as long as the file's basic
structure (one field per line, standard "key: value" form) stays as
it already is.
"""

import os
import re
import subprocess
import threading
import time

from flask import Flask, request

# -- AP/hotspot mode settings --------------------------------------
HOTSPOT_SSID = "VedicGhadi-Setup"
HOTSPOT_PASSWORD = "vedicghadi123"  # shown to the user when they trigger setup mode
HOTSPOT_CONNECTION_NAME = "VedicGhadi-Hotspot"  # nmcli's internal name for this connection profile

# NetworkManager's hotspot/"shared" mode always assigns the Pi
# itself this fixed address -- this is where the phone's browser
# needs to go once connected to the hotspot.
SETUP_PAGE_URL = "http://10.42.0.1:5000"

SETTINGS_YAML_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "config", "settings.yaml"
)

_setup_mode_active = False  # guards against double-entry if Button 4 is pressed twice
_flask_started = False      # Flask's server thread only ever needs starting once per app run


def _run(cmd: list) -> subprocess.CompletedProcess:
    """
    Small helper: run a command, always through sudo, never raise on
    failure (caller checks .returncode) -- this module should log
    problems rather than crash the whole app over a network hiccup.
    """
    return subprocess.run(["sudo"] + cmd, capture_output=True, text=True, timeout=30)


def _start_hotspot() -> bool:
    """Switch the Pi's Wi-Fi into AP/hotspot mode, broadcasting HOTSPOT_SSID. Returns True on success."""
    # Clear out any leftover profile from a previous run first (errors
    # ignored -- "profile doesn't exist" is the normal, fine case).
    _run(["nmcli", "connection", "delete", HOTSPOT_CONNECTION_NAME])

    result = _run([
        "nmcli", "device", "wifi", "hotspot",
        "ifname", "wlan0",
        "con-name", HOTSPOT_CONNECTION_NAME,
        "ssid", HOTSPOT_SSID,
        "password", HOTSPOT_PASSWORD,
    ])
    if result.returncode != 0:
        print(f"[wifi_setup] Could not start hotspot: {result.stderr}")
        return False

    # CRITICAL SAFETY: nmcli's hotspot command saves a persistent
    # profile that can autoconnect on the NEXT BOOT -- which would trap
    # the Pi in hotspot mode forever instead of rejoining home Wi-Fi.
    # (Found the hard way: the hotspot switch itself worked during the
    # first real test, but nothing stopped it from coming back after a
    # reboot.) Hotspot mode must ONLY ever be entered via Button 4.
    _run(["nmcli", "connection", "modify", HOTSPOT_CONNECTION_NAME, "connection.autoconnect", "no"])

    print(f"[wifi_setup] Hotspot '{HOTSPOT_SSID}' active (password: {HOTSPOT_PASSWORD}). "
          f"Connect a phone to it, then visit {SETUP_PAGE_URL}")
    return True


def _update_location_in_settings_yaml(name: str, latitude: float, longitude: float) -> None:
    """Targeted find-and-replace of just the location block's 3 fields -- see module docstring for why."""
    with open(SETTINGS_YAML_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r'(name:\s*)"[^"]*"', f'\\1"{name}"', content, count=1)
    content = re.sub(r'(latitude:\s*)[-\d.]+', f'\\g<1>{latitude}', content, count=1)
    content = re.sub(r'(longitude:\s*)[-\d.]+', f'\\g<1>{longitude}', content, count=1)

    with open(SETTINGS_YAML_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[wifi_setup] settings.yaml location updated: {name} ({latitude}, {longitude})")


def _finish_setup_and_reboot(ssid: str, password: str, location_name: str,
                              latitude: float, longitude: float) -> None:
    """
    Runs a few seconds AFTER the success page has already been sent
    to the phone's browser (see module docstring for why the delay
    matters). Connects to the real Wi-Fi network, updates
    settings.yaml, then reboots to apply everything cleanly.
    """
    time.sleep(4)  # give the phone's browser time to actually render the success page first

    global _setup_mode_active

    # Remove the hotspot profile entirely before joining the real
    # network -- it's a one-shot, never something to keep around.
    _run(["nmcli", "connection", "delete", HOTSPOT_CONNECTION_NAME])

    print(f"[wifi_setup] Connecting to '{ssid}'...")
    result = _run(["nmcli", "device", "wifi", "connect", ssid, "password", password])
    if result.returncode != 0:
        # Can't reach the phone anymore to report this failure (the
        # hotspot may already be gone) -- logged for later diagnosis
        # over SSH instead. Reset the flag so Button 4 works again
        # for a retry instead of staying blocked until an app restart.
        print(f"[wifi_setup] Could not connect to '{ssid}': {result.stderr}")
        _setup_mode_active = False
        return

    _update_location_in_settings_yaml(location_name, latitude, longitude)

    print("[wifi_setup] Rebooting to apply everything cleanly...")
    _run(["reboot"])


# =============================================================================
# The setup form itself (Flask)
# =============================================================================

_flask_app = Flask(__name__)


@_flask_app.route("/", methods=["GET"])
def _show_form():
    # Deliberately plain, inline HTML/CSS (no separate template files
    # or static assets needed for one small form) -- kept simple on
    # purpose, this page is only ever seen briefly during setup.
    return """
    <html>
    <head>
        <title>VedicGhadi Wi-Fi Setup</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: sans-serif; max-width: 400px; margin: 40px auto; padding: 0 16px; }
            h1 { font-size: 20px; }
            label { display: block; margin-top: 16px; font-weight: bold; }
            input { width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box; }
            button { margin-top: 24px; width: 100%; padding: 12px; background: #f39c12; border: none; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>Vedic Ghadi -- Wi-Fi Setup</h1>
        <form action="/submit" method="post">
            <label>Wi-Fi Network Name (SSID)</label>
            <input type="text" name="ssid" required>

            <label>Wi-Fi Password</label>
            <input type="password" name="password" required>

            <label>Location Name</label>
            <input type="text" name="location_name" required>

            <label>Latitude</label>
            <input type="text" name="latitude" required>

            <label>Longitude</label>
            <input type="text" name="longitude" required>

            <button type="submit">Save and Connect</button>
        </form>
    </body>
    </html>
    """


@_flask_app.route("/submit", methods=["POST"])
def _handle_submit():
    ssid = request.form["ssid"]
    password = request.form["password"]
    location_name = request.form["location_name"]

    try:
        latitude = float(request.form["latitude"])
        longitude = float(request.form["longitude"])
    except ValueError:
        return "Latitude and longitude must be numbers. Go back and try again.", 400

    # Do the actual network switch + reboot on a background thread,
    # AFTER this response is sent -- see module docstring for why.
    threading.Thread(
        target=_finish_setup_and_reboot,
        args=(ssid, password, location_name, latitude, longitude),
        daemon=True,
    ).start()

    return """
    <html><body style="font-family: sans-serif; max-width: 400px; margin: 40px auto; padding: 0 16px;">
        <h1>Saved!</h1>
        <p>Vedic Ghadi is connecting to your network and will restart in a few seconds.</p>
        <p>You can close this page now.</p>
    </body></html>
    """


def enter_wifi_setup_mode() -> None:
    """
    The actual function to wire up to hardware/buttons.py's
    wifi_setup_pressed signal (replacing the placeholder). Starts
    the hotspot, then starts the Flask server on a background thread
    (Flask's app.run() blocks forever, so it can't run on the main
    Qt thread without freezing the whole UI).
    """
    global _setup_mode_active, _flask_started
    if _setup_mode_active:
        print("[wifi_setup] Already in setup mode -- ignoring repeated button press.")
        return

    if not _start_hotspot():
        return  # error already logged in _start_hotspot()

    _setup_mode_active = True

    # Flask only ever needs starting ONCE per app run -- if setup mode
    # is re-entered after a failed attempt, the server from the first
    # time is still running, and starting a second one would fail
    # trying to bind port 5000 again.
    if not _flask_started:
        _flask_started = True
        threading.Thread(
            target=lambda: _flask_app.run(host="0.0.0.0", port=5000, debug=False),
            daemon=True,
        ).start()


# =============================================================================
# Standalone test -- run directly on the Pi to test the hotspot + form
# without needing the full app: `python3 hardware/wifi_setup.py`
# =============================================================================

if __name__ == "__main__":
    print("Entering Wi-Fi Setup mode standalone...")
    enter_wifi_setup_mode()
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
