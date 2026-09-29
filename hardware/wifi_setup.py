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

PRE-FILLING THE FORM: by the time the phone loads the form, wlan0 is
already broadcasting the setup hotspot -- it is NOT on the home
network anymore, so "what network is active right now" can't be
asked at that point; it would just answer with the hotspot itself.
Instead, _capture_previous_wifi() runs BEFORE _start_hotspot()
switches anything, reads whatever network was active at that moment,
and caches its SSID + saved password (via `nmcli -s`, needs the
passwordless sudo rule) into the module-level _previous_wifi_ssid /
_previous_wifi_password. The form is then filled from that cache, not
a live query. Location doesn't have this problem -- settings.yaml
doesn't change during setup mode, so it's read live.

UNCHANGED SUBMISSIONS: if what's submitted is identical to the
previous Wi-Fi + current location, nothing is switched or rebooted --
the hotspot is simply torn down and the Pi rejoins the same network
it was already on. This doubles as the "discard" path: since nothing
on the Pi changes until Submit is pressed, simply closing the page
without pressing it is already a safe cancel.

LOGGING + ORDER OF OPERATIONS: every step is written to
data/wifi_setup.log (never the Wi-Fi password). The location is saved
BEFORE any network switching (it doesn't depend on the network), and
the Pi only reboots once the entered network was actually joined --
after a failed join it rejoins a known network instead of being left
stranded. See _finish_setup_and_reboot().

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
import traceback

from flask import Flask, request

# -- AP/hotspot mode settings --------------------------------------
HOTSPOT_SSID = "VedicGhadi-Setup"
HOTSPOT_PASSWORD = "vedicghadi123"  # shown to the user when they trigger setup mode
HOTSPOT_CONNECTION_NAME = "VedicGhadi-Hotspot"  # nmcli's internal name for this connection profile

# Profiles this module creates for the network the user types in are
# always named with this prefix + the SSID -- deliberately NOT the
# bare SSID, so we can never collide with (or delete, or overwrite)
# a saved network the user already had, like their home Wi-Fi.
CONNECTION_NAME_PREFIX = "VedicGhadi-Wifi-"

# NetworkManager's hotspot/"shared" mode always assigns the Pi
# itself this fixed address -- this is where the phone's browser
# needs to go once connected to the hotspot.
SETUP_PAGE_URL = "http://10.42.0.1:5000"

SETTINGS_YAML_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "config", "settings.yaml"
)

# How many times to try joining the entered network before giving up.
# Right after the hotspot is torn down the Wi-Fi scan list is often
# empty for a few seconds, so the first attempt can fail with "no
# network with that name" even though the network is right there.
CONNECT_ATTEMPTS = 3

# Everything this module does is also written here (never the Wi-Fi
# password), so a failed attempt can be diagnosed afterwards even
# when nobody was watching the terminal. Pi-generated -- keep it out
# of git (add data/wifi_setup.log to .gitignore).
LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "wifi_setup.log"
)

_setup_mode_active = False  # guards against double-entry if Button 4 is pressed twice
_flask_started = False      # Flask's server thread only ever needs starting once per app run

# Populated by _capture_previous_wifi(), just before the hotspot goes
# up -- see the module docstring's "PRE-FILLING THE FORM" note for why
# this can't just be looked up fresh when the form loads.
_previous_wifi_ssid = ""
_previous_wifi_password = ""


