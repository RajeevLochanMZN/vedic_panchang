"""
ui/setup_card_text.py  --  the WORDING of the Wi-Fi / location setup card, and the option to hide the
hotspot password on it.  No Qt in here, so it is tested on any PC (tests/test_setup_card_text.py).

settings.yaml  setup_show_password:
    true  (default)   the password line shows the hotspot password, as before
    dots              the line shows ●●●●●●●● instead (always 8 dots: the length is not given away)
    false             the password step is left out; the other steps are renumbered

The value is read once when the clock starts (restart the clock after a change).  Anything not
understood counts as `true`, i.e. the card behaves as it always did.  This only changes what the
CARD shows; the hotspot itself, hardware/wifi_setup.py and its log are not touched.
"""

SHOW, DOTS, HIDE = "show", "dots", "hide"
DOTS_TEXT = "●●●●●●●●"

_WORDS_SHOW = {"true", "yes", "on", "show", "1"}
_WORDS_HIDE = {"false", "no", "off", "hide", "0"}
_WORDS_DOTS = {"dots", "dot", "mask", "masked", "hidden"}


def password_mode(value):
    """settings.yaml value -> SHOW | DOTS | HIDE (anything unknown -> SHOW)."""
    if value is True:
        return SHOW
    if value is False:
        return HIDE
    word = str(value).strip().lower()
    if word in _WORDS_DOTS:
        return DOTS
    if word in _WORDS_HIDE:
        return HIDE
    return SHOW


def setup_steps(ssid, url, password, mode=SHOW):
    """The numbered steps of the setup card: [(number, text, key line)], as PopupCard.show_card wants them."""
    steps = [("1", "मोबाइल में Wi-Fi खोलें और इस नेटवर्क से जुड़ें:", ssid)]
    if password and mode == SHOW:
        steps.append(("2", "पासवर्ड डालें:", password))
    elif password and mode == DOTS:
        steps.append(("2", "पासवर्ड डालें:", DOTS_TEXT))
    steps.append((str(len(steps) + 1), "मोबाइल के ब्राउज़र में यह पता खोलें:", url))
    steps.append((str(len(steps) + 1), "Wi-Fi और स्थान भरकर सेव करें", ""))
    return steps
