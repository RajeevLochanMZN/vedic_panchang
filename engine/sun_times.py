"""
engine/sun_times.py

Sunrise, sunset, Dinman (day duration), Ratriman (night duration),
and total day length, for a given date and location.

Uses pyswisseph's rise_trans(), searching from local (IST) midnight
so "today's" sunrise/sunset are found correctly regardless of the
UT/IST date boundary mismatch.

Depends on engine/ephemeris.py. No PyQt / GPIO dependencies --
pure Python, testable standalone.
"""

import os
from datetime import datetime, timedelta, timezone

import swisseph as swe
from ephemeris import init_ephemeris, datetime_to_julday

IST_OFFSET = timedelta(hours=5, minutes=30)


def get_local_midnight_jd_ut(dt_ist: datetime) -> float:
    """Julian Day (UT) of the most recent local (IST) midnight."""
    midnight_ist = datetime(dt_ist.year, dt_ist.month, dt_ist.day, 0, 0, 0)
    midnight_utc = (midnight_ist - IST_OFFSET).replace(tzinfo=timezone.utc)
    return datetime_to_julday(midnight_utc)


def get_sunrise_jd(jd_ut_search_start: float, lat: float, lon: float) -> float:
    """Julian Day (UT) of the next sunrise after jd_ut_search_start."""
    _flag, tret = swe.rise_trans(
        jd_ut_search_start, swe.SUN,
        rsmi=swe.CALC_RISE | swe.BIT_DISC_CENTER,
        geopos=(lon, lat, 0),
    )
    return tret[0]


def get_sunset_jd(jd_ut_search_start: float, lat: float, lon: float) -> float:
    """Julian Day (UT) of the next sunset after jd_ut_search_start."""
    _flag, tret = swe.rise_trans(
        jd_ut_search_start, swe.SUN,
        rsmi=swe.CALC_SET | swe.BIT_DISC_CENTER,
        geopos=(lon, lat, 0),
    )
    return tret[0]


def get_moonrise_jd(jd_ut_search_start: float, lat: float, lon: float) -> float:
    """
    Julian Day (UT) of the next moonrise after jd_ut_search_start.
    Same rise_trans mechanism as sunrise, just swapping the body.
    Note: unlike the Sun, the Moon doesn't rise exactly once every
    24h (it drifts ~50 min later each day), so on rare occasions a
    moonrise might not fall within a given civil day at all -- not
    specially handled here, same simple search-forward approach as
    sunrise/sunset.
    """
    _flag, tret = swe.rise_trans(
        jd_ut_search_start, swe.MOON,
        rsmi=swe.CALC_RISE | swe.BIT_DISC_CENTER,
        geopos=(lon, lat, 0),
    )
    return tret[0]


def get_moonset_jd(jd_ut_search_start: float, lat: float, lon: float) -> float:
    """Julian Day (UT) of the next moonset after jd_ut_search_start."""
    _flag, tret = swe.rise_trans(
        jd_ut_search_start, swe.MOON,
        rsmi=swe.CALC_SET | swe.BIT_DISC_CENTER,
        geopos=(lon, lat, 0),
    )
    return tret[0]


def format_duration(days: float) -> str:
    """Convert a duration in days into 'Hh Mm Ss'."""
    total_seconds = int(round(days * 86400))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours}h {minutes}m {seconds}s"


def get_sun_times_details(dt_ist_now: datetime, lat: float, lon: float) -> dict:
    """
    Everything the UI needs for Page 3: today's sunrise, sunset,
    Dinman (day duration), Ratriman (night duration), day length.
    """
    midnight_jd = get_local_midnight_jd_ut(dt_ist_now)

    sunrise_jd = get_sunrise_jd(midnight_jd, lat, lon)
    sunset_jd = get_sunset_jd(sunrise_jd, lat, lon)
    next_sunrise_jd = get_sunrise_jd(sunset_jd, lat, lon)

    dinman_days = sunset_jd - sunrise_jd          # day duration
    ratriman_days = next_sunrise_jd - sunset_jd   # night duration
    day_length_days = dinman_days                 # sunrise-to-sunset span

    from panchang import julday_to_ist_string  # reuse existing formatter

    return {
        "sunrise_ist": julday_to_ist_string(sunrise_jd),
        "sunset_ist": julday_to_ist_string(sunset_jd),
        "next_sunrise_ist": julday_to_ist_string(next_sunrise_jd),
        "dinman": format_duration(dinman_days),
        "ratriman": format_duration(ratriman_days),
        "day_length": format_duration(day_length_days),
        "sunrise_jd": sunrise_jd,
        "sunset_jd": sunset_jd,
    }


# =============================================================================
# Quick manual test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    from config_loader import get_location
    lat, lon = get_location()

    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc + IST_OFFSET

    details = get_sun_times_details(now_ist, lat, lon)

    print(f"Location         : lat={lat}, lon={lon} (from config/settings.yaml)")
    print(f"Current IST time : {now_ist}")
    print()
    print(f"Sunrise (today)  : {details['sunrise_ist']}")
    print(f"Sunset (today)   : {details['sunset_ist']}")
    print(f"Sunrise (tomorrow): {details['next_sunrise_ist']}")
    print()
    print(f"Dinman (day)     : {details['dinman']}")
    print(f"Ratriman (night) : {details['ratriman']}")
    print(f"Day length       : {details['day_length']}")
