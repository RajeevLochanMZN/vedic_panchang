"""
engine/festival_span.py  --  ONE date per festival: the day on which its tithi covers
the most hours of DAYTIME (sunrise to sunset).

Decision (Pi clock, 12 Nov 2026): a tithi usually touches two calendar dates, sometimes
three ("14/15/16"), but often one of them has almost no daytime (the tithi starts after
sunset or ends before sunrise).  The festival is shown on the date where the tithi is
present for the LONGEST part of the daytime.  (Before: every date the tithi touched.)
The vyapti scoring and tie-break in festival_vyapti.py are still NOT used by this module.

THE RULE
  * Every tithi that prevails at any moment of a calendar day (IST) is looked at.
    Its lunar month is checked (Adhik / Kshaya months are skipped, as before).
  * A festival with that tithi and month is held on ONE date: of the calendar dates the
    tithi touches, the one with the most hours between sunrise and sunset inside the tithi.
    Equal hours (within a minute): the earlier date.  A tithi that covers no daytime at all
    (it lies wholly in a night): the date on which it starts.
  * The festival is ON that date only (active_on(festivals, k) lists it for that k alone).
  * tithi_and_weekday festivals (Somavati / Shani Amavasya): unchanged - on the date inside
    the tithi's WHOLE span whose weekday matches.
  * Holi = the day after the Holika Dahan date.
  * eclipse_shift(day_index) (optional): moves a date that has a visible eclipse.
  * Sankranti festivals are not handled here (festivals.py keeps doing them).

The RIGHT PANEL tithi line uses tithi_period_text(): "9 नव॰ 10:30 से 10 नव॰ 06:30 तक".

Adapter (same as festival_vyapti.py, plus weekday_of):
    tithi_at(jd), month_at(jd), sun_times(k), weekday_of(k) -> "Somvar" ...
"""
import math
from datetime import datetime, timedelta

from festival_vyapti import tithi_span, format_dates_hi, MONTHS_HI

MONTHS_SHORT_HI = ["जन॰", "फ़र॰", "मार्च", "अप्रै॰", "मई", "जून", "जुला॰", "अग॰",
                   "सित॰", "अक्टू॰", "नव॰", "दिस॰"]


def jd_to_local(jd, tz_hours=5.5):
    """Julian Day (UT) -> naive local datetime (IST by default)."""
    return datetime(2000, 1, 1, 12) + timedelta(days=jd - 2451545.0 + tz_hours / 24.0)


def tithi_period_text(start_jd, end_jd, tz_hours=5.5, till="तक", frm="से",
                      months=MONTHS_SHORT_HI):
    """'9 नव॰ 10:30 से 10 नव॰ 06:30 तक'  -- for the tithi line of the right panel."""
    a, b = jd_to_local(start_jd, tz_hours), jd_to_local(end_jd, tz_hours)
    f = lambda d: "%d %s %02d:%02d" % (d.day, months[d.month - 1], d.hour, d.minute)
    return "%s %s %s %s" % (f(a), frm, f(b), till)


