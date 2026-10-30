"""
ui/dial_preview.py  --  stand-alone preview of the whole new dial page.

Runs on the PC (needs only PyQt5; no engine, no GPIO):
    python ui/dial_preview.py                  # live, real clock
    python ui/dial_preview.py 14:30            # freeze at 14:30 today (for checking)
    python ui/dial_preview.py 14:30 empty      # no festival / eclipse -> swastik cards

EVERY VALUE BELOW IS SAMPLE DATA (typed by hand, loosely based on 27 Oct 2026).
When the page is wired to the engine these come from the engine instead.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication

from page_vedic_dial import VedicDialPage

SUNRISE = (6, 29)
SUNSET = (17, 52)

SAMPLE = {
    # captions (Hindi build)
    "cap": {
        "sunrise": "सूर्योदय", "sunset": "सूर्यास्त",
        "dinman": "दिनमान", "ratriman": "रात्रिमान",
        "moonrise": "चन्द्रोदय", "moonset": "चन्द्रास्त",
        "sun_rashi": "सूर्य राशि", "moon_rashi": "चन्द्र राशि",
        "tithi": "तिथि", "nakshatra": "नक्षत्र", "yoga": "योग", "karana": "करण",
        "till": "तक", "ist": "भारतीय मानक समय",
        "date": "दिनांक", "ayana": "अयन", "samvatsara": "संवत्सर",
        "city": "स्थान", "ritu": "ऋतु",
    },
    "sunrise": "06:29", "sunset": "17:52", "dinman": "11:23", "ratriman": "12:37",
    "moonrise": "18:37", "moonset": "07:30",
    "sun_rashi": "तुला", "moon_rashi": "मेष",
    "tithi": "द्वितीया", "nakshatra": "भरणी", "yoga": "सिद्धि", "karana": "बालव",
    "tithi_range": "27 अक्टू॰ 10:30 से 28 अक्टू॰ 06:30 तक", "tithi_end": "18:42", "nakshatra_end": "21:05", "yoga_end": "13:30", "karana_end": "07:55",
    "ritu": "शरद ऋतु", "samvatsara": "सिद्धार्थी", "ayana": "दक्षिणायन",
    "samvat": "विक्रम संवत् 2083", "masa": "कार्तिक", "paksha": "कृष्ण पक्ष",
    "weekday": "मंगलवार",
    "date": "27 अक्टूबर 2026", "city": "मुज़फ़्फ़रनगर",
}


SAMPLE_FESTIVAL = ("आज का पर्व : दीपावली", "9/10 नवम्बर")             # sample text only
SAMPLE_ECLIPSE = ("चन्द्र ग्रहण", "28 अगस्त 2026, 09:12 से 10:48 तक")    # sample text only


def register_fonts():
    """Load the bundled Devanagari font so Qt shapes Hindi correctly (without
    this Windows falls back to Arial and prints 'OpenType support missing')."""
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "fonts")
    family = "Noto Sans Devanagari"
    if os.path.isdir(fonts_dir):
        for name in sorted(os.listdir(fonts_dir)):
            if name.lower().endswith((".ttf", ".otf")):
                fid = QFontDatabase.addApplicationFont(os.path.join(fonts_dir, name))
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams and "Devanagari" in fams[0]:
                    family = fams[0]
    return family


def ghati_now(now):
    """(elapsed_ghati since sunrise, day_ghati) for the sample sun times."""
    sr = now.replace(hour=SUNRISE[0], minute=SUNRISE[1], second=0, microsecond=0)
    ss = now.replace(hour=SUNSET[0], minute=SUNSET[1], second=0, microsecond=0)
    day_min = (ss - sr).total_seconds() / 60.0
    if now < sr:                       # before sunrise: still yesterday's day
        sr -= timedelta(days=1)
    return (now - sr).total_seconds() / 60.0 / 24.0, day_min / 24.0


class PreviewPage(VedicDialPage):
    def __init__(self, frozen=None, font_family="Noto Sans Devanagari", empty=False):
        super().__init__(font_family)
        self.frozen = frozen
        self.empty = empty            # True = no festival / eclipse -> swastik cards
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)              # vipal changes every 0.4 s
        self.tick()

    def tick(self):
        now = self.frozen or datetime.now()
        e, d = ghati_now(now)
        self.set_dial(e, d)
        data = dict(SAMPLE)
        data["ist_time"] = now.strftime("%H:%M:%S")
        self.set_data(data)
        if self.empty:
            self.set_notices(None, None)
        else:
            self.set_notices(SAMPLE_FESTIVAL, SAMPLE_ECLIPSE)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    frozen = None
    if len(sys.argv) > 1:
        h, m = sys.argv[1].split(":")
        frozen = datetime.now().replace(hour=int(h), minute=int(m), second=7)
    family = register_fonts()
    w = PreviewPage(frozen, font_family=family, empty=("empty" in sys.argv[2:]))
    w.resize(1360, 768)
    w.show()
    sys.exit(app.exec_())
