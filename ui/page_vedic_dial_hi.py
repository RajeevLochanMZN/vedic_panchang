"""
ui/page_vedic_dial_hi.py  --  the NEW dial Home page, LIVE (Hindi build).

VedicDialPage (page_vedic_dial.py) only DISPLAYS.  This class feeds it from the
real engine, using the same engine functions and the same Hindi tables as
page_home_hi.py / page_panchang_hi.py, so every value agrees with the old pages.

REFRESH RATES (same idea as page_home_hi.py)
    100 ms   dial hand + ghati:pal:vipal digits      (cheap)
      1 s    IST digital clock
     60 s    everything from the engine (tithi, nakshatra, sun/moon times ...)
      1 h    eclipse card (+ festival cards when the hour or the date changes)
      5 s    next page of the festival card, when there are several

IMPORTANT: an error in any one refresh is printed and skipped -- it never stops
the clock.  Look at /dev/shm/vedicghadi.log if a value stays "...".

ASSUMPTIONS (flagged because the engine files were not all available):
  * muhurta.py exports DAY_MUHURTA_NAMES, NIGHT_MUHURTA_NAMES, DAY_PAHAR_NAMES,
    NIGHT_PAHAR_NAMES (named in translations_hi.py's comments).  If not, the dial
    falls back to its built-in names.
  * the dicts from get_nakshatra_details / get_yoga_details / get_karana_details /
    get_chandra_rashi_details / get_surya_rashi_details have "name" and "end_ist"
    ('YYYY-MM-DD HH:MM:SS IST'), as used by page_panchang_hi.py.
"""
import os
import re
import sys
import traceback
import calendar
from datetime import datetime, timedelta, timezone

from PyQt5.QtCore import QTimer

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "engine"))

from ephemeris import datetime_to_julday
from panchang import get_tithi_details, get_nakshatra_details, get_yoga_details, get_karana_details
from rashi import get_chandra_rashi_details, get_surya_rashi_details
from masa import (get_purnimanta_masa_name, get_paksha, get_vikram_samvat_year,
                  get_samvatsara_name, get_ritu, get_ayana)
from time_systems import get_ist, get_vara
from sun_times import (get_sun_times_details, get_local_midnight_jd_ut, get_sunrise_jd,
                       get_moonrise_jd, get_moonset_jd)
from muhurta import get_muhurta_details, get_brahma_muhurta
from config_loader import get_location, load_settings
from eclipse_banner import get_eclipse_display_info

from page_vedic_dial import VedicDialPage
from city_names_hi import city_hi
from translations_hi import (
    HEADINGS_HI, PHRASE_TILL, PHRASE_TO, LABEL_ABHIJIT, LABEL_ECLIPSE_WORD,
    CAPTION_GHATI, CAPTION_PAL, CAPTION_VIPAL,
    MONTH_HI, translate_value, translate_masa, translate_weekday, translate_month,
    translate_month_abbr, translate_location, translate_eclipse_type,
    hi_date_short, get_devanagari_font_family,
)

# festival engine (new): every festival is shown on every date its tithi covers
from festival_vyapti import PiAdapter, tithi_span
from festival_span import SpanResolver, card_pages

IST_OFFSET = timedelta(hours=5, minutes=30)
MONTHS_FULL_HI = [MONTH_HI[calendar.month_name[i]] for i in range(1, 13)]   # जनवरी ... दिसंबर


