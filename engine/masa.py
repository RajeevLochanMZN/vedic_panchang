"""
engine/masa.py

Masa (lunar month), Paksha, Samvatsara -- including Adhik Masa
(extra lunar month) and Kshaya Masa (dropped lunar month) detection.

APPROACH (Amanta system: month runs new-moon to new-moon):
  - A lunar month is named after the solar month (Rashi) the Sun is
    mostly in during that span.
  - Normally, exactly one solar transition (Sankranti) happens inside
    a lunar month -- the month is named after the Rashi the Sun moves
    INTO at that transition.
  - Adhik Masa: the Sun stays in a single Rashi for the WHOLE lunar
    month -- zero Sankranti inside it. This is the standard,
    well-documented detection rule (happens roughly once every 32-33
    months).
  - Kshaya Masa: two Sankrantis happen inside a single lunar month --
    extremely rare (roughly once per 19 years). This module DETECTS
    that case and flags it, but does not implement the full month-
    merging/renaming logic, since it's rare enough that it's more
    practical to handle by hand when it's actually about to occur
    than to fully automate now.

NOTE: the exact naming convention for which Rashi an Adhik month
"borrows" its name from varies slightly between regional traditions.
This module uses "the Rashi the Sun occupies for the whole month" as
the name -- this needs to be checked against a real Adhik Masa year
as part of the validation plan (e.g. 2026 has no Adhik Masa; recent
Adhik Masa years include 2023 (Adhik Shravana) and 2020).

Depends on engine/ephemeris.py and engine/panchang.py (reuses
get_tithi_number / find_angular_boundary for locating new moons).
No PyQt / GPIO dependencies -- pure Python, testable standalone.
"""

import os
from datetime import datetime, timezone

from ephemeris import init_ephemeris, datetime_to_julday, get_sun_longitude
from panchang import (
    get_tithi_number,
    get_tithi_name_and_paksha,
    find_angular_boundary,
    julday_to_ist_string,
)


def _jd_to_ist_datetime(jd_ut: float) -> datetime:
    """Julian Day (UT) -> IST datetime (for Gregorian-year lookups)."""
    import swisseph as swe
    from datetime import timedelta
    y, m, d, h = swe.revjul(jd_ut)
    hour = int(h)
    minute = int((h - hour) * 60)
    second = int((((h - hour) * 60) - minute) * 60)
    dt_utc = datetime(y, m, d, hour, minute, second, tzinfo=timezone.utc)
    return dt_utc + timedelta(hours=5, minutes=30)


MASA_NAMES = [
    "Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada",
    "Ashwin", "Kartik", "Margashirsha", "Pausha", "Magha", "Phalguna",
]

# 60-year Jupiter-cycle Samvatsara names, in classical order starting
# from Prabhava. Calibrated so that Vikram Samvat 2083 = "Siddharthi"
# (index 53), matching real 2026 panchang references.
SAMVATSARA_NAMES = [
    "Prabhava", "Vibhava", "Shukla", "Pramoda", "Prajapati", "Angirasa",
    "Shrimukha", "Bhava", "Yuva", "Dhata", "Ishvara", "Bahudhanya",
    "Pramathi", "Vikrama", "Vrisha", "Chitrabhanu", "Svabhanu", "Tarana",
    "Parthiva", "Vyaya", "Sarvajit", "Sarvadhari", "Virodhi", "Vikriti",
    "Khara", "Nandana", "Vijaya", "Jaya", "Manmatha", "Durmukhi",
    "Hemalambi", "Vilambi", "Vikari", "Sharvari", "Plava", "Shubhakrit",
    "Shobhakrit", "Krodhi", "Vishvavasu", "Parabhava", "Plavanga",
    "Kilaka", "Saumya", "Sadharana", "Virodhikrit", "Paridhavi",
    "Pramadi", "Ananda", "Rakshasa", "Nala", "Pingala", "Kalayukta",
    "Siddharthi", "Raudra", "Durmati", "Dundubhi", "Rudhirodgari",
    "Raktakshi", "Krodhana", "Kshaya",
]


# =============================================================================
# Sun's Rashi (solar zodiac sign), 0-11, 0 = Mesha (Aries)
# =============================================================================

def get_sun_rashi(jd_ut: float) -> int:
    """Return the Sun's sidereal Rashi index, 0-11 (0 = Mesha)."""
    return int(get_sun_longitude(jd_ut) / 30.0) % 12


# =============================================================================
# Finding the new moons (Amavasya) bracketing "now" -- the boundaries
# of the current Amanta lunar month.
# =============================================================================

