"""
tests/test_festival_span.py -- pytest tests of engine/festival_span.py (the ONE-DATE festival rule
decided on 12 Nov 2026):

    a festival is held on ONE date: the day its tithi covers the most hours of DAYTIME
    (sunrise to sunset).  Ties (under a minute): the earlier date.  A tithi with no daytime at all:
    the date it starts.  tithi_and_weekday festivals: the weekday date inside the tithi's WHOLE
    span.  Holi = the day after Holika Dahan.

Run from the project folder (venv active):

    pip install pytest pyswisseph pyyaml
    python -m pytest tests/test_festival_span.py -v

Two parts:
  1. FAKE SKY tests -- a hand-made sky (12-hour days, sunrise 06:00, sunset 18:00, tithis that
     start and end exactly where the test says).  Need nothing installed except pytest.
  2. REAL SKY tests -- the Muzaffarnagar sky of tests/swiss_sky.py (pyswisseph).  Skipped when
     pyswisseph or pyyaml is missing.
"""
import os
import sys
from datetime import date, datetime, timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "engine"))

from festival_span import SpanResolver, card_pages, tithi_period_text  # noqa: E402


# ====================================================================== fake sky
NAMES = ["Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar"]


class FakeSky:
    """Hand-made sky.  Day 0 = a local (IST) calendar day; every day has sunrise 06:00 and
    sunset 18:00.  `periods` = [(start_hour, tithi, month)], hours counted from the local
    midnight that starts day 0 (so 36.0 = day 1 at 12:00).  Each period lasts until the next."""
    TZ = 5.5
    BASE_DAY = 2461000

    def __init__(self, periods, base_weekday=6):
        self.periods = sorted(periods)
        self.base_weekday = base_weekday                     # 6 = day 0 is a Ravivar (Sunday)
        self.midnight0 = self.BASE_DAY - 0.5 - self.TZ / 24.0

    def _period(self, jd):
        h = (jd - self.midnight0) * 24.0
        cur = self.periods[0]
        for p in self.periods:
            if p[0] <= h:
                cur = p
        return cur

    def tithi_at(self, jd):
        return self._period(jd)[1]

    def month_at(self, jd):
        return self._period(jd)[2]

    def sun_times(self, k):
        m = self.midnight0 + k
        return m + 6.0 / 24.0, m + 18.0 / 24.0

    def weekday_of(self, k):
        return NAMES[(self.base_weekday + k) % 7]


def sky(start_h, end_h, tithi=30, month=7, **kw):
    """A sky in which `tithi` (of `month`) runs from hour start_h to hour end_h; the tithis
    before and after it are the neighbouring numbers."""
    prev, nxt = (tithi - 2) % 30 + 1, tithi % 30 + 1
    return FakeSky([(-200.0, prev, month), (start_h, tithi, month), (end_h, nxt, month)], **kw)


def F(name, tithi, month=None, rule="tithi_at_sunrise", **kw):
    f = {"id": name.lower().replace(" ", "_"), "name": name, "rule": rule, "tithi": tithi}
    if month is not None:
        f["lunar_month"] = month
    f.update(kw)
    return f


DIWALI = F("Diwali", 30, 7)


def days_of(resolver, festivals, name, ks=range(-3, 6)):
    """Day indexes (0 = day 0 of the sky) on which the festival `name` is held."""
    return [k for k in ks if name in [e["festival"]["name"] for e in resolver.active_on(festivals, k)]]


# ------------------------------------------------------------ ONE date, most daytime
def test_tithi_with_more_daytime_on_first_date_is_held_on_first_date():
    # Amavasya 11:00 day 0 -> 12:00 day 1.  Daytime: day 0 = 7 h, day 1 = 6 h  -> day 0
    r = SpanResolver(sky(11.0, 36.0))
    assert days_of(r, [DIWALI], "Diwali") == [0]


def test_tithi_with_more_daytime_on_second_date_is_held_on_second_date():
    # Amavasya 15:00 day 0 -> 15:00 day 1.  Daytime: day 0 = 3 h, day 1 = 9 h  -> day 1
    r = SpanResolver(sky(15.0, 39.0))
    assert days_of(r, [DIWALI], "Diwali") == [1]


