"""
engine/festival_vyapti.py  --  which DAY a tithi-based festival is held on.

Python port of the ESP32 clock's "vyapti" rule (FestivalsEngine.cpp), plus the
tie-break rule agreed for the Pi clock.  Pure logic: it never imports the other
engine modules itself.  It talks to an ADAPTER object (see PiAdapter at the
bottom for the real one, and tests/test_festival_vyapti.py for a test one).

THE RULE, step by step
  1. Every festival has its own time of day ("kaala") at which its tithi must
     prevail: sunrise, madhyahna (midday), aparahna (afternoon), sayahna
     (evening), pradosh (just after sunset), moonrise, or nishitha (midnight).
     Festivals not listed in KAALA_OF are judged at sunrise.
  2. For each of the three days (yesterday, today, tomorrow) a SCORE is
     calculated: the share of that kaala window during which the festival's
     tithi prevails (8 samples).  For sunrise festivals the tithi at the
     sunrise itself adds +2 (the "udaya tithi" counts most).
     The score is 0 unless the lunar month is right (not Adhik / Kshaya).
  3. The day with the highest score holds the festival.
  4. TIE (two days with exactly the same highest score):
        take each day's DOMINANT tithi = the tithi at sunrise, but if that
        tithi ends before midday, the NEXT tithi.  (i.e. the tithi that
        exists for most of the daytime).  The day whose dominant tithi is the
        festival's tithi wins.  If that does not decide it (both days or
        neither), the EARLIER day wins (what the ESP32 clock does).
     A tie is reported in the result (tie_dates) so the screen can show
     "9/10 नवम्बर".
  5. A festival is never held on a day with an eclipse visible from the clock's
     place: it moves to the day after that eclipse ends (eclipse_shift hook).
     Holi is always the day after Holika Dahan.

"Midday" in step 4 = the midpoint between sunrise and sunset (not 12:00 clock noon).
"""

# ----------------------------------------------------------------- kaala table
K_SUNRISE, K_MADHYAHNA, K_APARAHNA, K_SAYAHNA, K_PRADOSH, K_MOONRISE, K_NISHITHA = range(7)

KAALA_OF = {
    "Bhishma Ashtami": K_MADHYAHNA, "Ram Navami": K_MADHYAHNA, "Sita Navami": K_MADHYAHNA,
    "Maha Navami": K_MADHYAHNA, "Durga Ashtami": K_MADHYAHNA, "Ganesh Chaturthi": K_MADHYAHNA,
    "Rishi Panchami": K_MADHYAHNA, "Radha Ashtami": K_MADHYAHNA, "Vaman Jayanti": K_MADHYAHNA,
    "Skanda Sashti": K_MADHYAHNA, "Akshaya Tritiya": K_MADHYAHNA,
    "Dussehra": K_APARAHNA, "Bhai Dooj": K_APARAHNA,
    "Narasimha Jayanti": K_SAYAHNA, "Chhath Puja": K_SAYAHNA,
    "Holika Dahan": K_PRADOSH, "Dhanteras": K_PRADOSH, "Diwali": K_PRADOSH,
    "Ahoi Ashtami": K_PRADOSH, "Parashurama Jayanti": K_PRADOSH, "Dattatreya Jayanti": K_PRADOSH,
    "Karva Chauth": K_MOONRISE, "Sakat Chauth": K_MOONRISE,
    "Maha Shivaratri": K_NISHITHA, "Janmashtami": K_NISHITHA, "Kali Puja": K_NISHITHA,
    "Sharad Purnima": K_NISHITHA,
}


def kaala_of(name):
    if name.startswith("Pitrupaksh") or name == "Mahalaya Amavasya":
        return K_APARAHNA                       # shraddha: afternoon
    return KAALA_OF.get(name, K_SUNRISE)


def kaala_window(k, sr, ss, sr_next):
    """(start, end) Julian Days of kaala k on a day with this sunrise / sunset /
    next sunrise."""
    L = ss - sr
    if k == K_MADHYAHNA:
        return sr + 0.4 * L, sr + 0.6 * L
    if k == K_APARAHNA:
        return sr + 0.6 * L, sr + 0.8 * L
    if k == K_SAYAHNA:
        return sr + 0.8 * L, ss
    if k == K_PRADOSH:
        return ss, ss + 120.0 / 1440.0
    if k == K_MOONRISE:                          # stand-in; real moonrise replaces it
        return ss + 60.0 / 1440.0, ss + 180.0 / 1440.0
    if k == K_NISHITHA:
        mid = (ss + sr_next) / 2.0
        return mid - 24.0 / 1440.0, mid + 24.0 / 1440.0
    return sr, sr + L / 5.0                      # K_SUNRISE


