"""
tests/test_festival_vyapti.py -- a LISTING TOOL for the festival rules (it asserts nothing; the
pytest tests of the new rule are in tests/test_festival_span.py).  It uses the independent sky of
tests/swiss_sky.py (pyswisseph, Moshier ephemeris, no ephe files), so it runs on any PC:

    pip install pyswisseph pyyaml
    python tests/test_festival_vyapti.py                         # festivals Oct 2026 - Mar 2027, NEW rule (festival_span)
    python tests/test_festival_vyapti.py 2026-10-20 2026-11-15   # the same for another range
    python tests/test_festival_vyapti.py --year 2026             # whole year, NEW rule
    python tests/test_festival_vyapti.py --cards 2026-11-06 2026-11-12   # festival card pages per day
    python tests/test_festival_vyapti.py --old                   # the OLD vyapti rule (festival_vyapti), with "TIE a/b"
    python tests/test_festival_vyapti.py --selftest              # asserts for the OLD vyapti rule only

Compare the dates with a reference calendar (e.g. Drik Panchang).
"""
import os
import sys
from datetime import date, datetime, timedelta

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "engine"))
from festival_vyapti import FestivalDayResolver, festivals_held_on  # noqa: E402

from swiss_sky import LAT, LON, IST, SwissAdapter, to_ist_date  # noqa: E402,F401


def run(start, end):
    """NEW rule (festival_span): one row per festival, on the one date it is held."""
    from festival_span import SpanResolver
    with open(os.path.join(HERE, "..", "config", "festivals.yaml"), encoding="utf-8") as f:
        festivals = yaml.safe_load(f)["festivals"]
    rows = []
    d = start
    while d <= end:
        for e in SpanResolver(SwissAdapter(d)).active_on(festivals, 0):
            rows.append((d, e["festival"]["name"], ""))
        d += timedelta(days=1)
    return rows


def run_old(start, end):
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
    args = [x for x in sys.argv[1:] if x != "--old"]
    a = date(2026, 10, 1) if len(args) < 2 else date.fromisoformat(args[0])
    b = date(2027, 3, 31) if len(args) < 2 else date.fromisoformat(args[1])
    for d, name, tie in (run_old if "--old" in sys.argv else run)(a, b):
        print(d.isoformat(), d.strftime("%a"), name, tie)
