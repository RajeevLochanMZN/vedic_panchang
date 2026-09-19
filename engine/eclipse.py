"""
engine/eclipse.py

Grahan (eclipse) detection: finds the next upcoming solar or lunar
eclipse from a given date, with start/end times and an approximate
% visibility/obscuration at the configured observer location.

*** LEAST TESTED MODULE SO FAR ***
pyswisseph's eclipse functions (sol_eclipse_when_loc, lun_eclipse_when,
lun_eclipse_how) have signatures that can't be verified without
actually running pyswisseph -- and we already hit one real mismatch
with rise_trans() needing different arguments than expected. Treat
this module the same way: run it, and if you get a TypeError or
clearly wrong-looking output, share it and we'll fix the call
signature together, the same way we fixed rise_trans and the Yoga
naming issue.

Depends on engine/ephemeris.py, engine/panchang.py (for
julday_to_ist_string), engine/config_loader.py. No PyQt / GPIO
dependencies -- pure Python, testable standalone.
"""

import os
from datetime import datetime, timezone

import swisseph as swe
from ephemeris import init_ephemeris, datetime_to_julday
from panchang import julday_to_ist_string


# =============================================================================
# Solar eclipse -- local event, depends on observer location
# =============================================================================

def get_next_solar_eclipse(jd_start: float, lat: float, lon: float, alt: float = 0):
    """
    Find the next solar eclipse visible from (lat, lon), searching
    forward from jd_start.

    Returns a dict, or None if pyswisseph reports no eclipse found
    (rare, but the search has to stop somewhere).
    """
    try:
        retflag, tret, attr = swe.sol_eclipse_when_loc(
            jd_start, geopos=(lon, lat, alt),
        )
    except Exception as e:
        return {"error": f"sol_eclipse_when_loc failed: {e}"}

    if retflag <= 0:
        return None

    # tret indices per Swiss Ephemeris docs:
    # 0 = time of maximum eclipse, 1 = first contact, 4 = last contact
    max_jd = tret[0]
    first_contact_jd = tret[1]
    last_contact_jd = tret[4]

    # attr[0] = fraction of Sun's diameter covered (magnitude)
    magnitude = attr[0]
    obscuration_percent = magnitude * 100.0

    return {
        "type": "Solar",
        "max_ist": julday_to_ist_string(max_jd),
        "start_ist": julday_to_ist_string(first_contact_jd),
        "end_ist": julday_to_ist_string(last_contact_jd),
        "visibility_percent": round(obscuration_percent, 1),
        "max_jd": max_jd,
    }


# =============================================================================
# Lunar eclipse -- global event (visible from the whole night side of
# Earth), but local magnitude/visibility still depends on location.
# =============================================================================

def get_next_lunar_eclipse(jd_start: float):
    """
    Find the next lunar eclipse anywhere on Earth, searching forward
    from jd_start (lunar eclipses aren't location-restricted the way
    solar ones are -- visible wherever the Moon is above the horizon).
    """
    try:
        retflag, tret = swe.lun_eclipse_when(jd_start)
    except Exception as e:
        return {"error": f"lun_eclipse_when failed: {e}"}

    if retflag <= 0:
        return None

    # tret indices per Swiss Ephemeris docs:
    # 0 = time of maximum eclipse
    # 2 = partial phase begin, 3 = partial phase end
    # 6 = penumbral phase begin, 7 = penumbral phase end
    #
    # NOTE: indices 2/3 are only populated when the eclipse actually
    # HAS a partial (umbral) phase. A penumbral-only eclipse leaves
    # them at 0, which converts to the Julian Day epoch (~4713 BCE)
    # and crashes date formatting -- so fall back to the penumbral
    # contact times (6/7) when 2/3 look unset (far from max_jd).
    max_jd = tret[0]
    partial_start_jd = tret[2]
    partial_end_jd = tret[3]

    if abs(partial_start_jd - max_jd) > 10 or abs(partial_end_jd - max_jd) > 10:
        # Partial-phase times are unset/nonsensical -- this is likely
        # a penumbral-only eclipse. Use penumbral contact times instead.
        partial_start_jd = tret[6]
        partial_end_jd = tret[7]
        eclipse_type_label = "Lunar (Penumbral)"
    else:
        eclipse_type_label = "Lunar"

    return {
        "type": eclipse_type_label,
        "max_jd": max_jd,
        "max_ist": julday_to_ist_string(max_jd),
        "start_ist": julday_to_ist_string(partial_start_jd),
        "end_ist": julday_to_ist_string(partial_end_jd),
    }