def test_festival_is_active_on_its_date_only():
    r = SpanResolver(sky(11.0, 36.0))
    assert [e["festival"]["name"] for e in r.active_on([DIWALI], 0)] == ["Diwali"]
    assert r.active_on([DIWALI], 1) == []
    assert r.active_on([DIWALI], -1) == []
    entry = r.active_on([DIWALI], 0)[0]
    assert entry["tithi_days"] == [0]                    # ONE date, not the old two-date list


def test_tithi_over_three_dates_is_held_on_the_middle_date():
    # 20:00 day 0 -> 05:00 day 2: touches three dates; day 0 and day 2 have no daytime, day 1 12 h
    r = SpanResolver(sky(20.0, 53.0))
    assert days_of(r, [DIWALI], "Diwali") == [1]


# -------------------------------------------------------------------------- ties
def test_exact_tie_takes_the_earlier_date():
    # 12:00 day 0 -> 12:00 day 1: 6 h on each date
    r = SpanResolver(sky(12.0, 36.0))
    assert days_of(r, [DIWALI], "Diwali") == [0]


def test_difference_under_a_minute_counts_as_a_tie():
    # day 0 gets 6 h, day 1 gets 6 h minus 20 s (ends 11:59:40): earlier date
    r = SpanResolver(sky(12.0, 36.0 - 20.0 / 3600.0))
    assert days_of(r, [DIWALI], "Diwali") == [0]
    # day 1 gets 6 h plus 20 s: still a tie (under a minute), still the earlier date
    r = SpanResolver(sky(12.0, 36.0 + 20.0 / 3600.0))
    assert days_of(r, [DIWALI], "Diwali") == [0]


def test_difference_of_two_minutes_is_not_a_tie():
    # day 1 gets 6 h 02 min, day 0 gets 6 h: the later date wins
    r = SpanResolver(sky(12.0, 36.0 + 2.0 / 60.0))
    assert days_of(r, [DIWALI], "Diwali") == [1]


# ------------------------------------------------------------ tithi with no daytime
def test_tithi_entirely_in_a_night_is_held_on_its_start_date():
    # 19:00 day 0 -> 04:00 day 1: after sunset and before sunrise, no daytime at all
    r = SpanResolver(sky(19.0, 28.0))
    assert days_of(r, [DIWALI], "Diwali") == [0]


def test_tithi_entirely_in_the_small_hours_is_held_on_its_start_date():
    # 00:30 day 1 -> 05:00 day 1: both ends on date 1, no daytime
    r = SpanResolver(sky(24.5, 29.0))
    assert days_of(r, [DIWALI], "Diwali") == [1]


# --------------------------------------------------------------------- month check
def test_wrong_lunar_month_is_not_held():
    r = SpanResolver(sky(11.0, 36.0, month=8))           # Kartik, not Ashwin
    assert days_of(r, [DIWALI], "Diwali") == []


def test_adhik_month_is_skipped():
    r = SpanResolver(sky(11.0, 36.0, month=0))           # month_at() gives 0 for Adhik / Kshaya
    assert days_of(r, [DIWALI], "Diwali") == []


# --------------------------------------------------------------- tithi_and_weekday
SOMAVATI = F("Somavati Amavasya", 30, rule="tithi_and_weekday", vara="Somvar")
SHANI = F("Shani Amavasya", 30, rule="tithi_and_weekday", vara="Shanivar")


def test_weekday_festival_uses_the_whole_span_not_the_most_daytime_date():
    # Amavasya 11:00 day 0 -> 12:00 day 1.  Diwali is on day 0 (more daytime) but day 1 is a
    # Somvar, so Somavati Amavasya is on day 1.
    r = SpanResolver(sky(11.0, 36.0, base_weekday=6))    # day 0 Ravivar, day 1 Somvar
    fs = [DIWALI, SOMAVATI, SHANI]
    assert days_of(r, fs, "Diwali") == [0]
    assert days_of(r, fs, "Somavati Amavasya") == [1]
    assert days_of(r, fs, "Shani Amavasya") == []