# --------------------------------------------------------------------- resolver
class FestivalDayResolver:
    """
    adapter must provide (all times are Julian Day UT):
        tithi_at(jd)            -> 1..30
        month_at(jd)            -> Amanta month 1..12, or 0 for Adhik / Kshaya
        sun_times(k)            -> (sunrise_jd, sunset_jd) of day k  (0 = today,
                                   -1 = yesterday ...)  must work for k = -3 .. +4
        moonrise_jd(k)          -> moonrise JD of day k, or None
    eclipse_shift(k) (optional callable): day index k -> the day the festivals of
        day k move to because of a visible eclipse (k itself if no eclipse).
    """
    N = 8                                       # samples across each kaala window

    def __init__(self, adapter, eclipse_shift=None, tz_hours=5.5):
        self.a = adapter
        self.tz = tz_hours
        self.eclipse_shift = eclipse_shift or (lambda k: k)
        self._sun = {}
        self._rise = {}
        self._tcache = {}
        self._mcache = {}
        self._dom = {}

    # ---- cached look-ups
    def _suntimes(self, k):
        if k not in self._sun:
            self._sun[k] = self.a.sun_times(k)
        return self._sun[k]

    def _sr_next(self, k):
        return self._suntimes(k + 1)[0]

    def _window(self, kaala, k):
        sr, ss = self._suntimes(k)
        a, b = kaala_window(kaala, sr, ss, self._sr_next(k))
        if kaala == K_MOONRISE:
            if k not in self._rise:
                self._rise[k] = self.a.moonrise_jd(k)
            r = self._rise[k]
            if r:
                a, b = r, r + 10.0 / 1440.0     # the tithi must prevail at the real moonrise
        return a, b

    def score(self, kaala, k, tithi, month):
        """Share (0..1, +2 udaya bonus for sunrise festivals) of kaala on day k in
        which `tithi` of lunar `month` prevails."""
        a, b = self._window(kaala, k)
        key = (kaala, k)
        if key not in self._mcache:
            self._mcache[key] = self.a.month_at((a + b) / 2.0)
        if self._mcache[key] != month:
            return 0.0
        udaya = 0.0
        if kaala == K_SUNRISE and self.a.tithi_at(self._suntimes(k)[0]) == tithi:
            udaya = 2.0
        if key not in self._tcache:
            self._tcache[key] = [self.a.tithi_at(a + (b - a) * (s + 0.5) / self.N)
                                 for s in range(self.N)]
        n = sum(1 for t in self._tcache[key] if t == tithi)
        return udaya + n / float(self.N)

    # ---- tie-break: the day's dominant tithi
    def tithi_end_jd(self, jd):
        """JD at which the tithi prevailing at `jd` ends (to about a minute)."""
        t0 = self.a.tithi_at(jd)
        lo, step = jd, 1.0 / 24.0
        hi = lo + step
        while self.a.tithi_at(hi) == t0 and hi - jd < 2.0:
            lo, hi = hi, hi + step
        for _ in range(14):                      # bisection
            mid = (lo + hi) / 2.0
            if self.a.tithi_at(mid) == t0:
                lo = mid
            else:
                hi = mid
        return hi

    def dominant_tithi(self, k):
        """Tithi at sunrise; if it ends before midday (midpoint of sunrise and
        sunset) then the NEXT tithi."""
        if k not in self._dom:
            sr, ss = self._suntimes(k)
            t = self.a.tithi_at(sr)
            if self.tithi_end_jd(sr) < (sr + ss) / 2.0:
                t = t % 30 + 1
            self._dom[k] = t
        return self._dom[k]

    # ---- calendar dates over which a festival's tithi runs
    def day_index_of(self, jd):
        """Local calendar day of `jd` as an index: 0 = today, 1 = tomorrow ..."""
        import math
        local = lambda x: math.floor(x + 0.5 + self.tz / 24.0)
        return local(jd) - local(self._suntimes(0)[0])

    def tithi_dates(self, f, k):
        """Sorted day indexes (local calendar dates) on which the festival's
        tithi starts and ends, e.g. [1, 2] for "7/8 नवम्बर".  One entry if it
        starts and ends on the same date.  k = the day the festival is held."""
        a, b = self._window(kaala_of(f["name"]), k)
        jd = None
        for i in range(self.N):                  # a moment of the window with that tithi
            t = a + (b - a) * (i + 0.5) / self.N
            if self.a.tithi_at(t) == f["tithi"]:
                jd = t
                break
        if jd is None:
            jd = self._suntimes(k)[0]
        start, end = tithi_span(self.a, jd)
        return sorted({self.day_index_of(start), self.day_index_of(end)})

    # ---- the festival day
    def festival_day(self, name, tithi, month, around):
        """Day index on which the festival is held, looking at days around-1,
        around, around+1.  Returns (day_index, tie_dates) where tie_dates is a
        sorted list of the day indexes that tied (empty if no tie), or
        (None, []) if none of the three days qualifies."""
        kaala = kaala_of(name)
        days = (around - 1, around, around + 1)
        sc = {d: self.score(kaala, d, tithi, month) for d in days}
        best = max(sc.values())
        if best <= 0.0:
            return None, []
        tied = [d for d in days if abs(sc[d] - best) < 1e-9]
        if len(tied) == 1:
            return tied[0], []
        # TIE: the day whose dominant tithi is the festival's tithi wins
        dom = [d for d in tied if self.dominant_tithi(d) == tithi]
        winner = dom[0] if len(dom) == 1 else tied[0]     # still undecided: earlier day
        return winner, tied

    def held_on(self, f, k):
        """Is tithi-based festival f (dict from festivals.yaml) held on day k?
        Returns (True/False, tie_dates)."""
        tithi, month = f["tithi"], f["lunar_month"]
        # cheap filter: the tithi must be within 2 tithis of today's sunrise tithi
        if (tithi - self.a.tithi_at(self._suntimes(k)[0])) % 30 > 2:
            return False, []
        day, tied = self.festival_day(f["name"], tithi, month, k)
        return day == k, (tied if day == k else [])


