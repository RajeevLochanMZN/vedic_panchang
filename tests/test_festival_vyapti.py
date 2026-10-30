"""
tests/test_festival_vyapti.py -- checks engine/festival_vyapti.py with an
independent astronomical adapter built on pyswisseph alone (built-in Moshier
ephemeris, no ephe files needed), so it runs on any PC:

    pip install pyswisseph pyyaml
    python tests/test_festival_vyapti.py              # print every festival Oct 2026 - Mar 2027
    python tests/test_festival_vyapti.py 2026-10-20 2026-11-15

It prints the date the rule gives for each tithi-based festival (and "TIE a/b"
when two days tied).  Compare with a reference calendar (e.g. Drik Panchang).
"""
import os
import sys
from datetime import date, datetime, timedelta

import swisseph as swe
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
from festival_vyapti import FestivalDayResolver, festivals_held_on  # noqa: E402

LAT, LON = 29.4667, 77.7333          # Muzaffarnagar
IST = 5.5 / 24.0
FLAGS = swe.FLG_MOSEPH


def _lon(body, jd, sid=False):
    f = FLAGS | (swe.FLG_SIDEREAL if sid else 0)
    return swe.calc_ut(jd, body, f)[0][0]


def _elong(jd):
    return (_lon(swe.MOON, jd) - _lon(swe.SUN, jd)) % 360.0


