"""
engine/panchang.py

Core Panchang five: Tithi, Nakshatra, Yoga, Karana -- each with
start/end IST. (Vara/weekday and Masa live in engine/masa.py and
engine/time_systems.py.)

All four use the same underlying idea: some angle (built from Sun
and/or Moon sidereal longitude) is divided into equal-sized slices,
and the current "number" is just which slice we're in right now.
The tricky part is finding the *exact* moment a slice boundary is
crossed -- that's what find_angular_boundary() does, using a coarse
search followed by a binary search for sub-second precision.

Depends on engine/ephemeris.py for raw Sun/Moon longitudes.
No PyQt / GPIO dependencies -- pure Python, testable standalone.
"""

import os
from datetime import datetime, timedelta, timezone

from ephemeris import (
    init_ephemeris,
    datetime_to_julday,
    get_sun_longitude,
    get_moon_longitude,
)


IST_OFFSET = timedelta(hours=5, minutes=30)  # fixed, no DST


# =============================================================================
# Shared helpers
# =============================================================================

def julday_to_ist_string(jd_ut: float) -> str:
    """Convert a Julian Day (UT) back into a readable IST date-time string."""
    import swisseph as swe
    y, m, d, h = swe.revjul(jd_ut)
    hour = int(h)
    minute = int((h - hour) * 60)
    second = int((((h - hour) * 60) - minute) * 60)
    dt_utc = datetime(y, m, d, hour, minute, second, tzinfo=timezone.utc)
    dt_ist = dt_utc + IST_OFFSET
    return dt_ist.strftime("%Y-%m-%d %H:%M:%S IST")


def find_angular_boundary(jd_start: float, get_number_func, target_number: int,
                           search_forward: bool, max_hours: float = 48.0) -> float:
    """
    Generic boundary finder, reused by Tithi / Nakshatra / Yoga / Karana.

    get_number_func: a function(jd_ut) -> int, e.g. get_tithi_number.
    target_number: the "slice number" active at jd_start (caller already
                    knows this -- passing it avoids recomputing it here).
    search_forward: True to find when this slice ENDS, False to find
                     when it STARTED.
    max_hours: safety cap on the coarse search, in case something is
               wrong and the number never seems to change.

    Returns the Julian Day (UT) of the boundary crossing.
    """
    step = 1.0 if search_forward else -1.0
    hour = 1.0 / 24.0
    jd = jd_start
    steps = 0
    max_steps = int(max_hours)

    # Coarse search: step forward/backward in ~1 hour increments until
    # the slice number changes.
    while get_number_func(jd) == target_number and steps < max_steps:
        jd += step * hour
        steps += 1

    # Fine search: binary search between the last two points to pin down
    # the boundary to within a fraction of a second.
    lo, hi = (jd - step * hour, jd) if search_forward else (jd, jd - step * hour)
    for _ in range(30):
        mid = (lo + hi) / 2.0
        if get_number_func(mid) == target_number:
            if search_forward:
                lo = mid
            else:
                hi = mid
        else:
            if search_forward:
                hi = mid
            else:
                lo = mid

    return hi if search_forward else lo


# =============================================================================
# Tithi (lunar day) -- 30 slices of 12 degrees, based on Moon-Sun elongation
# =============================================================================

TITHI_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi",
]


def get_tithi_number(jd_ut: float) -> int:
    """Return the Tithi index, 1-30. 1-15 = Shukla, 16-30 = Krishna."""
    sun_lon = get_sun_longitude(jd_ut)
    moon_lon = get_moon_longitude(jd_ut)
    elongation = (moon_lon - sun_lon) % 360.0
    return int(elongation / 12.0) + 1


def get_tithi_name_and_paksha(tithi_number: int) -> tuple[str, str]:
    """Convert a 1-30 Tithi number into (name, paksha)."""
    if 1 <= tithi_number <= 15:
        paksha = "Shukla"
        within_paksha = tithi_number
    elif 16 <= tithi_number <= 30:
        paksha = "Krishna"
        within_paksha = tithi_number - 15
    else:
        raise ValueError(f"Invalid tithi_number: {tithi_number} (must be 1-30)")

    if within_paksha == 15:
        name = "Purnima" if paksha == "Shukla" else "Amavasya"
    else:
        name = TITHI_NAMES[within_paksha - 1]
    return name, paksha


def get_tithi_details(jd_ut: float) -> dict:
    """Everything the UI needs for today's Tithi."""
    tithi_number = get_tithi_number(jd_ut)
    name, paksha = get_tithi_name_and_paksha(tithi_number)
    start_jd = find_angular_boundary(jd_ut, get_tithi_number, tithi_number, search_forward=False)
    end_jd = find_angular_boundary(jd_ut, get_tithi_number, tithi_number, search_forward=True)
    return {
        "number": tithi_number,
        "name": name,
        "paksha": paksha,
        "start_ist": julday_to_ist_string(start_jd),
        "end_ist": julday_to_ist_string(end_jd),
    }


# =============================================================================
# Nakshatra -- 27 slices of 13d20' (360/27 degrees), based on Moon longitude
# =============================================================================

NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha",
    "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha",
    "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada",
    "Uttara Bhadrapada", "Revati",
]

NAKSHATRA_SPAN = 360.0 / 27.0  # 13.3333... degrees


def get_nakshatra_number(jd_ut: float) -> int:
    """Return the Nakshatra index, 1-27, based on Moon's sidereal longitude."""
    moon_lon = get_moon_longitude(jd_ut)
    return int(moon_lon / NAKSHATRA_SPAN) + 1