# ------------------------------------------------------------- public helpers
def festivals_held_on(resolver, festivals, k=0):
    """Festivals whose festival DAY (by the rule) is day k, each as
    {"festival": f, "tie_dates": [day indexes] or []}.  Holi = day after
    Holika Dahan.  Eclipse shifts are applied through resolver.eclipse_shift."""
    out = []
    for f in festivals:
        if f.get("rule") != "tithi_at_sunrise" or f["name"] == "Holi":
            continue
        # the festival may be held on day k itself, or have been held on k-1 and
        # moved onto k because of a visible eclipse
        for src in (k, k - 1):
            if resolver.eclipse_shift(src) != k:
                continue
            held, tied = resolver.held_on(f, src)
            if held:
                out.append({"festival": f, "tie_dates": tied,
                            "tithi_days": resolver.tithi_dates(f, src)})
                break
    # Holi: the day after Holika Dahan (whatever day Holika Dahan landed on)
    holi = next((f for f in festivals if f["name"] == "Holi"), None)
    hd = next((f for f in festivals if f["name"] == "Holika Dahan"), None)
    if holi and hd:
        held, _ = resolver.held_on(hd, k - 1)
        if held:
            out.append({"festival": holi, "tie_dates": [], "tithi_days": []})
    return out


def festivals_active_on(resolver, festivals, k=0):
    """Festivals to SHOW on day k: from the festival day (by the rule) until the
    last calendar date of its tithi.  Diwali: festival day 8 Nov, tithi runs
    8/9 Nov, so it is shown on 8 and on 9 November.  Same entry format as
    festivals_held_on, with "tithi_days"."""
    out = []
    for f in festivals:
        if f.get("rule") != "tithi_at_sunrise" or f["name"] == "Holi":
            continue
        for d in (k, k - 1, k - 2):              # the festival day may be earlier than k
            shifted = resolver.eclipse_shift(d)
            if shifted > k:
                continue
            held, tied = resolver.held_on(f, d)
            if not held:
                continue
            days = resolver.tithi_dates(f, d)
            if shifted <= k <= max(days + [shifted]):
                out.append({"festival": f, "tie_dates": tied, "tithi_days": days})
            break                                  # this festival's day found
    holi = next((f for f in festivals if f["name"] == "Holi"), None)
    hd = next((f for f in festivals if f["name"] == "Holika Dahan"), None)
    if holi and hd and resolver.held_on(hd, k - 1)[0]:
        out.append({"festival": holi, "tie_dates": [], "tithi_days": []})
    return out


def next_festival_within(resolver, festivals, days_ahead=2):
    """(day_index, entries) for the first of days 1..days_ahead whose festival DAY
    (rule day) has a festival, else None.  For the 'अगला पर्व' line (only shown 2 days before)."""
    for k in range(1, days_ahead + 1):
        entries = festivals_held_on(resolver, festivals, k)
        if entries:
            return k, entries
    return None


