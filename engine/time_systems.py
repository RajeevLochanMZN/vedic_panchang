"""
engine/time_systems.py

Time display conversions: IST, GMT, Local Mean Time (LMT, from
configured longitude), and Vedic time (Ghati-Pal-Vipal, counted
from today's sunrise).

Depends on engine/ephemeris.py and engine/sun_times.py (for the
sunrise reference point Vedic time is measured from).
No PyQt / GPIO dependencies -- pure Python, testable standalone.
"""

import os
from datetime import datetime, timedelta, timezone

from ephemeris import init_ephemeris, datetime_to_julday

IST_OFFSET = timedelta(hours=5, minutes=30)


# =============================================================================
# IST / GMT -- trivial, just for a consistent single place to get them
# =============================================================================

def get_ist(now_utc: datetime) -> datetime:
    """IST is a fixed UTC+5:30 offset, no DST."""
    return now_utc + IST_OFFSET


def get_gmt(now_utc: datetime) -> datetime:
    """GMT/UTC, unchanged -- provided for a consistent API."""
    return now_utc


# =============================================================================
# Local Mean Time (LMT) -- true solar-based local time from longitude.
# Every 15 degrees of longitude = 1 hour offset from GMT (1 degree = 4 min).
# =============================================================================

def get_lmt(now_utc: datetime, longitude_deg: float) -> datetime:
    """
    Local Mean Time for the given longitude (degrees East positive).
    This is the "true" local solar time, distinct from IST (which is
    a fixed zone based on 82.5 degrees East, not the clock's actual
    location).
    """
    offset_hours = longitude_deg / 15.0
    return now_utc + timedelta(hours=offset_hours)


# =============================================================================
# Vedic time -- Ghati / Pal / Vipal, counted from today's sunrise.
# 1 day (sunrise to next sunrise) = 60 Ghatis
# 1 Ghati = 60 Pals  (~24 minutes)
# 1 Pal   = 60 Vipals (~24 seconds)
# So: 1 Ghati = 24 min, 1 Pal = 24 sec, 1 Vipal = 0.4 sec.
# =============================================================================

def get_vedic_time(jd_now_ut: float, sunrise_jd_ut: float) -> dict:
    """
    Ghati-Pal-Vipal elapsed since the most recent sunrise.
    sunrise_jd_ut must be the sunrise that has already occurred
    (i.e. <= jd_now_ut) -- pass today's sunrise_jd from
    sun_times.get_sun_times_details(), or yesterday's sunset-window
    equivalent if calculating before today's sunrise.
    """
    elapsed_days = jd_now_ut - sunrise_jd_ut
    if elapsed_days < 0:
        raise ValueError(
            "sunrise_jd_ut must be at or before jd_now_ut -- "
            "pass the most recent sunrise, not a future one"
        )

    elapsed_seconds = elapsed_days * 86400.0

    seconds_per_ghati = 24 * 60      # 1440
    seconds_per_pal = 24              # 24
    seconds_per_vipal = 0.4           # 0.4

    ghati = int(elapsed_seconds // seconds_per_ghati)
    remainder = elapsed_seconds - (ghati * seconds_per_ghati)

    pal = int(remainder // seconds_per_pal)
    remainder -= pal * seconds_per_pal

    vipal = int(remainder // seconds_per_vipal)

    return {"ghati": ghati, "pal": pal, "vipal": vipal}


def format_vedic_time(vedic: dict) -> str:
    return f"{vedic['ghati']} Ghati, {vedic['pal']} Pal, {vedic['vipal']} Vipal"


# =============================================================================
# Vara (weekday name) -- straightforward, but hadn't been built yet
# =============================================================================

VARA_NAMES = [
    "Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar",
]  # Python's datetime.weekday(): Monday=0 ... Sunday=6, matches this order directly


def get_vara(dt_ist: datetime) -> str:
    """Weekday name for a given IST datetime."""
    return VARA_NAMES[dt_ist.weekday()]


# =============================================================================
# Quick manual test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    from sun_times import get_sun_times_details
    from config_loader import get_location

    lat, lon = get_location()

    now_utc = datetime.now(timezone.utc)
    now_ist = get_ist(now_utc)
    now_gmt = get_gmt(now_utc)
    now_lmt = get_lmt(now_utc, lon)

    jd_now = datetime_to_julday(now_utc)
    sun_details = get_sun_times_details(now_ist, lat, lon)
    sunrise_jd = sun_details["sunrise_jd"]

    # If it's currently before today's sunrise, Vedic time should be
    # measured from YESTERDAY's sunrise instead -- not handled here for
    # simplicity (rare edge case, pre-dawn); flagged as a known gap.
    vedic = get_vedic_time(jd_now, sunrise_jd)

    print(f"Location : lat={lat}, lon={lon} (from config/settings.yaml)")
    print(f"IST : {now_ist.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"GMT : {now_gmt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"LMT : {now_lmt.strftime('%Y-%m-%d %H:%M:%S')} (for longitude {lon})")
    print(f"Vedic time (since sunrise): {format_vedic_time(vedic)}")