# ------------------------------------------------------------------ helpers
def _parse_ist(s):
    """'YYYY-MM-DD HH:MM:SS IST' -> naive datetime (IST)."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S IST")


def _hhmm(ist_string):
    return _parse_ist(ist_string).strftime("%H:%M")


def _duration_hhmm(text):
    """'11h 23m 12s' -> '11:23'."""
    m = re.match(r"\s*(\d+)h\s+(\d+)m", text)
    return "%02d:%02d" % (int(m.group(1)), int(m.group(2))) if m else text


def _jd_to_hhmm(jd_ut):
    import swisseph as swe
    y, mo, d, h = swe.revjul(jd_ut)
    dt = datetime(y, mo, d, tzinfo=timezone.utc) + timedelta(hours=h) + IST_OFFSET
    return dt.strftime("%H:%M")


def _end_text(end_ist, now_ist):
    """'18:42' when it ends today, else '29 नव 06:30' (the page appends 'तक')."""
    e = _parse_ist(end_ist)
    if e.date() == now_ist.date():
        return e.strftime("%H:%M")
    return "%d %s %s" % (e.day, translate_month_abbr(e.strftime("%b")), e.strftime("%H:%M"))


def _period_text(start_jd, end_jd):
    """'9 नव 10:30 से 10 नव 06:30 तक' for the tithi line of the right panel."""
    def f(jd):
        import swisseph as swe
        y, mo, d, h = swe.revjul(jd)
        dt = datetime(y, mo, d, tzinfo=timezone.utc) + timedelta(hours=h) + IST_OFFSET
        return "%d %s %s" % (dt.day, translate_month_abbr(dt.strftime("%b")), dt.strftime("%H:%M"))
    return "%s %s %s %s" % (f(start_jd), PHRASE_TO, f(end_jd), PHRASE_TILL)


def _eclipse_range(start_short, end_short):
    """'28 Aug 09:12:00' + '28 Aug 10:48:00' -> '28 अग 09:12 से 10:48 तक'
    (no seconds; the date is written once when both are on the same day)."""
    s, e = start_short.split(" ", 2), end_short.split(" ", 2)
    if len(s) != 3 or len(e) != 3:
        return "%s %s %s %s" % (hi_date_short(start_short), PHRASE_TO, hi_date_short(end_short), PHRASE_TILL)
    ms, me = translate_month_abbr(s[1]), translate_month_abbr(e[1])
    if s[:2] == e[:2]:
        return "%s %s %s %s %s %s" % (s[0], ms, s[2][:5], PHRASE_TO, e[2][:5], PHRASE_TILL)
    return "%s %s %s %s %s %s %s %s" % (s[0], ms, s[2][:5], PHRASE_TO, e[0], me, e[2][:5], PHRASE_TILL)


NOT_VISIBLE_SHORT = "यहाँ दिखाई नहीं देगा"


def _ghati_of(dt_ist, sunrise_ist):
    """Ghati since sunrise (0..60) of an IST datetime."""
    return ((dt_ist - sunrise_ist).total_seconds() / 60.0 / 24.0) % 60.0


class PageVedicDialHi(VedicDialPage):
    def __init__(self):
        self.font_family = get_devanagari_font_family()
        super().__init__(font_family=self.font_family)

        self.lat, self.lon = get_location()
        self.location_name = load_settings().get("location", {}).get("name", "")
        # Hindi name if the city is in config/cities_hi.yaml (spelling-tolerant), else as typed
        self.city_text = city_hi(self.location_name, self.lat, self.lon)

        self._sun = None              # sun details of the CURRENT panchang day
        self._data = None             # last good data dict for set_data()
        self._banner_override = None
        self._fest_key = None
        self._fest_pages = []
        self._fest_idx = 0
        self._eclipse = None

        self._load_dial_names()

        # timers ---------------------------------------------------------
        self.dial_timer = QTimer(self)
        self.dial_timer.timeout.connect(self._tick_dial)
        self.dial_timer.start(100)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_clock)
        self.clock_timer.start(1000)

        self.slow_timer = QTimer(self)
        self.slow_timer.timeout.connect(self._update_slow)
        self.slow_timer.start(60 * 1000)

        self.eclipse_timer = QTimer(self)
        self.eclipse_timer.timeout.connect(self._update_eclipse)
        self.eclipse_timer.start(60 * 60 * 1000)

        self.rotate_timer = QTimer(self)
        self.rotate_timer.timeout.connect(self._rotate_festival)
        self.rotate_timer.start(5000)

        self._update_slow()
        self._update_eclipse()
        self._tick_dial()

    # ------------------------------------------------------------ dial names
    def _load_dial_names(self):
        labels = {"sunrise": HEADINGS_HI["sunrise"], "sunset": HEADINGS_HI["sunset"],
                  "abhijit": LABEL_ABHIJIT, "brahma": HEADINGS_HI["brahma"],
                  "ghati": CAPTION_GHATI, "pal": CAPTION_PAL, "vipal": CAPTION_VIPAL}
        muhurta_names = pahar_names = None
        try:
            import muhurta as m
            muhurta_names = [translate_value("muhurta", n)
                             for n in list(m.DAY_MUHURTA_NAMES) + list(m.NIGHT_MUHURTA_NAMES)]
            pahar_names = [translate_value("pahar", n)
                           for n in list(m.DAY_PAHAR_NAMES) + list(m.NIGHT_PAHAR_NAMES)]
            if len(muhurta_names) != 30 or len(pahar_names) != 8:
                raise ValueError("unexpected name list lengths %d / %d"
                                 % (len(muhurta_names), len(pahar_names)))
        except Exception:
            print("[dial] muhurta/pahar name lists not found in muhurta.py -- "
                  "using the dial's built-in names")
            traceback.print_exc()
            muhurta_names = pahar_names = None
        self.dial.set_names(muhurta_names, pahar_names, labels)

    # ------------------------------------------------------------ fast: dial
    def _active_sun(self, now_ist, jd_now):
        """Sun details of the current PANCHANG day (sunrise to next sunrise): before
        today's sunrise that is still yesterday's day."""
        today = get_sun_times_details(now_ist, self.lat, self.lon)
        if jd_now < today["sunrise_jd"]:
            return get_sun_times_details(now_ist - timedelta(days=1), self.lat, self.lon)
        return today

    def _tick_dial(self):
        try:
            if self._sun is None:
                return
            jd_now = datetime_to_julday(datetime.now(timezone.utc))
            sr, ss = self._sun["sunrise_jd"], self._sun["sunset_jd"]
            self.set_dial((jd_now - sr) * 60.0, (ss - sr) * 60.0)     # 1 day = 60 ghati
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------- 1 s: clock
    def _tick_clock(self):
        try:
            if self._data is None:
                return
            now_ist = get_ist(datetime.now(timezone.utc))
            self._data["ist_time"] = now_ist.strftime("%H:%M:%S")
            self.set_data(self._data)
            self._apply_banner()
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------ 60 s: engine
    def _update_slow(self):
        try:
            now_utc = datetime.now(timezone.utc)
            now_ist = get_ist(now_utc)
            jd_now = datetime_to_julday(now_utc)

            self._sun = sun = self._active_sun(now_ist, jd_now)
            sunrise_jd, sunset_jd = sun["sunrise_jd"], sun["sunset_jd"]

            # --- panchang values -------------------------------------------
            tithi = get_tithi_details(jd_now)
            nak = get_nakshatra_details(jd_now)
            yoga = get_yoga_details(jd_now)
            kar = get_karana_details(jd_now)
            moon_r = get_chandra_rashi_details(jd_now)
            sun_r = get_surya_rashi_details(jd_now)

            vara = get_vara(now_ist)
            vikram_year = get_vikram_samvat_year(jd_now)
            masa_hi = translate_masa(get_purnimanta_masa_name(jd_now))
            paksha_hi = translate_value("paksha", get_paksha(jd_now)) + " पक्ष"

            # tithi period with dates -- from the same engine function the festivals use
            adapter = PiAdapter(now_ist, self.lat, self.lon)
            t_start, t_end = tithi_span(adapter, jd_now)

            # --- moon times ----------------------------------------------------
            midnight_jd = get_local_midnight_jd_ut(now_ist)
            moonrise = _jd_to_hhmm(get_moonrise_jd(midnight_jd, self.lat, self.lon))
            moonset = _jd_to_hhmm(get_moonset_jd(midnight_jd, self.lat, self.lon))

            date_text = "%d %s %d" % (now_ist.day, translate_month(now_ist.strftime("%B")), now_ist.year)

            data = {
                "cap": {
                    "ist": "भारतीय मानक समय", "date": "दिनांक",
                    "sunrise": HEADINGS_HI["sunrise"], "sunset": HEADINGS_HI["sunset"],
                    "dinman": "दिनमान", "ratriman": "रात्रिमान",
                    "moonrise": HEADINGS_HI["moonrise"], "moonset": HEADINGS_HI["moonset"],
                    "sun_rashi": HEADINGS_HI["surya_rashi"], "moon_rashi": HEADINGS_HI["chandra_rashi"],
                    "tithi": HEADINGS_HI["tithi"], "nakshatra": HEADINGS_HI["nakshatra"],
                    "yoga": HEADINGS_HI["yoga"], "karana": HEADINGS_HI["karana"],
                    "ayana": HEADINGS_HI["ayana"], "samvatsara": HEADINGS_HI["samvatsara"],
                    "till": PHRASE_TILL, "city": "", "ritu": "",
                },
                "ist_time": now_ist.strftime("%H:%M:%S"),
                "date": date_text,
                "sunrise": _hhmm(sun["sunrise_ist"]), "sunset": _hhmm(sun["sunset_ist"]),
                "dinman": _duration_hhmm(sun["dinman"]), "ratriman": _duration_hhmm(sun["ratriman"]),
                "moonrise": moonrise, "moonset": moonset,
                "sun_rashi": translate_value("rashi", sun_r["name"]),
                "moon_rashi": translate_value("rashi", moon_r["name"]),
                "tithi": translate_value("tithi", tithi["name"]),
                "tithi_range": _period_text(t_start, t_end),
                "nakshatra": translate_value("nakshatra", nak["name"]),
                "nakshatra_end": _end_text(nak["end_ist"], now_ist),
                "yoga": translate_value("yoga", yoga["name"]),
                "yoga_end": _end_text(yoga["end_ist"], now_ist),
                "karana": translate_value("karana", kar["name"]),
                "karana_end": _end_text(kar["end_ist"], now_ist),
                "samvat": "%s %d" % (HEADINGS_HI["vikram_samvat"], vikram_year),
                "masa": masa_hi, "paksha": paksha_hi,
                "weekday": translate_value("vara", vara),
                "ritu": translate_value("ritu", get_ritu(jd_now)) + " ऋतु",
                "samvatsara": translate_value("samvatsara", get_samvatsara_name(vikram_year)),
                "ayana": translate_value("ayana", get_ayana(jd_now)),
                "city": self.city_text,
            }
            data["cap"]["till"] = PHRASE_TILL
            self._data = data
            self.set_data(data)
            self._apply_banner()

            # --- Abhijit / Brahma arcs on the dial ---------------------------------
            self._update_marked_spans(sun, jd_now, sunrise_jd, sunset_jd)

            # --- festivals (rarely changes: recompute when the hour changes) ------
            self._update_festivals(now_ist)
        except Exception:
            traceback.print_exc()

    def _update_marked_spans(self, sun, jd_now, sunrise_jd, sunset_jd):
        try:
            sr_ist = _parse_ist(sun["sunrise_ist"])
            next_sunrise_jd = get_sunrise_jd(sunset_jd, self.lat, self.lon)
            muhurta = get_muhurta_details(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)
            a0 = _ghati_of(_parse_ist(muhurta["abhijit_start_ist"]), sr_ist)
            a1 = _ghati_of(_parse_ist(muhurta["abhijit_end_ist"]), sr_ist)
            brahma = get_brahma_muhurta(sunrise_jd)
            b0 = _ghati_of(_parse_ist(brahma["start_ist"]), sr_ist)
            b1 = _ghati_of(_parse_ist(brahma["end_ist"]), sr_ist)
            if b1 < b0:
                b1 += 60.0
            self.set_marked_spans((a0, a1), (b0, b1))
        except Exception:
            print("[dial] could not read Abhijit / Brahma muhurta -- dial uses its defaults")
            traceback.print_exc()

    # ------------------------------------------------------------- festivals
    def _update_festivals(self, now_ist):
        key = (now_ist.date(), now_ist.hour)
        if key == self._fest_key:
            return
        self._fest_key = key
        try:
            from festivals import load_festivals, get_todays_festivals
            festivals = load_festivals()
            resolver = SpanResolver(PiAdapter(now_ist, self.lat, self.lon))
            pages = card_pages(resolver, festivals, now_ist.date(),
                               name_hi=lambda n: translate_value("festival", n),
                               months_hi=MONTHS_FULL_HI)
            # Sankranti festivals stay with the old engine (one date, no tithi)
            sun = get_sun_times_details(now_ist, self.lat, self.lon)
            for f in get_todays_festivals(sun["sunrise_jd"], sun["sunrise_jd"] - 1.0):
                if f.get("rule") == "sankranti":
                    pages.append(("आज का पर्व : " + translate_value("festival", f["name"]), ""))
            self._fest_pages = pages[:4]
            self._fest_idx = 0
            self._show_festival()
        except Exception:
            traceback.print_exc()

    def _show_festival(self):
        if self._fest_pages:
            self.set_notices(festival=self._fest_pages[self._fest_idx % len(self._fest_pages)],
                             eclipse=self._eclipse)
        else:
            self.set_notices(festival=None, eclipse=self._eclipse)

    def _rotate_festival(self):
        if len(self._fest_pages) > 1:
            self._fest_idx = (self._fest_idx + 1) % len(self._fest_pages)
            self._show_festival()

    # --------------------------------------------------------------- eclipse
    def _update_eclipse(self):
        try:
            jd_now = datetime_to_julday(datetime.now(timezone.utc))
            info = get_eclipse_display_info(jd_now, self.lat, self.lon, self.location_name)
            if info is None:
                self._eclipse = None
            else:
                title = "%s %s" % (translate_eclipse_type(info["type"]), LABEL_ECLIPSE_WORD)
                detail = _eclipse_range(info["start_short"], info["end_short"])
                if info.get("visible_at_max") is False:
                    detail += " · " + NOT_VISIBLE_SHORT
                self._eclipse = (title, detail)
            self._show_festival()
        except Exception:
            traceback.print_exc()

    # ---------------------------------------------------------- shutdown text
    def show_message(self, text):
        """Temporarily replace the banner text (e.g. the shutdown message);
        show_message(None) restores it."""
        self._banner_override = text
        self._apply_banner()

    def _apply_banner(self):
        if self._banner_override:
            self.banner.set_lines(self._banner_override, [])


# =============================================================================
# Standalone test (works on the PC -- needs no GPIO):   python ui/page_vedic_dial_hi.py
# =============================================================================
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    from ephemeris import init_ephemeris

    init_ephemeris(ephe_path=os.path.join(_HERE, "..", "data", "ephe"))
    app = QApplication(sys.argv)
    page = PageVedicDialHi()
    size = app.primaryScreen().availableGeometry().size()
    page.resize(size.width(), size.height())
    page.setWindowTitle("New dial page (Hindi) (standalone test)")
    page.show()
    sys.exit(app.exec_())