def test_weekday_festival_on_a_date_with_no_daytime_of_the_tithi():
    # Amavasya 20:00 day 0 -> 05:00 day 2.  Diwali on day 1; day 2 is a Somvar although the
    # tithi has no daytime on it, so Somavati Amavasya is on day 2.
    r = SpanResolver(sky(20.0, 53.0, base_weekday=5))    # day 0 Shanivar, 1 Ravivar, 2 Somvar
    fs = [DIWALI, SOMAVATI, SHANI]
    assert days_of(r, fs, "Diwali") == [1]
    assert days_of(r, fs, "Somavati Amavasya") == [2]
    assert days_of(r, fs, "Shani Amavasya") == [0]


def test_weekday_festival_not_held_when_no_date_of_the_tithi_has_the_weekday():
    r = SpanResolver(sky(11.0, 36.0, base_weekday=1))    # Mangalvar, Budhvar
    assert days_of(r, [SOMAVATI, SHANI], "Somavati Amavasya") == []
    assert days_of(r, [SOMAVATI, SHANI], "Shani Amavasya") == []


# ------------------------------------------------------------------------- Holi
HOLIKA = F("Holika Dahan", 15, 12)
HOLI = F("Holi", 15, 12)


def test_holi_is_the_day_after_holika_dahan():
    r = SpanResolver(sky(11.0, 36.0, tithi=15, month=12))     # Purnima: Holika Dahan on day 0
    fs = [HOLIKA, HOLI]
    assert days_of(r, fs, "Holika Dahan") == [0]
    assert days_of(r, fs, "Holi") == [1]


def test_holi_follows_holika_dahan_when_that_is_on_the_second_date():
    r = SpanResolver(sky(15.0, 39.0, tithi=15, month=12))     # Holika Dahan on day 1
    fs = [HOLIKA, HOLI]
    assert days_of(r, fs, "Holika Dahan") == [1]
    assert days_of(r, fs, "Holi") == [2]


def test_holi_is_not_held_by_the_tithi_rule_itself():
    # Holi has tithi 15 / month 12 in festivals.yaml like Holika Dahan, but without Holika Dahan
    # in the list it must not appear on its own
    r = SpanResolver(sky(11.0, 36.0, tithi=15, month=12))
    assert days_of(r, [HOLI], "Holi") == []


# ------------------------------------------------------------------- eclipse shift
def test_eclipse_shift_moves_the_date():
    r = SpanResolver(sky(11.0, 36.0), eclipse_shift=lambda k: 1 if k == 0 else k)
    assert days_of(r, [DIWALI], "Diwali") == [1]


# ------------------------------------------------------------------------ the card
def _two_day_sky():
    # Amavasya 11:00 day 0 -> 12:00 day 1 (Diwali, day 0); Pratipada of Kartik 12:00 day 1 ->
    # 10:00 day 2 (Govardhan Puja: 6 h on day 1, 4 h on day 2 -> day 1)
    return FakeSky([(-200.0, 29, 7), (11.0, 30, 7), (36.0, 1, 8), (58.0, 2, 8)])


GOVARDHAN = F("Govardhan Puja", 1, 8)


def test_card_shows_todays_festival_without_dates_line_and_next_festival_with_its_date():
    pages = card_pages(SpanResolver(_two_day_sky()), [DIWALI, GOVARDHAN], date(2026, 11, 8))
    assert pages == [("आज का पर्व : Diwali", ""),
                     ("अगला पर्व : Govardhan Puja", "9 नवम्बर")]


def test_card_uses_the_name_translation():
    pages = card_pages(SpanResolver(_two_day_sky()), [DIWALI, GOVARDHAN], date(2026, 11, 8),
                       name_hi=lambda n: {"Diwali": "दीपावली", "Govardhan Puja": "गोवर्धन पूजा"}[n])
    assert pages == [("आज का पर्व : दीपावली", ""), ("अगला पर्व : गोवर्धन पूजा", "9 नवम्बर")]


def test_card_is_empty_when_nothing_is_near():
    # no festival of this month in the list: the card shows the swastik (empty list)
    assert card_pages(SpanResolver(_two_day_sky()), [F("Gita Jayanti", 11, 9)], date(2026, 11, 8)) == []