def _log(message: str) -> None:
    """Print a timestamped line AND append it to LOG_PATH. Logging must never be the thing that breaks the feature, so file errors are swallowed."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [wifi_setup] {message}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _run(cmd: list, timeout: int = 30) -> subprocess.CompletedProcess:
    """
    Small helper: run a command, always through sudo, and NEVER raise
    -- a timeout or any other failure comes back as a non-zero
    .returncode (124 for a timeout) with the reason in .stderr, for
    the caller to check and log. (An earlier version let
    TimeoutExpired escape, which would have silently killed the
    background thread doing the network switch.)
    """
    try:
        return subprocess.run(["sudo"] + cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, stdout="", stderr=f"timed out after {timeout}s")
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(e))


def _capture_previous_wifi() -> None:
    """
    Run ONCE, right before _start_hotspot() switches anything, so the
    setup form can show what the Pi was actually connected to. Best-
    effort -- if wlan0 isn't connected to anything (e.g. first-ever
    boot with no saved network), leaves both cached values empty
    rather than failing.
    """
    global _previous_wifi_ssid, _previous_wifi_password

    active = _run(["nmcli", "-t", "-f", "GENERAL.CONNECTION", "device", "show", "wlan0"])
    profile_name = active.stdout.strip().split(":", 1)[-1].strip()
    if not profile_name or profile_name == "--":
        _log("No active Wi-Fi connection to capture before entering setup mode.")
        return

    # Our own profiles are named "VedicGhadi-Wifi-<ssid>" -- strip the
    # prefix back off to get the plain SSID for display; any other
    # profile name IS the SSID (e.g. a network saved via the Imager).
    if profile_name.startswith(CONNECTION_NAME_PREFIX):
        ssid = profile_name[len(CONNECTION_NAME_PREFIX):]
    else:
        ssid = profile_name

    pw_result = _run(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", profile_name])
    password = pw_result.stdout.strip()

    _previous_wifi_ssid = ssid
    _previous_wifi_password = password
    _log(f"Captured previous Wi-Fi '{ssid}' for pre-filling the form.")


def _read_current_location():
    """
    Read the CURRENT location straight from settings.yaml, converted
    to degrees+minutes for pre-filling the form. Plain yaml.safe_load
    is fine here -- only WRITING with PyYAML loses comments, reading
    never touches the file.
    """
    import yaml
    try:
        with open(SETTINGS_YAML_PATH, "r", encoding="utf-8") as f:
            loc = yaml.safe_load(f)["location"]
        lat_deg = int(loc["latitude"])
        lat_min = round((loc["latitude"] - lat_deg) * 60, 2)
        lon_deg = int(loc["longitude"])
        lon_min = round((loc["longitude"] - lon_deg) * 60, 2)
        return loc["name"], lat_deg, lat_min, lon_deg, lon_min
    except Exception:
        _log("Could not read current location for pre-filling the form.")
        return "", 0, 0, 0, 0


def _start_hotspot() -> bool:
    """Switch the Pi's Wi-Fi into AP/hotspot mode, broadcasting HOTSPOT_SSID. Returns True on success."""
    _capture_previous_wifi()  # MUST happen before anything below switches the radio

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
        _log(f"Could not start hotspot: {result.stderr.strip()}")
        return False

    # CRITICAL SAFETY: nmcli's hotspot command saves a persistent
    # profile that can autoconnect on the NEXT BOOT -- which would trap
    # the Pi in hotspot mode forever instead of rejoining home Wi-Fi.
    # (Found the hard way: the hotspot switch itself worked during the
    # first real test, but nothing stopped it from coming back after a
    # reboot.) Hotspot mode must ONLY ever be entered via Button 4.
    _run(["nmcli", "connection", "modify", HOTSPOT_CONNECTION_NAME, "connection.autoconnect", "no"])

    _log(f"Hotspot '{HOTSPOT_SSID}' active (password: {HOTSPOT_PASSWORD}). "
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

    _log(f"settings.yaml location updated: {name} ({latitude}, {longitude})")


def _finish_setup_and_reboot(ssid: str, password: str, location_name: str,
                              latitude: float, longitude: float) -> None:
    """
    Runs on a background thread a few seconds AFTER the success page
    has already been sent to the phone's browser (see module docstring
    for why the delay matters).

    Order matters:
      1. Save the location FIRST -- it has nothing to do with the
         network, so a flaky Wi-Fi join must never cost the user
         their location entry. (It also proves in the log that this
         thread actually ran.)
      2. Remove the setup hotspot and let the radio settle.
      3. Create our own fresh profile for the entered network and
         bring it up, rescanning first and retrying up to
         CONNECT_ATTEMPTS times -- see CONNECT_ATTEMPTS above.
      4. Only if the join succeeded: reboot to apply everything.
         If it failed, ask NetworkManager to rejoin a known network
         so the Pi is never left stranded, and free up Button 4 to
         be pressed again.
    Every step is logged, and the whole thing is wrapped so an
    unexpected error is logged instead of silently killing the thread.
    """
    global _setup_mode_active
    try:
        time.sleep(4)  # give the phone's browser time to actually render the success page first

        try:
            _update_location_in_settings_yaml(location_name, latitude, longitude)
        except Exception:
            _log("Could not save location:\n" + traceback.format_exc())

        _log("Removing the setup hotspot...")
        _run(["nmcli", "connection", "delete", HOTSPOT_CONNECTION_NAME])
        time.sleep(5)  # let the Wi-Fi radio settle back into normal (client) mode

        # Build our OWN fresh profile with the security settings spelled
        # out, instead of `nmcli device wifi connect <ssid> password <pw>`.
        # That shortcut tries to REUSE any saved profile with the same
        # name as the SSID -- and on the real Pi, typing the home
        # network's name hit a saved profile with no security section,
        # failing every attempt with "802-11-wireless-security.key-mgmt:
        # property is missing". Our own uniquely-named profile can't
        # collide with the user's saved networks, and can't damage them
        # if the password turns out to be wrong.
        # (WPA/WPA2 password networks only -- which is what the form,
        # with its required password box, is built for.)
        profile_name = f"{CONNECTION_NAME_PREFIX}{ssid}"
        _run(["nmcli", "connection", "delete", profile_name])  # clear a leftover of OURS from an earlier attempt

        _log(f"Creating a Wi-Fi profile for '{ssid}'...")
        add = _run([
            "nmcli", "connection", "add", "type", "wifi", "ifname", "wlan0",
            "con-name", profile_name, "ssid", ssid,
            "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password,
        ])

        connected = False
        if add.returncode != 0:
            _log(f"Could not create the Wi-Fi profile: {(add.stderr or add.stdout).strip()}")
        else:
            for attempt in range(1, CONNECT_ATTEMPTS + 1):
                _log(f"Joining '{ssid}' (attempt {attempt} of {CONNECT_ATTEMPTS})...")
                _run(["nmcli", "device", "wifi", "rescan"], timeout=20)  # may be refused if scanned very recently -- fine
                time.sleep(4)  # scan results take a few seconds to arrive
                result = _run(["nmcli", "connection", "up", profile_name], timeout=60)
                if result.returncode == 0:
                    connected = True
                    break
                _log(f"Attempt {attempt} failed: {(result.stderr or result.stdout).strip()}")
                time.sleep(3)

            if not connected:
                # Wrong password or network out of range -- don't leave
                # a useless profile of ours lying around.
                _run(["nmcli", "connection", "delete", profile_name])

        if not connected:
            _log("Could not join the entered network. Asking NetworkManager to rejoin a known one instead.")
            _run(["nmcli", "device", "connect", "wlan0"], timeout=60)
            _setup_mode_active = False
            return

        _log("Connected. Rebooting to apply everything cleanly...")
        _run(["reboot"])
    except Exception:
        _log("Unexpected error:\n" + traceback.format_exc())
        _setup_mode_active = False


def _discard_and_reconnect() -> None:
    """
    The "nothing actually changed" path from _handle_submit(): just
    tear down the hotspot and let NetworkManager rejoin whatever
    network it already knew, WITHOUT creating a new profile or
    rebooting -- there's nothing new to apply.
    """
    global _setup_mode_active
    time.sleep(3)  # give the phone's browser a moment to render the response first
    _run(["nmcli", "connection", "delete", HOTSPOT_CONNECTION_NAME])
    time.sleep(5)
    _run(["nmcli", "device", "connect", "wlan0"], timeout=60)
    _setup_mode_active = False
    _log("Reconnected with no changes made.")


# =============================================================================
# The setup form itself (Flask)
# =============================================================================

def _degrees_minutes_to_decimal(degrees_text: str, minutes_text: str, max_degrees: int) -> float:
    """
    Convert a degrees + minutes pair (as typed into the setup form,
    e.g. 29 and 28 for 29 deg 28 min) into the decimal degrees the
    rest of the project uses (29.4667). Raises ValueError with a
    readable message if anything is out of range. The form only asks
    for North latitude / East longitude (positive values) -- correct
    for India, which is this project's whole scope; southern/western
    hemispheres would need a sign or hemisphere selector added.
    """
    degrees = float(degrees_text)
    minutes = float(minutes_text)
    if not (0 <= degrees <= max_degrees):
        raise ValueError(f"degrees must be between 0 and {max_degrees}")
    if not (0 <= minutes < 60):
        raise ValueError("minutes must be between 0 and 59.99")
    decimal = degrees + minutes / 60.0
    if decimal > max_degrees:
        raise ValueError(f"value is beyond {max_degrees} degrees")
    return round(decimal, 4)  # 4 decimal places is about 11 metres, plenty


_flask_app = Flask(__name__)


@_flask_app.route("/", methods=["GET"])
def _show_form():
    # Deliberately plain, inline HTML/CSS (no separate template files
    # or static assets needed for one small form) -- kept simple on
    # purpose, this page is only ever seen briefly during setup.
    #
    # PRE-FILLED with the previously-connected Wi-Fi (captured before
    # the hotspot went up -- see module docstring) and the location
    # currently in settings.yaml. Leave everything as-is and press
    # Save to keep things unchanged (no network switch or reboot
    # happens in that case -- see _handle_submit), or simply close
    # this page without pressing anything to cancel outright.
    name, lat_deg, lat_min, lon_deg, lon_min = _read_current_location()
    return f"""
    <html>
    <head>
        <title>VedicGhadi Wi-Fi Setup</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: sans-serif; max-width: 400px; margin: 40px auto; padding: 0 16px; }}
            h1 {{ font-size: 20px; }}
            .note {{ color: #555; font-size: 14px; }}
            label {{ display: block; margin-top: 16px; font-weight: bold; }}
            input {{ width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box; }}
            button {{ margin-top: 24px; width: 100%; padding: 12px; background: #f39c12; border: none; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>Vedic Ghadi -- Wi-Fi Setup</h1>
        <p class="note">Shown below is what's currently set. Change only what
        you need, then press Save -- or just close this page to leave
        everything as it is.</p>
        <form action="/submit" method="post">
            <label>Wi-Fi Network Name (SSID)</label>
            <input type="text" name="ssid" value="{_previous_wifi_ssid}" required>

            <label>Wi-Fi Password</label>
            <input type="password" name="password" value="{_previous_wifi_password}" required>

            <label>Location Name</label>
            <input type="text" name="location_name" value="{name}" required>

            <label>Latitude (North)</label>
            <input type="number" name="lat_deg" value="{lat_deg}" placeholder="Degrees, e.g. 29" min="0" max="90" step="1" required>
            <input type="number" name="lat_min" value="{lat_min}" placeholder="Minutes, e.g. 28" min="0" max="59.99" step="any" required>

            <label>Longitude (East)</label>
            <input type="number" name="lon_deg" value="{lon_deg}" placeholder="Degrees, e.g. 77" min="0" max="180" step="1" required>
            <input type="number" name="lon_min" value="{lon_min}" placeholder="Minutes, e.g. 42" min="0" max="59.99" step="any" required>

            <button type="submit">Save</button>
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
        latitude = _degrees_minutes_to_decimal(request.form["lat_deg"], request.form["lat_min"], max_degrees=90)
        longitude = _degrees_minutes_to_decimal(request.form["lon_deg"], request.form["lon_min"], max_degrees=180)
    except ValueError as e:
        return f"Please check the latitude/longitude values ({e}). Go back and try again.", 400

    # If nothing actually changed from what was pre-filled, treat this
    # the same as if the page had just been closed without pressing
    # Save -- no point reconnecting to the SAME network or rebooting
    # for a no-op. See module docstring's "UNCHANGED SUBMISSIONS".
    current_name, cur_lat_deg, cur_lat_min, cur_lon_deg, cur_lon_min = _read_current_location()
    nothing_changed = (
        ssid == _previous_wifi_ssid
        and password == _previous_wifi_password
        and location_name == current_name
        and abs(latitude - (cur_lat_deg + cur_lat_min / 60.0)) < 0.0001
        and abs(longitude - (cur_lon_deg + cur_lon_min / 60.0)) < 0.0001
    )
    if nothing_changed:
        _log("Submitted form matches the previous settings exactly -- nothing to do, just reconnecting.")
        threading.Thread(target=_discard_and_reconnect, daemon=True).start()
        return """
        <html><body style="font-family: sans-serif; max-width: 400px; margin: 40px auto; padding: 0 16px;">
            <h1>No changes made</h1>
            <p>Nothing was different from before, so Vedic Ghadi is just reconnecting -- no restart needed.</p>
            <p>You can close this page now.</p>
        </body></html>
        """

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
        _log("Already in setup mode -- ignoring repeated button press.")
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
