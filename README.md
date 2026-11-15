# Option to hide the password on the setup card (15 Nov 2026)

New setting `setup_show_password` in config/settings.yaml:

| value | the setup card shows |
| --- | --- |
| `true` (default, also when the key is missing) | the hotspot password, exactly as before |
| `dots` | `●●●●●●●●` instead of the password (always 8 dots, the length is not given away) |
| `false` | no password step; the other steps are renumbered 1, 2, 3 |

Read once when the clock starts: restart the clock after a change.

## Files

| File | |
| --- | --- |
| ui/setup_card_text.py | NEW. The wording of the card and the option (no Qt, testable on the PC). |
| ui/main_window_hi.py | CHANGED (4 places): import, reads the setting next to idle_return_seconds, `_setup_steps()` uses the new module, header note. |
| tests/test_setup_card_text.py | NEW. 37 pytest tests. |

config/settings.yaml is NOT in the zip on purpose: the setup form edits the location in that file on each Pi,
so overwriting or committing a copy could reset a Pi's location or make `git pull` stop with a conflict.
The key is optional. To switch the option, add these lines at the END of the Pi's config/settings.yaml
(not before the `location:` block: wifi_setup.py edits the first name:/latitude:/longitude: lines):

    # Wi-Fi / location setup card (the Setup button).  Read when the clock starts: restart it after a change.
    #   setup_show_password: true    the hotspot password is shown on the card (default)
    #   setup_show_password: dots    the card shows ●●●●●●●● instead
    #   setup_show_password: false   the password step is left out of the card
    setup_show_password: dots

## One more fix in the same function

The card asked wifi_setup.py for `SETUP_URL`, but the file calls it `SETUP_PAGE_URL`, so the card always used its
built-in fallback address (the same text, so nothing was visibly wrong). It now reads `SETUP_PAGE_URL` first
(and still accepts `SETUP_URL`), so a changed address in wifi_setup.py reaches the card.

## Install and check

Copy the two files in ui/ and the test file into the project, commit, push, `git pull` on the Pi. On the PC:

    python -m pytest tests -v        # expected: 37 passed (the flask test needs: pip install flask)

On the Pi 2: add the key (value `dots`), restart the clock (sudo reboot), touch Setup. Expected: step 2 shows
`●●●●●●●●`. With `false` the card has 3 steps. Touch Setup again within 8 s to cancel before the hotspot starts.

## What was tested where

Sandbox only: all 37 tests pass; breaking the option on purpose makes tests fail; the real `_setup_steps` text from
main_window_hi.py was run with a stand-in module in all three modes; `wifi_setup._update_location_in_settings_yaml`
still saves the location in settings.yaml with the key added; also with settings.yaml without a final newline.
NOT tested: the card drawn on the real screen. Check that the `●` dots draw (the card's font is Noto Sans Devanagari;
if they show as empty boxes, say so: the dot character is one constant, DOTS_TEXT in ui/setup_card_text.py).

## Not changed (read this if hiding is for privacy)

Hiding is only on the CARD. The password `vedicghadi123` is also written in plain text in hardware/wifi_setup.py
(HOTSPOT_PASSWORD, so in git) and in the log line "Hotspot ... active (password: ...)" in data/wifi_setup.log and
on the console. If the repository is public, anyone can read it there. A per-device password (a local file, not in
git) would be the real fix; tell me if you want it.
