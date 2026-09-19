"""
engine/muhurta.py

Muhurta, Shubh Muhurta, and Pahar -- all derived from sunrise/sunset,
so this module depends on engine/sun_times.py.

  - Muhurta: the daytime (sunrise-to-sunset) span divided into 15
    equal parts (~48 min each), and the nighttime (sunset-to-next-
    sunrise) span into another 15. Names sourced directly from
    DrikPanchang's own "Do Ghati Muhurat" page -- our actual
    reference standard throughout this whole project -- rather than
    triangulated from multiple third-party sources as an earlier
    version of this file did (which had some real discrepancies,
    now corrected).
  - Abhijit Muhurta: the 8th of the 15 day names ("Vidhi" here,
    confirmed directly on DrikPanchang's page as "Madhyahna -
    Abhijit Muhurat").
  - Shubh Muhurta: this module covers Abhijit Muhurta and Brahma
    Muhurta (96-48 minutes before sunrise). Note DrikPanchang's own
    30-name list ALSO has a separate muhurta literally named "Brahma"
    (day #9 and night #23) -- that's a different, coincidentally-
    named concept from the pre-dawn "Brahma Muhurta" tradition; don't
    conflate the two.
  - Pahar: day divided into 4 Pahars, night into 4 Pahars (8 total
    across a full day-night cycle), each roughly 3 hours.

Depends on engine/ephemeris.py, engine/sun_times.py, engine/panchang.py
(for julday_to_ist_string). No PyQt / GPIO dependencies -- pure
Python, testable standalone.
"""

import os
from datetime import datetime, timezone

from ephemeris import init_ephemeris, datetime_to_julday
from panchang import julday_to_ist_string
from sun_times import get_sun_times_details


# Source: https://www.drikpanchang.com/muhurat/daily/do-ghati-muhurat.html
# (DrikPanchang's own page, our reference standard throughout this project)
DAY_MUHURTA_NAMES = [
    "Rudra", "Uraga", "Mitra", "Pitara", "Vasu", "Ambu", "Vishwedeva",
    "Vidhi (Abhijit)", "Brahma", "Indra", "Indragni", "Daitya",
    "Varuna", "Aryama", "Bhaga",
]

NIGHT_MUHURTA_NAMES = [
    "Ishwara", "Ajaikapada", "Ahirbudhnya", "Pusha", "Ashwini", "Yama",
    "Agni", "Brahma", "Chandra", "Aditi", "Brihaspati", "Vishnu",
    "Surya", "Tvashta", "Samirana",
]


# =============================================================================
# Muhurta (15 divisions of the day) and Abhijit Muhurta
# =============================================================================

def get_muhurta_details(jd_now: float, sunrise_jd: float, sunset_jd: float,
                         next_sunrise_jd: float = None) -> dict:
    """
    Current Muhurta number/name -- day (1-15) or night (1-15, using
    DAY_MUHURTA_NAMES or NIGHT_MUHURTA_NAMES as appropriate) -- plus
    Abhijit Muhurta's start/end (always computable from sunrise/sunset
    alone, regardless of what time it currently is).

    next_sunrise_jd is only needed if jd_now falls at night; pass None
    if you only care about the daytime case (Abhijit still works).
    """
    day_duration = sunset_jd - sunrise_jd
    day_muhurta_duration = day_duration / 15.0

    if sunrise_jd <= jd_now <= sunset_jd:
        current_number = int((jd_now - sunrise_jd) / day_muhurta_duration) + 1
        current_number = min(current_number, 15)
        current_name = DAY_MUHURTA_NAMES[current_number - 1]
        is_day = True
    elif next_sunrise_jd is not None and jd_now > sunset_jd:
        night_duration = next_sunrise_jd - sunset_jd
        night_muhurta_duration = night_duration / 15.0
        current_number = int((jd_now - sunset_jd) / night_muhurta_duration) + 1
        current_number = min(current_number, 15)
        current_name = NIGHT_MUHURTA_NAMES[current_number - 1]
        is_day = False
    else:
        current_number = None
        current_name = None
        is_day = None

    abhijit_start_jd = sunrise_jd + 7 * day_muhurta_duration  # start of the 8th day Muhurta
    abhijit_end_jd = sunrise_jd + 8 * day_muhurta_duration

    return {
        "current_muhurta_number": current_number,
        "current_muhurta_name": current_name,
        "is_day": is_day,
        "muhurta_duration_minutes": day_muhurta_duration * 1440.0,
        "abhijit_start_ist": julday_to_ist_string(abhijit_start_jd),
        "abhijit_end_ist": julday_to_ist_string(abhijit_end_jd),
        "abhijit_start_jd": abhijit_start_jd,
        "abhijit_end_jd": abhijit_end_jd,
    }