def tithi_span(adapter, jd):
    """(start_jd, end_jd) of the tithi prevailing at jd -- for the right-panel
    line "9 नव॰ 10:30 से 10 नव॰ 06:30 तक"."""
    t0 = adapter.tithi_at(jd)

    def edge(direction):
        step = 1.0 / 24.0
        lo, hi = jd, jd + direction * step
        while adapter.tithi_at(hi) == t0 and abs(hi - jd) < 2.0:
            lo, hi = hi, hi + direction * step
        for _ in range(14):
            mid = (lo + hi) / 2.0
            if adapter.tithi_at(mid) == t0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    return edge(-1), edge(+1)


# ------------------------------------------------------------- the real adapter
class PiAdapter:
    """Adapter over the Pi project's own engine modules (ephemeris, panchang,
    masa, sun_times).  Day 0 = the IST calendar day of base_ist.
    NOT tested here (the engine modules were not available) -- the function
    names and result keys are the ones used by ui/page_home_hi.py."""

    def __init__(self, base_ist, lat, lon):
        from datetime import timedelta
        self._td = timedelta
        self.base_ist = base_ist
        self.lat, self.lon = lat, lon

    def tithi_at(self, jd):
        from panchang import get_tithi_number
        return get_tithi_number(jd)

    def month_at(self, jd):
        from masa import get_masa_details, MASA_NAMES
        m = get_masa_details(jd)
        if m["is_adhik"] or m["is_kshaya"]:
            return 0
        return MASA_NAMES.index(m["name"].split(" (")[0]) + 1

    def sun_times(self, k):
        from sun_times import get_sun_times_details
        d = self.base_ist + self._td(days=k)
        sun = get_sun_times_details(d, self.lat, self.lon)
        return sun["sunrise_jd"], sun["sunset_jd"]

    def weekday_of(self, k):
        from time_systems import get_vara
        return get_vara(self.base_ist + self._td(days=k))

    def moonrise_jd(self, k):
        from sun_times import get_moonrise_jd, get_local_midnight_jd_ut
        d = self.base_ist + self._td(days=k)
        jd = get_moonrise_jd(get_local_midnight_jd_ut(d), self.lat, self.lon)
        return jd if jd and jd > 0 else None


# ------------------------------------------------------------ text for the card
MONTHS_HI = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त",
             "सितम्बर", "अक्टूबर", "नवम्बर", "दिसम्बर"]


def format_dates_hi(base_date, day_indexes, months_hi=MONTHS_HI):
    """[0, 1] with base_date 9 Nov -> "9/10 नवम्बर";  [2] -> "11 नवम्बर".
    base_date is the date of day index 0 (a datetime.date)."""
    from datetime import timedelta
    ds = [base_date + timedelta(days=i) for i in day_indexes]
    if len({(d.year, d.month) for d in ds}) == 1:
        return "%s %s" % ("/".join(str(d.day) for d in ds), months_hi[ds[0].month - 1])
    return " / ".join("%d %s" % (d.day, months_hi[d.month - 1]) for d in ds)


# True : line 2 of the card shows the dates over which the festival's tithi runs
#        ("8/9 नवम्बर" for Diwali), for every tithi-based festival.
# False: line 2 shows dates only when two days TIED.
SHOW_TITHI_DATES = True


def _dates_of(entry):
    return entry["tithi_days"] if SHOW_TITHI_DATES else entry["tie_dates"]


def _pages(entries, label, base_date, name_hi, months_hi, fallback_days=None):
    """One card page per festival: (label + name, its dates)."""
    out = []
    for e in entries:
        dates = _dates_of(e) or (fallback_days or [])
        out.append((label + name_hi(e["festival"]["name"]),
                    format_dates_hi(base_date, list(dates), months_hi) if dates else ""))
    return out


def card_pages(resolver, festivals, base_date, name_hi=lambda n: n,
               months_hi=MONTHS_HI, days_ahead=2, max_next=2):
    """What the festival corner card should show, as a list of (line1, line2)
    pages to rotate through.  An EMPTY list means nothing to announce -> swastik.
      1. every festival that is ON today (its festival day up to the last date
         of its tithi):            ("आज का पर्व : दीपावली", "8/9 नवम्बर")
      2. then the nearest coming festival day within days_ahead days (at most
         max_next festivals):      ("अगला पर्व : गोवर्धन पूजा", "9/10 नवम्बर")
    name_hi: function English festival name -> Hindi name (from translations_hi)."""
    pages = _pages(festivals_active_on(resolver, festivals, 0), "आज का पर्व : ",
                   base_date, name_hi, months_hi)
    nxt = next_festival_within(resolver, festivals, days_ahead)
    if nxt:
        k, entries = nxt
        pages += _pages(entries[:max_next], "अगला पर्व : ", base_date, name_hi,
                        months_hi, fallback_days=[k])
    return pages