class SwissAdapter:
    def __init__(self, base_date):
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        self.base = base_date
        self._nm = {}

    def tithi_at(self, jd):
        return int(_elong(jd) // 12.0) + 1

    # -- amanta month via the new moon that starts the lunar month
    def _newmoon_near(self, jd):
        for _ in range(8):
            e = _elong(jd)
            e = e - 360.0 if e > 180.0 else e
            jd -= e / 12.19
        return jd

    def month_at(self, jd):
        e = _elong(jd)
        start = self._newmoon_near(jd - e / 12.19)
        end = self._newmoon_near(start + 29.53)
        r0 = int(_lon(swe.SUN, start, True) // 30.0)
        r1 = int(_lon(swe.SUN, end, True) // 30.0)
        if r0 == r1:
            return 0                      # Adhik month: festivals skipped
        return (r0 + 1) % 12 + 1

    def _midnight(self, k):
        d = self.base + timedelta(days=k)
        return swe.julday(d.year, d.month, d.day, 0.0) - IST

    def _rise_set(self, body, jd0, rise):
        flag = swe.CALC_RISE if rise else swe.CALC_SET
        res, tret = swe.rise_trans(jd0, body, flag, (LON, LAT, 200.0), 1013.25, 15.0, FLAGS)
        return tret[0] if res == 0 else None

    def sun_times(self, k):
        j0 = self._midnight(k)
        sr = self._rise_set(swe.SUN, j0, True)
        ss = self._rise_set(swe.SUN, sr, False)
        return sr, ss

    def weekday_of(self, k):
        names = ["Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar"]
        return names[(self.base + timedelta(days=k)).weekday()]

    def moonrise_jd(self, k):
        j0 = self._midnight(k)
        r = self._rise_set(swe.MOON, j0, True)
        return r if r and r < j0 + 1.0 else None


def to_ist_date(jd):
    y, m, d, h = swe.revjul(jd + IST)
    return date(y, m, d)


def run(start, end):
    with open(os.path.join(HERE, "..", "config", "festivals.yaml"), encoding="utf-8") as f:
        festivals = yaml.safe_load(f)["festivals"]
    d = start
    rows = []
    while d <= end:
        ad = SwissAdapter(d)
        res = FestivalDayResolver(ad)
        for e in festivals_held_on(res, festivals, 0):
            name = e["festival"]["name"]
            tie = ""
            if e["tie_dates"]:
                tie = "   TIE " + "/".join(str((d + timedelta(days=x)).day) for x in e["tie_dates"])
            rows.append((d, name, tie))
        d += timedelta(days=1)
    return rows


class FakeAdapter:
    """Hand-made sky for testing the TIE rule: 24-hour days, sunrise at .25 and
    sunset at .75 of each day, Amavasya (tithi 30) from jd 0.70 to 1.95."""
    def tithi_at(self, jd):
        return 30 if 0.70 <= jd < 1.95 else (29 if jd < 0.70 else 1)
    def month_at(self, jd):
        return 7
    def sun_times(self, k):
        return k + 0.25, k + 0.75
    def moonrise_jd(self, k):
        return None


def selftest():
    """Diwali (pradosh) with Amavasya covering the pradosh of BOTH day 0 and day 1:
    a tie.  Day 0 sunrise tithi (29) ends AFTER midday -> its dominant tithi is 29.
    Day 1 sunrise tithi (30) ends after midday -> dominant 30.  Day 1 must win,
    and the tie must be reported as days 0 and 1."""
    res = FestivalDayResolver(FakeAdapter())
    day, tied = res.festival_day("Diwali", 30, 7, around=0)
    assert (day, tied) == (1, [0, 1]), (day, tied)
    f = {"name": "Diwali", "tithi": 30, "lunar_month": 7, "rule": "tithi_at_sunrise"}
    assert res.held_on(f, 0) == (False, []), res.held_on(f, 0)
    assert res.held_on(f, 1) == (True, [0, 1]), res.held_on(f, 1)
    # no tie: Amavasya present at pradosh on day 0 only -> day 0
    class OneDay(FakeAdapter):
        def tithi_at(self, jd):
            return 30 if 0.70 <= jd < 1.2 else (29 if jd < 0.70 else 1)
    res2 = FestivalDayResolver(OneDay())
    assert res2.festival_day("Diwali", 30, 7, around=0) == (0, []), res2.festival_day("Diwali", 30, 7, around=0)
    # eclipse hook: day 1 is blocked and moves to day 2
    res3 = FestivalDayResolver(FakeAdapter(), eclipse_shift=lambda k: 2 if k == 1 else k)
    assert [e["festival"]["name"] for e in festivals_held_on(res3, [f], 2)] == ["Diwali"]
    assert festivals_held_on(res3, [f], 1) == []
    print("selftest OK: tie -> later day by dominant tithi, tie dates reported, eclipse shift works")


def cards(a, b):
    """Card pages for each day a..b (festival names in English)."""
    from festival_span import SpanResolver, card_pages
    with open(os.path.join(HERE, "..", "config", "festivals.yaml"), encoding="utf-8") as f:
        festivals = yaml.safe_load(f)["festivals"]
    d = a
    while d <= b:
        pages = card_pages(SpanResolver(SwissAdapter(d)), festivals, d)
        print(d.isoformat(), d.strftime("%a"), pages if pages else "(swastik)")
        d += timedelta(days=1)


def year_list(year):
    """Every festival with the dates it is shown on (span rule), for a whole year."""
    from festival_span import SpanResolver
    from festival_vyapti import MONTHS_HI
    with open(os.path.join(HERE, "..", "config", "festivals.yaml"), encoding="utf-8") as f:
        festivals = yaml.safe_load(f)["festivals"]
    seen = {}
    d = date(year, 1, 1)
    while d.year == year:
        r = SpanResolver(SwissAdapter(d))
        for e in r.active_on(festivals, 0):
            dates = tuple(d + timedelta(days=x) for x in e["tithi_days"])
            seen[(e["festival"]["id"], dates)] = (dates[0], e["festival"]["name"], dates)
        d += timedelta(days=1)
    for _, (first, name, dates) in sorted(seen.items(), key=lambda kv: kv[1][0]):
        if len({(x.year, x.month) for x in dates}) == 1:
            label = "/".join(str(x.day) for x in dates) + " " + dates[0].strftime("%b")
        else:
            label = " / ".join(x.strftime("%d %b") for x in dates)
        print(first.isoformat(), name, label)


if __name__ == "__main__":
    if "--cards" in sys.argv:
        i = sys.argv.index("--cards")
        cards(date.fromisoformat(sys.argv[i + 1]), date.fromisoformat(sys.argv[i + 2]))
        sys.exit(0)
    if "--year" in sys.argv:
        year_list(int(sys.argv[sys.argv.index("--year") + 1]))
        sys.exit(0)
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    a = date(2026, 10, 1) if len(sys.argv) < 3 else date.fromisoformat(sys.argv[1])
    b = date(2027, 3, 31) if len(sys.argv) < 3 else date.fromisoformat(sys.argv[2])
    for d, name, tie in run(a, b):
        print(d.isoformat(), d.strftime("%a"), name, tie)