def get_nakshatra_details(jd_ut: float) -> dict:
    """Everything the UI needs for today's Nakshatra."""
    nak_number = get_nakshatra_number(jd_ut)
    name = NAKSHATRA_NAMES[nak_number - 1]
    start_jd = find_angular_boundary(jd_ut, get_nakshatra_number, nak_number, search_forward=False)
    end_jd = find_angular_boundary(jd_ut, get_nakshatra_number, nak_number, search_forward=True)
    return {
        "number": nak_number,
        "name": name,
        "start_ist": julday_to_ist_string(start_jd),
        "end_ist": julday_to_ist_string(end_jd),
    }


# =============================================================================
# Yoga -- 27 slices of 13d20', based on (Sun longitude + Moon longitude)
# =============================================================================

YOGA_NAMES = [
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
    "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
    "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha",
    "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra",
    "Vaidhriti",
]


def get_yoga_number(jd_ut: float) -> int:
    """Return the Yoga index, 1-27, based on Sun longitude + Moon longitude."""
    sun_lon = get_sun_longitude(jd_ut)
    moon_lon = get_moon_longitude(jd_ut)
    combined = (sun_lon + moon_lon) % 360.0
    return int(combined / NAKSHATRA_SPAN) + 1  # same 13d20' span as Nakshatra


def get_yoga_details(jd_ut: float) -> dict:
    """Everything the UI needs for today's Yoga."""
    yoga_number = get_yoga_number(jd_ut)
    # Standard 1-indexed lookup. (An earlier "fix" here was reverted --
    # it was based on misreading an ambiguous "upto HH:MM AM" reference
    # time as same-day when it actually meant the next calendar day.
    # Cross-checked against Prokerala's Aug 20, 2026 Ujjain table, which
    # gives explicit dated transitions -- this direct mapping matches
    # those exactly: Indra Aug20 03:43 AM -> Aug21 04:24 AM.)
    name = YOGA_NAMES[yoga_number - 1]
    start_jd = find_angular_boundary(jd_ut, get_yoga_number, yoga_number, search_forward=False)
    end_jd = find_angular_boundary(jd_ut, get_yoga_number, yoga_number, search_forward=True)
    return {
        "number": yoga_number,
        "name": name,
        "start_ist": julday_to_ist_string(start_jd),
        "end_ist": julday_to_ist_string(end_jd),
    }


# =============================================================================
# Karana -- half of a Tithi. 60 per lunar month: 4 "fixed" (appear once)
# and 7 "movable" names that repeat in a cycle for the remaining 56.
# =============================================================================

KARANA_MOVABLE_NAMES = [
    "Bava", "Balava", "Kaulava", "Taitila", "Garija", "Vanija", "Vishti",
]


def get_karana_number(jd_ut: float) -> int:
    """Return the Karana index, 1-60 (each Karana spans 6 degrees)."""
    sun_lon = get_sun_longitude(jd_ut)
    moon_lon = get_moon_longitude(jd_ut)
    elongation = (moon_lon - sun_lon) % 360.0
    return int(elongation / 6.0) + 1


def get_karana_name(karana_number: int) -> str:
    """
    Convert a 1-60 Karana number into its name.
    Karana 1        = Kimstughna (fixed, start of the lunar month)
    Karana 2-57      = Bava..Vishti, cycling 8 times (7 x 8 = 56)
    Karana 58        = Shakuni (fixed)
    Karana 59        = Chatushpada (fixed)
    Karana 60        = Naga (fixed)
    """
    if karana_number == 1:
        return "Kimstughna"
    elif karana_number == 58:
        return "Shakuni"
    elif karana_number == 59:
        return "Chatushpada"
    elif karana_number == 60:
        return "Naga"
    elif 2 <= karana_number <= 57:
        idx = (karana_number - 2) % 7
        return KARANA_MOVABLE_NAMES[idx]
    else:
        raise ValueError(f"Invalid karana_number: {karana_number} (must be 1-60)")


def get_karana_details(jd_ut: float) -> dict:
    """Everything the UI needs for today's Karana."""
    karana_number = get_karana_number(jd_ut)
    name = get_karana_name(karana_number)
    start_jd = find_angular_boundary(jd_ut, get_karana_number, karana_number, search_forward=False)
    end_jd = find_angular_boundary(jd_ut, get_karana_number, karana_number, search_forward=True)
    return {
        "number": karana_number,
        "name": name,
        "start_ist": julday_to_ist_string(start_jd),
        "end_ist": julday_to_ist_string(end_jd),
    }


# =============================================================================
# Quick manual test -- run this file directly to see today's full Panchang
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    now_utc = datetime.now(timezone.utc)
    jd = datetime_to_julday(now_utc)

    tithi = get_tithi_details(jd)
    nakshatra = get_nakshatra_details(jd)
    yoga = get_yoga_details(jd)
    karana = get_karana_details(jd)

    print(f"Current UTC time : {now_utc}")
    print()
    print(f"Tithi     : {tithi['name']} ({tithi['paksha']} Paksha), "
          f"{tithi['number']}/30")
    print(f"            starts {tithi['start_ist']}, ends {tithi['end_ist']}")
    print()
    print(f"Nakshatra : {nakshatra['name']}, {nakshatra['number']}/27")
    print(f"            starts {nakshatra['start_ist']}, ends {nakshatra['end_ist']}")
    print()
    print(f"Yoga      : {yoga['name']}, {yoga['number']}/27")
    print(f"            starts {yoga['start_ist']}, ends {yoga['end_ist']}")
    print()
    print(f"Karana    : {karana['name']}, {karana['number']}/60")
    print(f"            starts {karana['start_ist']}, ends {karana['end_ist']}")