def find_previous_new_moon(jd_now: float, max_days: float = 35.0) -> float:
    """Julian Day (UT) of the most recent Amavasya before jd_now
    (i.e. the start of the current lunar month)."""
    jd = jd_now
    half_day = 0.5
    steps = 0
    while get_tithi_number(jd) != 1 and steps < (max_days / half_day):
        jd -= half_day
        steps += 1
    if steps >= (max_days / half_day):
        raise RuntimeError("Could not locate previous new moon within search window")
    return find_angular_boundary(jd, get_tithi_number, 1, search_forward=False)


def find_next_new_moon(jd_now: float, max_days: float = 35.0) -> float:
    """Julian Day (UT) of the next Amavasya after jd_now
    (i.e. the end of the current lunar month)."""
    jd = jd_now
    half_day = 0.5
    steps = 0
    while get_tithi_number(jd) != 30 and steps < (max_days / half_day):
        jd += half_day
        steps += 1
    if steps >= (max_days / half_day):
        raise RuntimeError("Could not locate next new moon within search window")
    return find_angular_boundary(jd, get_tithi_number, 30, search_forward=True)


# =============================================================================
# Counting Sankrantis (Sun Rashi transitions) within the current lunar month
# =============================================================================

def count_sankrantis(jd_start: float, jd_end: float, step_days: float = 1.0):
    """
    Count how many times the Sun's Rashi changes between jd_start and
    jd_end. Returns (count, list_of_rashis_transitioned_into).
    Normally 1 (a regular month). 0 = Adhik Masa. 2+ = Kshaya-related
    (rare, flagged but not auto-resolved -- see module docstring).
    """
    count = 0
    transitions_into = []
    jd = jd_start
    prev_rashi = get_sun_rashi(jd)
    while jd < jd_end:
        jd = min(jd + step_days, jd_end)
        cur_rashi = get_sun_rashi(jd)
        if cur_rashi != prev_rashi:
            count += 1
            transitions_into.append(cur_rashi)
        prev_rashi = cur_rashi
    return count, transitions_into


# =============================================================================
# Masa (with Adhik / Kshaya detection) and Paksha
# =============================================================================

def get_masa_details(jd_ut: float) -> dict:
    """
    Full Masa detail for the current moment: name, whether it's
    Adhik or Kshaya, and the lunar month's start/end (new moon to
    new moon). This is the AMANTA name -- see get_purnimanta_masa_name()
    below for the North-India / mainstream-media convention, which
    differs during Krishna Paksha.
    """
    month_start = find_previous_new_moon(jd_ut)
    month_end = find_next_new_moon(jd_ut)

    sankranti_count, transitions_into = count_sankrantis(month_start, month_end)

    is_adhik = False
    is_kshaya = False

    if sankranti_count == 0:
        is_adhik = True
        rashi = get_sun_rashi(jd_ut)  # constant throughout the month
        masa_name = MASA_NAMES[(rashi + 1) % 12]
    elif sankranti_count == 1:
        rashi = transitions_into[0]
        masa_name = MASA_NAMES[rashi]
    else:
        is_kshaya = True
        rashi = transitions_into[-1]
        masa_name = MASA_NAMES[rashi] + " (Kshaya -- needs manual check)"

    return {
        "name": masa_name,
        "is_adhik": is_adhik,
        "is_kshaya": is_kshaya,
        "month_start_ist": julday_to_ist_string(month_start),
        "month_end_ist": julday_to_ist_string(month_end),
        "sankranti_count": sankranti_count,
    }


def get_paksha(jd_ut: float) -> str:
    """'Shukla' or 'Krishna', reusing the Tithi engine."""
    tithi_number = get_tithi_number(jd_ut)
    _, paksha = get_tithi_name_and_paksha(tithi_number)
    return paksha


