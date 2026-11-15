"""
tests/test_setup_card_text.py -- pytest tests of ui/setup_card_text.py (the setup card wording and the
setup_show_password option) and of config/settings.yaml with the new key.

    python -m pytest tests/test_setup_card_text.py -v

No PyQt needed.  The last tests import hardware/wifi_setup.py (needs `pip install flask`) and skip if
flask is missing.
"""
import os
import re

import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "ui"))
sys.path.insert(0, os.path.join(ROOT, "hardware"))

from setup_card_text import password_mode, setup_steps, SHOW, DOTS, HIDE, DOTS_TEXT  # noqa: E402

SSID, URL, PWD = "VedicGhadi-Setup", "http://10.42.0.1:5000", "vedicghadi123"


@pytest.mark.parametrize("value, mode", [
    (True, SHOW), ("true", SHOW), ("True", SHOW), ("yes", SHOW), ("on", SHOW), ("show", SHOW), (1, SHOW),
    (False, HIDE), ("false", HIDE), ("no", HIDE), ("off", HIDE), ("hide", HIDE), (0, HIDE),
    ("dots", DOTS), ("Dots", DOTS), (" mask ", DOTS),
    (None, SHOW), ("", SHOW), ("banana", SHOW), ([], SHOW),
])
def test_password_mode(value, mode):
    assert password_mode(value) == mode


def test_show_keeps_the_card_exactly_as_before():
    # the steps the card had before this option (copied from ui/main_window_hi.py, 14 Nov 2026)
    old = [("1", "मोबाइल में Wi-Fi खोलें और इस नेटवर्क से जुड़ें:", SSID),
           ("2", "पासवर्ड डालें:", PWD),
           ("3", "मोबाइल के ब्राउज़र में यह पता खोलें:", URL),
           ("4", "Wi-Fi और स्थान भरकर सेव करें", "")]
    assert setup_steps(SSID, URL, PWD, SHOW) == old
    assert setup_steps(SSID, URL, PWD) == old                     # SHOW is the default


def test_dots_replace_the_password_and_do_not_give_its_length_away():
    steps = setup_steps(SSID, URL, PWD, DOTS)
    assert [s[0] for s in steps] == ["1", "2", "3", "4"]
    assert steps[1] == ("2", "पासवर्ड डालें:", DOTS_TEXT)
    assert len(DOTS_TEXT) == 8 and len(PWD) != 8
    assert PWD not in repr(steps)
    assert repr(setup_steps(SSID, URL, "x", DOTS)) == repr(setup_steps(SSID, URL, "a-much-longer-password", DOTS))


def test_hide_leaves_the_password_step_out_and_renumbers():
    steps = setup_steps(SSID, URL, PWD, HIDE)
    assert [s[0] for s in steps] == ["1", "2", "3"]
    assert steps[0][2] == SSID and steps[1][2] == URL and steps[2][2] == ""
    assert PWD not in repr(steps)
    assert all("पासवर्ड" not in s[1] for s in steps)


@pytest.mark.parametrize("mode", [SHOW, DOTS, HIDE])
def test_no_password_at_all_gives_three_steps_in_every_mode(mode):
    # wifi_setup.py without a HOTSPOT_PASSWORD (open hotspot): same as before, no password step
    for pwd in (None, ""):
        assert [s[0] for s in setup_steps(SSID, URL, pwd, mode)] == ["1", "2", "3"]


# ------------------------------------------------------------------ settings.yaml
yaml = pytest.importorskip("yaml", reason="pip install pyyaml")
SETTINGS = os.path.join(ROOT, "config", "settings.yaml")

# what to add at the END of config/settings.yaml to change the option (the key is optional: without it
# the card shows the password, as before)
SNIPPET = """
# Wi-Fi / location setup card (the Setup button).  Read when the clock starts: restart it after a change.
#   setup_show_password: true    the hotspot password is shown on the card (default)
#   setup_show_password: dots    the card shows ●●●●●●●● instead
#   setup_show_password: false   the password step is left out of the card
setup_show_password: %s
"""


def _settings_text(value):
    """your real config/settings.yaml, with the snippet added at the end if it has no such key yet"""
    with open(SETTINGS, encoding="utf-8") as f:
        text = f.read()
    if "setup_show_password" in text:                                  # key already there: set its value
        return re.sub(r"(?m)^setup_show_password:.*$", "setup_show_password: %s" % value, text)
    return (text if text.endswith("\n") else text + "\n") + SNIPPET % value


def test_settings_yaml_without_the_key_means_show():
    with open(SETTINGS, encoding="utf-8") as f:
        s = yaml.safe_load(f)
    if "setup_show_password" not in s:
        assert password_mode(s.get("setup_show_password", True)) == SHOW


@pytest.mark.parametrize("text, mode", [("true", SHOW), ("false", HIDE), ("no", HIDE), ("dots", DOTS), ("off", HIDE)])
def test_yaml_spellings_of_the_option(text, mode):
    s = yaml.safe_load("setup_show_password: %s\n" % text)
    assert password_mode(s["setup_show_password"]) == mode


def test_empty_value_in_yaml_means_show():
    s = yaml.safe_load("setup_show_password:\n")
    assert s["setup_show_password"] is None and password_mode(s["setup_show_password"]) == SHOW


@pytest.mark.parametrize("value", ["true", "dots", "false"])
def test_snippet_loads_and_leaves_the_rest_of_settings_alone(value, tmp_path):
    text = _settings_text(value)
    s = yaml.safe_load(text)
    assert password_mode(s["setup_show_password"]) == {"true": SHOW, "dots": DOTS, "false": HIDE}[value]
    with open(SETTINGS, encoding="utf-8") as f:
        original = yaml.safe_load(f)
    for key in (k for k in original if k != "setup_show_password"):
        assert s[key] == original[key]


def test_wifi_setup_can_still_save_the_location_when_the_snippet_is_added(tmp_path):
    """hardware/wifi_setup.py edits the FIRST name:/latitude:/longitude: lines of settings.yaml with
    regular expressions; the added key and its comments must not get in their way."""
    pytest.importorskip("flask", reason="pip install flask (wifi_setup.py imports it)")
    import wifi_setup
    work = tmp_path / "settings.yaml"
    work.write_text(_settings_text("false"), encoding="utf-8")
    old_path = wifi_setup.SETTINGS_YAML_PATH
    wifi_setup.SETTINGS_YAML_PATH = str(work)
    wifi_setup.LOG_PATH = str(tmp_path / "wifi_setup.log")
    try:
        wifi_setup._update_location_in_settings_yaml("Meerut", 28.9845, 77.7064)
    finally:
        wifi_setup.SETTINGS_YAML_PATH = old_path
    text = work.read_text(encoding="utf-8")
    s = yaml.safe_load(text)
    assert s["location"]["name"] == "Meerut"
    assert s["location"]["latitude"] == 28.9845 and s["location"]["longitude"] == 77.7064
    assert password_mode(s["setup_show_password"]) in (HIDE, SHOW)
    assert "# default location" in text and "# auto-swap interval" in text       # the file's comments survived
