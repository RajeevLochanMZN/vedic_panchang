"""
tests/validate_panchang.py

Automated validation script -- consolidates the real-world checks
this project did manually during development (cross-checked against
Prokerala/DrikPanchang/TimeAndDate at the time) into a repeatable
test file, so a future engine change can be checked against these
known-correct historical answers instead of re-searching the web.

Each check pins a specific historical UTC instant (so results are
reproducible regardless of when this script is run) and compares
the engine's output against the value that was verified against a
real source during development. A [FAIL] here means something in
the engine changed behavior -- worth investigating before trusting
new output.

Run: python tests\\validate_panchang.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

from ephemeris import init_ephemeris, datetime_to_julday
from panchang import get_tithi_details, get_nakshatra_details, get_yoga_details, get_karana_details
from masa import (
    get_masa_details, get_paksha, get_vikram_samvat_year, get_samvatsara_name,
    get_ritu, get_ayana, get_purnimanta_masa_name,
)
from rashi import get_surya_rashi_details
from muhurta import get_pahar_details
from sun_times import get_sun_times_details
from eclipse import get_next_lunar_eclipse, get_local_lunar_eclipse_visibility
from festivals import get_todays_festivals
from config_loader import get_location

IST_OFFSET = timedelta(hours=5, minutes=30)

PASS_COUNT = 0
FAIL_COUNT = 0


def check(label: str, actual, expected, note: str = ""):
    global PASS_COUNT, FAIL_COUNT
    ok = (actual == expected)
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    extra = f"  ({note})" if note else ""
    print(f"[{status}] {label}: got {actual!r}, expected {expected!r}{extra}")


def check_close_time(label: str, actual_ist_string: str, expected_hh_mm: str,
                      tolerance_minutes: int = 5):
    """For boundary times, allow a few minutes of tolerance rather than
    exact-second matching (matches how these were validated originally
    -- 'within about a minute' of a real reference, not bit-exact)."""
    global PASS_COUNT, FAIL_COUNT
    actual_dt = datetime.strptime(actual_ist_string, "%Y-%m-%d %H:%M:%S IST")
    actual_minutes = actual_dt.hour * 60 + actual_dt.minute
    exp_h, exp_m = map(int, expected_hh_mm.split(":"))
    expected_minutes = exp_h * 60 + exp_m
    diff = abs(actual_minutes - expected_minutes)
    ok = diff <= tolerance_minutes
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    print(f"[{status}] {label}: got {actual_dt.strftime('%H:%M')}, "
          f"expected ~{expected_hh_mm} (+/-{tolerance_minutes} min)")


def jd_for_ist(year, month, day, hour, minute):
    dt_ist = datetime(year, month, day, hour, minute, 0)
    dt_utc = (dt_ist - IST_OFFSET).replace(tzinfo=timezone.utc)
    return datetime_to_julday(dt_utc)


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)
    lat, lon = get_location()

    print("=" * 70)
    print("Panchang Clock -- automated validation against known references")
    print("=" * 70)

    # -------------------------------------------------------------------
    # Aug 19-20, 2026, Ujjain -- validated against Prokerala during dev
    # -------------------------------------------------------------------
    print("\n--- Aug 19-20, 2026 (Prokerala, Ujjain) ---")
    jd_aug19 = jd_for_ist(2026, 8, 19, 15, 0)  # afternoon, well within Saptami

    tithi = get_tithi_details(jd_aug19)
    check("Tithi name", tithi["name"], "Saptami")
    check("Paksha", tithi["paksha"], "Shukla")
    check_close_time("Tithi end time", tithi["end_ist"], "19:19")

    nak = get_nakshatra_details(jd_aug19)
    check("Nakshatra name", nak["name"], "Vishakha")

    surya = get_surya_rashi_details(jd_aug19)
    check("Surya Rashi", surya["name"], "Simha")

    masa = get_masa_details(jd_aug19)
    check("Masa name", masa["name"], "Shravana")
    check("Masa is_adhik", masa["is_adhik"], False)

    ritu = get_ritu(jd_aug19)
    check("Ritu", ritu, "Varsha")
    ayana = get_ayana(jd_aug19)
    check("Ayana", ayana, "Dakshinayan")

    vs_year = get_vikram_samvat_year(jd_aug19)
    check("Vikram Samvat year", vs_year, 2083)
    samvatsara = get_samvatsara_name(vs_year)
    check("Samvatsara", samvatsara, "Siddharthi")

    purnimanta_aug19 = get_purnimanta_masa_name(jd_aug19)
    check("Purnimanta Masa (Shukla Paksha -- should agree with Amanta)",
          purnimanta_aug19, "Shravana",
          note="Purnimanta and Amanta only diverge during Krishna Paksha")

    # Aug 20 -- Yoga = Indra (validated the specific naming-bug fix)
    jd_aug20 = jd_for_ist(2026, 8, 20, 8, 45)
    yoga = get_yoga_details(jd_aug20)
    check("Yoga name (Aug 20)", yoga["name"], "Indra",
          note="catches a regression of the earlier Yoga off-by-one naming bug")

    karana = get_karana_details(jd_aug20)
    check("Karana name (Aug 20)", karana["name"], "Bava")

    # -------------------------------------------------------------------
    # Aug 28, 2026 lunar eclipse -- validated against 5+ independent
    # sources, confirmed NOT visible from India (daytime eclipse)
    # -------------------------------------------------------------------
    print("\n--- Aug 28, 2026 lunar eclipse (TheSkyLive, TimeAndDate, etc.) ---")
    jd_search_start = jd_for_ist(2026, 8, 20, 0, 0)
    lunar = get_next_lunar_eclipse(jd_search_start)
    if lunar and "error" not in lunar:
        check_close_time("Lunar eclipse max time", lunar["max_ist"], "09:43", tolerance_minutes=5)
        local_vis = get_local_lunar_eclipse_visibility(lunar["max_jd"], lat, lon)
        check("Eclipse visible from India", local_vis.get("visible_at_max"), False,
              note="Moon is below horizon at 9:43 AM IST -- daytime eclipse")
    else:
        print("[FAIL] Could not compute the Aug 28, 2026 lunar eclipse at all")
        FAIL_COUNT += 1

    # -------------------------------------------------------------------
    # Sept 4, 2026 Janmashtami -- confirmed Purnimanta vs Amanta
    # divergence (multiple independent sources: Prokerala, AstroYogi,
    # SmartPuja, etc. all name this "Bhadrapada Krishna Ashtami",
    # despite falling inside Amanta's own Aug 12 - Sep 11 Shravana
    # window -- exactly the case get_purnimanta_masa_name()'s
    # docstring describes)
    # -------------------------------------------------------------------
    print("\n--- Sept 4, 2026 Janmashtami (Purnimanta/Amanta divergence) ---")
    jd_janmashtami = jd_for_ist(2026, 9, 4, 15, 0)  # afternoon, well within Krishna Ashtami

    masa_janmashtami = get_masa_details(jd_janmashtami)
    check("Amanta Masa name (Janmashtami)", masa_janmashtami["name"], "Shravana")
    paksha_janmashtami = get_paksha(jd_janmashtami)
    check("Paksha (Janmashtami)", paksha_janmashtami, "Krishna")

    purnimanta_janmashtami = get_purnimanta_masa_name(jd_janmashtami)
    check("Purnimanta Masa name (Janmashtami)", purnimanta_janmashtami, "Bhadrapada",
          note="every real source calls this Bhadrapada, one month ahead of Amanta's own name")

    # -------------------------------------------------------------------
    # 2023 Adhik Shravana -- confirmed across many independent sources:
    # July 18 - Aug 16, 2023, zero Sankranti inside it
    # -------------------------------------------------------------------
    print("\n--- 2023 Adhik Shravana (multiple independent sources) ---")
    jd_2023_adhik = jd_for_ist(2023, 8, 1, 12, 0)
    masa_2023 = get_masa_details(jd_2023_adhik)
    check("2023 Adhik Masa detected", masa_2023["is_adhik"], True)
    check("2023 Adhik Masa name", masa_2023["name"], "Shravana",
          note="popular convention names it after the FOLLOWING regular month")
    check("2023 Adhik Masa sankranti count", masa_2023["sankranti_count"], 0)

    jd_2023_before = jd_for_ist(2023, 7, 10, 12, 0)
    masa_before = get_masa_details(jd_2023_before)
    check("Before 2023 Adhik Masa -> not Adhik", masa_before["is_adhik"], False)

    # -------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"RESULTS: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 70)
    if FAIL_COUNT == 0:
        print("All checks passed.")
    else:
        print(f"{FAIL_COUNT} check(s) failed -- review before trusting new engine changes.")