def get_purnimanta_masa_name(jd_ut: float) -> str:
    """
    The Masa name under the PURNIMANTA convention (month runs full-moon
    to full-moon; used in North India and by most mainstream Hindi
    Panchang sources), as opposed to get_masa_details()'s AMANTA name
    (month runs new-moon to new-moon; kept unchanged there because
    get_vikram_samvat_year() and other logic are specifically defined
    in terms of Amanta and would break if that base calculation
    changed).

    The two conventions agree during Shukla Paksha and differ during
    Krishna Paksha, where Purnimanta shifts to the NEXT month's name
    (since a Purnimanta month ends, rather than begins, at Purnima).
    CONFIRMED against real-world data (Sept 2026): Amanta Shravana
    (Aug 12 - Sep 11, 2026) contains both Raksha Bandhan (Shravana
    Shukla Purnima -- both conventions agree) and Janmashtami (Krishna
    Ashtami -- every real source calls this "Bhadrapada", one month
    ahead of Amanta's own name for that same lunar cycle).
    """
    masa_details = get_masa_details(jd_ut)
    base_name = masa_details["name"].split(" (")[0].split(" [")[0]
    amanta_number = MASA_NAMES.index(base_name) + 1
    paksha = get_paksha(jd_ut)

    if paksha == "Krishna":
        purnimanta_number = (amanta_number % 12) + 1
    else:
        purnimanta_number = amanta_number

    purnimanta_name = MASA_NAMES[purnimanta_number - 1]

    if masa_details["is_adhik"]:
        purnimanta_name += " [ADHIK]"
    elif masa_details["is_kshaya"]:
        purnimanta_name += " (Kshaya -- needs manual check)"

    return purnimanta_name


# =============================================================================
# Samvatsara (60-year Jupiter cycle name)
# =============================================================================

def get_vikram_samvat_year(jd_ut: float) -> int:
    """
    Precise Vikram Samvat year, derived from the actual (Amanta) Masa
    and Paksha at jd_ut rather than a calendar-month approximation.
    Vikram New Year begins exactly at Chaitra Shukla Pratipada.
      - Masa 2-11: always AFTER this cycle's Pratipada -> VS = year+57
      - Masa 12 (Phalguna): always BEFORE next Pratipada -> VS = year+56
      - Masa 1 (Chaitra): Krishna = before (+56), Shukla = on/after (+57)
    """
    masa_details = get_masa_details(jd_ut)
    base_name = masa_details["name"].split(" (")[0].split(" [")[0]
    masa_number = MASA_NAMES.index(base_name) + 1
    paksha = get_paksha(jd_ut)

    ist_dt = _jd_to_ist_datetime(jd_ut)
    gregorian_year = ist_dt.year

    if masa_number == 12:
        past_pratipada_this_cycle = False
    elif masa_number == 1:
        past_pratipada_this_cycle = (paksha == "Shukla")
    else:
        past_pratipada_this_cycle = True

    return gregorian_year + (57 if past_pratipada_this_cycle else 56)


def get_samvatsara_name(vikram_year: int) -> str:
    """Name in the 60-year cycle for a given Vikram Samvat year."""
    raw = (vikram_year + 10) % 60
    index = raw if raw != 0 else 60
    return SAMVATSARA_NAMES[index - 1]


# =============================================================================
# Ritu (season) and Ayana -- both purely solar, based on Sun's current Rashi
# =============================================================================

RITU_NAMES = ["Vasanta", "Grishma", "Varsha", "Sharad", "Hemanta", "Shishira"]
UTTARAYAN_RASHIS = {9, 10, 11, 0, 1, 2}


def get_ritu(jd_ut: float) -> str:
    rashi = get_sun_rashi(jd_ut)
    return RITU_NAMES[rashi // 2]


def get_ayana(jd_ut: float) -> str:
    rashi = get_sun_rashi(jd_ut)
    return "Uttarayan" if rashi in UTTARAYAN_RASHIS else "Dakshinayan"


# =============================================================================
# Quick manual test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    from datetime import timedelta
    now_utc = datetime.now(timezone.utc)
    jd = datetime_to_julday(now_utc)
    now_ist = now_utc + timedelta(hours=5, minutes=30)

    masa = get_masa_details(jd)
    purnimanta_name = get_purnimanta_masa_name(jd)
    paksha = get_paksha(jd)
    vikram_year = get_vikram_samvat_year(jd)
    samvatsara = get_samvatsara_name(vikram_year)
    ritu = get_ritu(jd)
    ayana = get_ayana(jd)

    print(f"Current IST time   : {now_ist}")
    print()
    print(f"Masa (Amanta)      : {masa['name']}"
          f"{' [ADHIK]' if masa['is_adhik'] else ''}"
          f"{' [KSHAYA]' if masa['is_kshaya'] else ''}")
    print(f"Masa (Purnimanta)  : {purnimanta_name}")
    print(f"Paksha             : {paksha}")
    print(f"Month runs         : {masa['month_start_ist']}  to  {masa['month_end_ist']}")
    print()
    print(f"Vikram Samvat year : {vikram_year}")
    print(f"Samvatsara         : {samvatsara}")
    print()
    print(f"Ritu               : {ritu}")
    print(f"Ayana              : {ayana}")