class SpanResolver:
    def __init__(self, adapter, tz_hours=5.5, eclipse_shift=None):
        self.a = adapter
        self.tz = tz_hours
        self.shift = eclipse_shift or (lambda k: k)
        self._base = self._local_day(adapter.sun_times(0)[0])
        self._occ = {}
        self._sun = {}

    def _local_day(self, jd):
        return math.floor(jd + 0.5 + self.tz / 24.0)

    def day_index(self, jd):
        """Local calendar day of jd: 0 = today, 1 = tomorrow ..."""
        return self._local_day(jd) - self._base

    def _day_start(self, k):
        return (self._base + k) - 0.5 - self.tz / 24.0      # local midnight starting day k

    def occurrences(self, k):
        """[(tithi, start_jd, end_jd, month)] for every tithi prevailing at some
        moment of calendar day k."""
        if k in self._occ:
            return self._occ[k]
        j0 = self._day_start(k)
        out, seen = [], set()
        for h in range(0, 25, 2):                            # every 2 hours is enough
            jd = j0 + h / 24.0
            t = self.a.tithi_at(jd)
            if t in seen:
                continue
            seen.add(t)
            s, e = tithi_span(self.a, jd)
            out.append((t, s, e, self.a.month_at((s + e) / 2.0)))
        self._occ[k] = out
        return out

    def _all_dates(self, s, e):
        """Every calendar date (day index) the tithi touches, from its start to its end."""
        d0, d1 = self.day_index(s), self.day_index(e)
        return list(range(d0, d1 + 1))

    def _sun_of(self, k):
        if k not in self._sun:
            self._sun[k] = self.a.sun_times(k)
        return self._sun[k]

    def _daytime_hours(self, k, s, e):
        """Hours between sunrise and sunset of day k that lie inside the tithi [s, e]."""
        sr, ss = self._sun_of(k)
        return max(0.0, (min(e, ss) - max(s, sr)) * 24.0)

    def _dates(self, s, e):
        """The ONE date the festival is held on: the day the tithi covers the most daytime."""
        days = self._all_dates(s, e)
        hours = {d: self._daytime_hours(d, s, e) for d in days}
        best = max(hours.values())
        if best <= 0.0:                                   # no daytime at all: the tithi's own start date
            chosen = days[0]
        else:
            chosen = next(d for d in days if hours[d] >= best - 1.0 / 60.0)    # ties (< 1 min): earlier
        return [self.shift(chosen)]

    def active_on(self, festivals, k=0):
        """Festivals held ON calendar day k: list of
        {"festival": f, "tithi_days": [day index], "span": (start_jd, end_jd)}."""
        out = []
        for t, s, e, month in self.occurrences(k):
            days = self._dates(s, e)                       # one date
            whole = None                                   # all dates of the tithi (weekday rule)
            for f in festivals:
                rule = f.get("rule")
                if rule == "tithi_at_sunrise" and f["name"] != "Holi":
                    if f["tithi"] == t and f["lunar_month"] == month and k in days:
                        out.append({"festival": f, "tithi_days": days, "span": (s, e)})
                elif rule == "tithi_and_weekday" and f["tithi"] == t:
                    if whole is None:
                        whole = sorted({self.shift(d) for d in self._all_dates(s, e)})
                    wd = [d for d in whole if self.a.weekday_of(d) == f["vara"] and d == k]
                    if wd:
                        out.append({"festival": f, "tithi_days": wd, "span": (s, e)})
        # Holi: the day after Holika Dahan
        holi = next((f for f in festivals if f["name"] == "Holi"), None)
        if holi:
            for e in self.active_on_no_holi(festivals, k - 1):
                if e["festival"]["name"] == "Holika Dahan":
                    days = sorted({d + 1 for d in e["tithi_days"]})
                    if k in days:
                        out.append({"festival": holi, "tithi_days": days, "span": e["span"]})
        return out

    def active_on_no_holi(self, festivals, k):
        out = []
        for t, s, e, month in self.occurrences(k):
            days = self._dates(s, e)
            for f in festivals:
                if f.get("rule") == "tithi_at_sunrise" and f["name"] == "Holika Dahan" \
                        and f["tithi"] == t and f["lunar_month"] == month and k in days:
                    out.append({"festival": f, "tithi_days": days, "span": (s, e)})
        return out


def card_pages(resolver, festivals, base_date, name_hi=lambda n: n,
               months_hi=MONTHS_HI, days_ahead=2, max_next=2, max_pages=4):
    """Pages (line1, line2) for the festival corner card; [] = swastik.  At most
    max_pages pages (today's first, so "अगला पर्व" pages are the first to be dropped).
      today's festivals:  ("आज का पर्व : दीपावली", "")           (one date: no dates line)
      then festivals held within days_ahead days and not today:
                          ("अगला पर्व : गोवर्धन पूजा", "10 नवम्बर")"""
    def page(label, e, force_date=None):
        days = e["tithi_days"]
        dates = days if len(days) > 1 else ([force_date] if force_date is not None else [])
        return (label + name_hi(e["festival"]["name"]),
                format_dates_hi(base_date, dates, months_hi) if dates else "")

    today = resolver.active_on(festivals, 0)
    pages = [page("आज का पर्व : ", e) for e in today]
    ids_today = {e["festival"]["id"] for e in today}
    for k in range(1, days_ahead + 1):
        nxt = [e for e in resolver.active_on(festivals, k) if e["festival"]["id"] not in ids_today]
        if nxt:
            pages += [page("अगला पर्व : ", e, force_date=k) for e in nxt[:max_next]]
            break
    return pages[:max_pages]
