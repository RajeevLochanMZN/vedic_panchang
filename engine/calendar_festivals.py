"""
engine/calendar_festivals.py  --  the festivals of EVERY DAY of a month, for the Calendar pages.

Uses the SAME rule as the dial card (festival_span.py): a festival is held on ONE date, the day
its tithi covers the most daytime (sunrise to sunset).  So the Calendar and the card agree.
Sankranti festivals stay with engine/festivals.py (one date, no tithi), exactly as on the card.

    mf = for_month(2026, 11, lat, lon)       # build once per month (tithi periods are cached)
    mf.names_on(date(2026, 11, 8))           # -> ["Diwali"]   (English names, as in festivals.yaml)

for_month() returns None if anything is missing, so a caller can fall back to the old
per-day lookup (festivals.get_todays_festivals) and the Calendar never breaks.
"""
from datetime import date, datetime

from festival_span import SpanResolver


class MonthFestivals:
    def __init__(self, adapter, festivals, first_day, sankranti_names=None):
        """adapter: festival_vyapti.PiAdapter(first day of the month, lat, lon)
        festivals: festivals.load_festivals();  first_day: datetime.date of day 0 of the adapter
        sankranti_names: optional callable(date) -> list of names"""
        self.res = SpanResolver(adapter)
        self.festivals = festivals
        self.first = first_day
        self._sankranti = sankranti_names
        self._cache = {}

    def names_on(self, day):
        k = (day - self.first).days
        if k not in self._cache:
            names = [e["festival"]["name"] for e in self.res.active_on(self.festivals, k)]
            if self._sankranti:
                names += [n for n in self._sankranti(day) if n not in names]
            self._cache[k] = names
        return list(self._cache[k])


def for_month(year, month, lat, lon):
    """MonthFestivals for the Pi project's engine, or None if it cannot be built."""
    try:
        from festival_vyapti import PiAdapter
        from festivals import load_festivals, get_todays_festivals
        from sun_times import get_sun_times_details
        first_dt = datetime(year, month, 1)
        festivals = load_festivals()

        def sankranti(day):
            sun = get_sun_times_details(datetime(day.year, day.month, day.day), lat, lon)
            return [f["name"] for f in get_todays_festivals(sun["sunrise_jd"], sun["sunrise_jd"] - 1.0)
                    if f.get("rule") == "sankranti"]

        return MonthFestivals(PiAdapter(first_dt, lat, lon), festivals, first_dt.date(), sankranti)
    except Exception as exc:                       # never let the Calendar fail because of this
        print("[calendar] festival rule not available (%r); using the sunrise rule" % (exc,), flush=True)
        return None