# =============================================================================
# Shubh Muhurta -- Abhijit (above) plus Brahma Muhurta (before sunrise)
# =============================================================================

def get_brahma_muhurta(sunrise_jd: float) -> dict:
    """
    Brahma Muhurta: starts 96 minutes before sunrise, ends 48 minutes
    before sunrise (a 48-minute window favoured for meditation/study).
    """
    minutes_to_days = 1.0 / 1440.0
    start_jd = sunrise_jd - 96 * minutes_to_days
    end_jd = sunrise_jd - 48 * minutes_to_days
    return {
        "start_ist": julday_to_ist_string(start_jd),
        "end_ist": julday_to_ist_string(end_jd),
    }


# =============================================================================
# Pahar -- 4 divisions of day, 4 of night
# =============================================================================

DAY_PAHAR_NAMES = ["Purvahna", "Madhyahna", "Aparahna", "Sayahna"]
NIGHT_PAHAR_NAMES = ["Pradosh", "Nishitha", "Trijama", "Ushakal"]


def get_pahar_details(jd_now: float, sunrise_jd: float, sunset_jd: float,
                       next_sunrise_jd: float) -> dict:
    """
    Current Pahar: which of the 8 (4 day + 4 night) we're in right now,
    its classical name, plus that Pahar's start/end time.
    """
    if sunrise_jd <= jd_now <= sunset_jd:
        is_day = True
        span_start, span_end = sunrise_jd, sunset_jd
    elif jd_now > sunset_jd:
        is_day = False
        span_start, span_end = sunset_jd, next_sunrise_jd
    else:
        # jd_now is before today's sunrise -- still part of last night's
        # span (sunset_jd here would need to be YESTERDAY's; caller
        # should pass yesterday's sun times in that case). Flagged as
        # a known edge case, same as the pre-dawn Vedic time gap.
        is_day = False
        span_start, span_end = sunset_jd, next_sunrise_jd

    span_duration = span_end - span_start
    pahar_duration = span_duration / 4.0
    pahar_number = int((jd_now - span_start) / pahar_duration) + 1
    pahar_number = max(1, min(pahar_number, 4))  # guard against edge rounding

    pahar_start_jd = span_start + (pahar_number - 1) * pahar_duration
    pahar_end_jd = span_start + pahar_number * pahar_duration

    name = (DAY_PAHAR_NAMES if is_day else NIGHT_PAHAR_NAMES)[pahar_number - 1]
    label = f"{name} ({'Day' if is_day else 'Night'} Pahar {pahar_number})"

    return {
        "label": label,
        "name": name,
        "is_day": is_day,
        "pahar_number": pahar_number,
        "start_ist": julday_to_ist_string(pahar_start_jd),
        "end_ist": julday_to_ist_string(pahar_end_jd),
    }


# =============================================================================
# Quick manual test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    from config_loader import get_location
    from datetime import timedelta

    lat, lon = get_location()
    IST_OFFSET = timedelta(hours=5, minutes=30)

    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc + IST_OFFSET
    jd_now = datetime_to_julday(now_utc)

    sun = get_sun_times_details(now_ist, lat, lon)
    sunrise_jd = sun["sunrise_jd"]
    sunset_jd = sun["sunset_jd"]

    # Need "next sunrise" as a Julian Day too, for Pahar's night span.
    from sun_times import get_sunrise_jd
    next_sunrise_jd = get_sunrise_jd(sunset_jd, lat, lon)

    muhurta = get_muhurta_details(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)
    brahma = get_brahma_muhurta(sunrise_jd)
    pahar = get_pahar_details(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)

    print(f"Current IST time      : {now_ist}")
    print()
    print(f"Current Muhurta       : {muhurta['current_muhurta_number']} / 15 "
          f"-- {muhurta['current_muhurta_name']} "
          f"(each ~{muhurta['muhurta_duration_minutes']:.1f} min)")
    print(f"Abhijit Muhurta       : {muhurta['abhijit_start_ist']}  to  {muhurta['abhijit_end_ist']}")
    print(f"Brahma Muhurta        : {brahma['start_ist']}  to  {brahma['end_ist']}")
    print()
    print(f"Current Pahar         : {pahar['label']}")
    print(f"  runs                : {pahar['start_ist']}  to  {pahar['end_ist']}")
