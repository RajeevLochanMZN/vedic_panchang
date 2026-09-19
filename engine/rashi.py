"""
engine/rashi.py

Chandra Rashi (Moon sign) and Surya Rashi (Sun sign) -- 12 slices
of 30 degrees each, from sidereal longitude. Same technique as
Nakshatra/Yoga in panchang.py, just a coarser 30-degree slice
instead of 13d20'.

Depends on engine/ephemeris.py and engine/panchang.py (reuses
find_angular_boundary / julday_to_ist_string).
No PyQt / GPIO dependencies -- pure Python, testable standalone.
"""

import os
from datetime import datetime, timezone

from ephemeris import init_ephemeris, datetime_to_julday, get_sun_longitude, get_moon_longitude
from panchang import find_angular_boundary, julday_to_ist_string


RASHI_NAMES = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena",
]

RASHI_SPAN = 30.0


def get_moon_rashi_number(jd_ut: float) -> int:
    """Moon's sidereal Rashi index, 1-12."""
    return int(get_moon_longitude(jd_ut) / RASHI_SPAN) + 1


def get_sun_rashi_number(jd_ut: float) -> int:
    """Sun's sidereal Rashi index, 1-12."""
    return int(get_sun_longitude(jd_ut) / RASHI_SPAN) + 1


def get_chandra_rashi_details(jd_ut: float) -> dict:
    """Everything the UI needs for Chandra Rashi (Moon sign)."""
    rashi_number = get_moon_rashi_number(jd_ut)
    name = RASHI_NAMES[rashi_number - 1]
    start_jd = find_angular_boundary(jd_ut, get_moon_rashi_number, rashi_number, search_forward=False)
    end_jd = find_angular_boundary(jd_ut, get_moon_rashi_number, rashi_number, search_forward=True)
    return {
        "number": rashi_number,
        "name": name,
        "start_ist": julday_to_ist_string(start_jd),
        "end_ist": julday_to_ist_string(end_jd),
    }


def get_surya_rashi_details(jd_ut: float) -> dict:
    """Everything the UI needs for Surya Rashi (Sun sign)."""
    rashi_number = get_sun_rashi_number(jd_ut)
    name = RASHI_NAMES[rashi_number - 1]
    start_jd = find_angular_boundary(jd_ut, get_sun_rashi_number, rashi_number, search_forward=False,
                                      max_hours=48 * 30)  # Sun stays in a Rashi ~30 days, not ~1 day
    end_jd = find_angular_boundary(jd_ut, get_sun_rashi_number, rashi_number, search_forward=True,
                                    max_hours=48 * 30)
    return {
        "number": rashi_number,
        "name": name,
        "start_ist": julday_to_ist_string(start_jd),
        "end_ist": julday_to_ist_string(end_jd),
    }


# =============================================================================
# Quick manual test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    now_utc = datetime.now(timezone.utc)
    jd = datetime_to_julday(now_utc)

    chandra = get_chandra_rashi_details(jd)
    surya = get_surya_rashi_details(jd)

    print(f"Current UTC time : {now_utc}")
    print()
    print(f"Chandra Rashi (Moon): {chandra['name']}")
    print(f"  starts {chandra['start_ist']}, ends {chandra['end_ist']}")
    print()
    print(f"Surya Rashi (Sun)   : {surya['name']}")
    print(f"  starts {surya['start_ist']}, ends {surya['end_ist']}")
