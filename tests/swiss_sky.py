"""
tests/swiss_sky.py -- an independent sky for the festival tests, built on pyswisseph alone
(built-in Moshier ephemeris, no ephe files needed):

    pip install pyswisseph pyyaml

SwissAdapter(base_date) answers the questions the festival engine asks (tithi_at, month_at,
sun_times, weekday_of, moonrise_jd) for a clock at LAT, LON; day 0 = base_date (IST).
Used by tests/test_festival_span.py and tests/test_festival_vyapti.py.
"""
from datetime import date, datetime, timedelta

import swisseph as swe

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
