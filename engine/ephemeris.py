"""
engine/ephemeris.py

pyswisseph wrapper. Sets up Lahiri ayanamsa and provides raw
Sun/Moon sidereal longitudes for a given UTC datetime + location.
This is the foundation every other engine module builds on.
No PyQt / GPIO dependencies -- pure Python, testable standalone.
"""

import swisseph as swe
from datetime import datetime, timezone


# --- Setup -----------------------------------------------------------------

def init_ephemeris(ephe_path: str = None) -> None:
    """
    Call once at startup before any calculations.
    ephe_path: folder containing the Swiss Ephemeris .se1 data files.
               If None, pyswisseph falls back to its built-in Moshier
               approximation (fine for testing, not for final eclipse work).
    """
    if ephe_path:
        swe.set_ephe_path(ephe_path)

    # Lahiri ayanamsa -- the Govt of India / most Panchang-standard sidereal mode
    swe.set_sid_mode(swe.SIDM_LAHIRI)


# --- Time conversion ---------------------------------------------------------

def datetime_to_julday(dt_utc: datetime) -> float:
    """
    Convert a timezone-aware UTC datetime into a Julian Day (UT),
    the time format Swiss Ephemeris uses internally.

    IMPORTANT: dt_utc must already be in UTC. Convert from IST
    before calling this (IST = UTC + 5:30, no DST).
    """
    if dt_utc.tzinfo is None:
        raise ValueError("datetime_to_julday requires a timezone-aware UTC datetime")
    dt_utc = dt_utc.astimezone(timezone.utc)

    hour_decimal = (
        dt_utc.hour
        + dt_utc.minute / 60.0
        + dt_utc.second / 3600.0
    )
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour_decimal)


# --- Core longitude lookups ---------------------------------------------------

def get_sidereal_longitude(jd_ut: float, body: int) -> float:
    """
    Return the sidereal (ayanamsa-corrected) ecliptic longitude
    of a body, in degrees (0-360), for the given Julian Day.

    body: one of swe.SUN, swe.MOON, etc.
    """
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    result, _ret_flags = swe.calc_ut(jd_ut, body, flags)
    longitude = result[0]
    return longitude % 360.0


def get_sun_longitude(jd_ut: float) -> float:
    """Sidereal longitude of the Sun (degrees, 0-360)."""
    return get_sidereal_longitude(jd_ut, swe.SUN)


def get_moon_longitude(jd_ut: float) -> float:
    """Sidereal longitude of the Moon (degrees, 0-360)."""
    return get_sidereal_longitude(jd_ut, swe.MOON)


def get_ayanamsa(jd_ut: float) -> float:
    """Current Lahiri ayanamsa value (degrees) for the given Julian Day."""
    return swe.get_ayanamsa_ut(jd_ut)


# --- Quick manual test -------------------------------------------------------

if __name__ == "__main__":
    # Basic smoke test: run this file directly to sanity-check the setup.
    # (No ephemeris files needed yet -- falls back to Moshier internally.)
    init_ephemeris()

    now_utc = datetime.now(timezone.utc)
    jd = datetime_to_julday(now_utc)

    sun_lon = get_sun_longitude(jd)
    moon_lon = get_moon_longitude(jd)
    ayanamsa = get_ayanamsa(jd)

    print(f"UTC time      : {now_utc}")
    print(f"Julian Day    : {jd}")
    print(f"Ayanamsa      : {ayanamsa:.6f} degrees")
    print(f"Sun longitude : {sun_lon:.6f} degrees (sidereal)")
    print(f"Moon longitude: {moon_lon:.6f} degrees (sidereal)")