def get_moon_altitude(jd_ut: float, lat: float, lon: float, alt: float = 0) -> float:
    """
    Moon's altitude above the horizon (degrees) at (lat, lon) at the
    given time. Negative means below the horizon -- not visible.
    """
    # swe.azalt converts equatorial/ecliptic coords to horizontal
    # (azimuth/altitude) for a given observer location and time.
    moon_eq = swe.calc_ut(jd_ut, swe.MOON, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)[0]
    ra, dec = moon_eq[0], moon_eq[1]
    azalt = swe.azalt(jd_ut, swe.EQU2HOR, (lon, lat, alt), 0, 0, (ra, dec, 0))
    altitude = azalt[1]  # (azimuth, true_altitude, apparent_altitude)
    return altitude


def get_local_lunar_eclipse_visibility(max_jd: float, lat: float, lon: float, alt: float = 0):
    """
    Local circumstances for a lunar eclipse at (lat, lon) -- magnitude
    as seen from this specific location, PLUS a check that the Moon is
    actually above the horizon at eclipse maximum (a lunar eclipse's
    physical magnitude is the same worldwide, but it's only visible
    where the Moon is up).
    """
    try:
        retflag, attr = swe.lun_eclipse_how(max_jd, geopos=(lon, lat, alt))
    except Exception as e:
        return {"error": f"lun_eclipse_how failed: {e}"}

    # attr[0] = umbral magnitude (fraction of Moon's diameter in umbra) --
    # this is the eclipse's true physical magnitude, same everywhere the
    # Moon is visible; it does NOT by itself account for local horizon.
    umbral_magnitude = attr[0]

    moon_altitude = get_moon_altitude(max_jd, lat, lon, alt)
    visible_at_max = moon_altitude > 0

    return {
        "visibility_percent": round(max(umbral_magnitude, 0) * 100.0, 1),
        "moon_altitude_at_max_deg": round(moon_altitude, 1),
        "visible_at_max": visible_at_max,
    }


# =============================================================================
# Combined "next eclipse" helper -- whichever (solar or lunar) comes first
# =============================================================================

def get_next_eclipse(jd_start: float, lat: float, lon: float):
    """
    Whichever eclipse (solar or lunar) comes next, for the UI banner.
    Returns None if neither type finds an eclipse (shouldn't normally
    happen -- eclipses occur several times a year globally).
    """
    solar = get_next_solar_eclipse(jd_start, lat, lon)
    lunar = get_next_lunar_eclipse(jd_start)

    if lunar and "error" not in lunar:
        local_vis = get_local_lunar_eclipse_visibility(lunar["max_jd"], lat, lon)
        if "error" not in local_vis:
            lunar["visibility_percent"] = local_vis["visibility_percent"]
            lunar["visible_at_max"] = local_vis["visible_at_max"]
            lunar["moon_altitude_at_max_deg"] = local_vis["moon_altitude_at_max_deg"]

    candidates = [e for e in (solar, lunar) if e and "error" not in e]
    if not candidates:
        return solar or lunar  # return whichever error, for debugging

    candidates.sort(key=lambda e: e["max_jd"])
    return candidates[0]


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
    jd_now = datetime_to_julday(now_utc)

    print(f"Searching forward from: {now_utc}")
    print(f"Location: lat={lat}, lon={lon}")
    print()

    solar = get_next_solar_eclipse(jd_now, lat, lon)
    print("Next SOLAR eclipse at this location:")
    print(solar)
    print()

    lunar = get_next_lunar_eclipse(jd_now)
    print("Next LUNAR eclipse (global):")
    print(lunar)
    if lunar and "error" not in lunar:
        local_vis = get_local_lunar_eclipse_visibility(lunar["max_jd"], lat, lon)
        print(f"Local visibility at this location: {local_vis}")
        if not local_vis.get("visible_at_max", True):
            print("  -> Moon is BELOW the horizon at max eclipse here -- not visible locally!")
    print()

    next_overall = get_next_eclipse(jd_now, lat, lon)
    print("NEXT ECLIPSE OVERALL (for UI banner):")
    print(next_overall)
