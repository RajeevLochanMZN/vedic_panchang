"""
engine/festival_span.py  --  festivals shown on EVERY date their tithi covers.

Decision (Pi clock): whenever a festival's tithi falls on two calendar dates, show
BOTH dates ("8/9 नवम्बर") and let people decide which day to celebrate.  So the
engine no longer has to choose one day (the vyapti scoring and tie-break in
festival_vyapti.py are NOT used by this module).

THE RULE
  * Every tithi that prevails at any moment of a calendar day (IST) is looked at.
    Its lunar month is checked (Adhik / Kshaya months are skipped, as before).
  * A festival with that tithi and month is ON that day.  Its dates are every
    calendar date from the date the tithi starts to the date it ends
    (usually two: "8/9").  It stays on the card on all of those dates.
  * tithi_and_weekday festivals (Somavati / Shani Amavasya): on the date inside
    the tithi's span whose weekday matches.
  * Holi = the day after each Holika Dahan date ("2/3" -> "3/4").
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

    def _dates(self, s, e):
        d0, d1 = self.day_index(s), self.day_index(e)
        return sorted({self.shift(d) for d in range(d0, d1 + 1)})

    def active_on(self, festivals, k=0):
        """Festivals ON calendar day k: list of
        {"festival": f, "tithi_days": [day indexes], "span": (start_jd, end_jd)}."""
        out = []
        for t, s, e, month in self.occurrences(k):
            days = self._dates(s, e)
            for f in festivals:
                rule = f.get("rule")
                if rule == "tithi_at_sunrise" and f["name"] != "Holi":
                    if f["tithi"] == t and f["lunar_month"] == month:
                        out.append({"festival": f, "tithi_days": days, "span": (s, e)})
                elif rule == "tithi_and_weekday" and f["tithi"] == t:
                    wd = [d for d in days if self.a.weekday_of(d) == f["vara"] and d == k]
                    if wd:
                        out.append({"festival": f, "tithi_days": wd, "span": (s, e)})
        # Holi: the day after Holika Dahan (every Holika Dahan date + 1)
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
            for f in festivals:
                if f.get("rule") == "tithi_at_sunrise" and f["name"] == "Holika Dahan" \
                        and f["tithi"] == t and f["lunar_month"] == month:
                    out.append({"festival": f, "tithi_days": self._dates(s, e), "span": (s, e)})
        return out


def card_pages(resolver, festivals, base_date, name_hi=lambda n: n,
               months_hi=MONTHS_HI, days_ahead=2, max_next=2, max_pages=4):
    """Pages (line1, line2) for the festival corner card; [] = swastik.  At most
    max_pages pages (today's first, so "अगला पर्व" pages are the first to be dropped).
      today's festivals:  ("आज का पर्व : दीपावली", "8/9 नवम्बर")   (dates only if 2+)
      then festivals that BEGIN within days_ahead days and are not on today:
                          ("अगला पर्व : गोवर्धन पूजा", "10/11 नवम्बर")"""
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