def test_card_next_festival_is_not_repeated_when_it_is_today():
    # Pratipada festival on day 0 and Diwali on day 0: both "today", no "अगला पर्व" for them
    r = SpanResolver(FakeSky([(-200.0, 29, 7), (8.0, 30, 7), (9.0, 1, 8), (60.0, 2, 8)]))
    pages = card_pages(r, [DIWALI, GOVARDHAN], date(2026, 11, 8))
    assert [p[0] for p in pages].count("आज का पर्व : Govardhan Puja") <= 1
    assert all("अगला पर्व : Diwali" != p[0] for p in pages)


# -------------------------------------------------------------- tithi line (panel)
def _ist_to_jd(y, m, d, hh, mm, ss=0):
    return 2451545.0 + (datetime(y, m, d, hh, mm, ss) - timedelta(hours=5, minutes=30)
                        - datetime(2000, 1, 1, 12)).total_seconds() / 86400.0


def test_tithi_period_text():
    # the times are given 30 s past the minute: the text shows hours and minutes only (seconds are
    # cut off, not rounded), and a time exactly ON a minute can come out one minute early because
    # of floating-point noise in the Julian Day
    s, e = _ist_to_jd(2026, 11, 9, 10, 30, 30), _ist_to_jd(2026, 11, 10, 6, 30, 30)
    assert tithi_period_text(s, e) == "9 नव॰ 10:30 से 10 नव॰ 06:30 तक"


# ================================================================= REAL SKY (Muzaffarnagar)
swe = pytest.importorskip("swisseph", reason="pip install pyswisseph for the real-sky tests")
yaml = pytest.importorskip("yaml", reason="pip install pyyaml for the real-sky tests")
from swiss_sky import SwissAdapter  # noqa: E402

with open(os.path.join(HERE, "..", "config", "festivals.yaml"), encoding="utf-8") as _f:
    FESTIVALS = yaml.safe_load(_f)["festivals"]


def _month_dates(year, month, days):
    """{festival id: [dates it is held on]} for the days of one month, by the real sky."""
    first = date(year, month, 1)
    r = SpanResolver(SwissAdapter(first))
    held = {}
    for k in range(days):
        for e in r.active_on(FESTIVALS, k):
            held.setdefault(e["festival"]["id"], []).append(first + timedelta(days=k))
    return held


@pytest.fixture(scope="module")
def november():
    return _month_dates(2026, 11, 30)


@pytest.fixture(scope="module")
def march():
    return _month_dates(2026, 3, 31)


def test_real_sky_no_festival_is_held_on_two_dates(november):
    twice = {i: d for i, d in november.items() if len(d) != 1}
    assert not twice, "a festival is held on more than one date: %r" % (twice,)


@pytest.mark.parametrize("fid, expected", [
    ("dhanteras", date(2026, 11, 6)),
    ("narak_chaturdashi", date(2026, 11, 7)),
    ("govardhan_puja", date(2026, 11, 10)),
    ("bhai_dooj", date(2026, 11, 11)),
    ("chhath_puja", date(2026, 11, 15)),
    ("skanda_sashti", date(2026, 11, 15)),
])
def test_real_sky_diwali_week_2026(november, fid, expected):
    assert november[fid] == [expected]


def test_real_sky_diwali_2026_is_8_november_by_a_narrow_margin(november):
    """CLOSE CALL: Amavasya covers 6.0 h of daytime on 8 Nov against 5.9 h on 9 Nov (about
    6 minutes).  If this test fails on another machine but the rest pass, suspect a difference
    in how sunrise/sunset are computed (refraction, disc edge, ephemeris) before suspecting the
    rule.  The Pi clock itself was checked against this date on 12 Nov 2026."""
    assert november["diwali"] == [date(2026, 11, 8)]


def test_real_sky_somavati_amavasya_9_november_2026(november):
    # Amavasya runs 8 Nov 11:27 -> 9 Nov 12:31 IST; the Monday inside it is 9 Nov (whole-span rule),
    # although Diwali itself is on 8 Nov
    assert november["somavati_amavasya"] == [date(2026, 11, 9)]


def test_real_sky_holi_is_the_day_after_holika_dahan_2026(march):
    assert len(march["holika_dahan"]) == 1 and len(march["holi"]) == 1
    assert march["holi"][0] == march["holika_dahan"][0] + timedelta(days=1)
