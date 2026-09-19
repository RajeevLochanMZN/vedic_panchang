"""
engine/festivals.py

Matches today's Tithi/Masa/Sankranti against config/festivals.yaml
(user-editable) to determine today's festival(s), if any.

Two rule types, per config/festivals.yaml's own comments:
  - tithi_at_sunrise: festival falls on the day when the specified
    Tithi prevails at TODAY's sunrise, in the specified amant lunar
    month. This is the simplest, most common matching rule -- finer
    "which of two candidate days wins" rules (vyapti/kaala) from the
    source data are NOT implemented (flagged, not silently wrong).
  - sankranti: festival falls on the day the Sun transits into the
    specified Rashi (detected by comparing today's and yesterday's
    Sun Rashi).
  - tithi_and_weekday: festival falls whenever the specified Tithi
    (usually 30 = Amavasya) coincides with a specific Vara (weekday),
    REGARDLESS of lunar month -- e.g. Somavati Amavasya (any Amavasya
    landing on a Monday) or Shani Amavasya (any Amavasya on a
    Saturday). Checked independently of the Adhik/Kshaya guard below,
    since this doesn't depend on the Masa name at all -- the tithi
    and weekday coincidence still happens regardless of what the
    lunar month is officially called that cycle.

Adhik Masa: tithi_at_sunrise and sankranti festivals are simply
skipped during an Adhik month (common real-world practice), not
shifted to the nija month. tithi_and_weekday festivals are NOT
skipped, since they don't depend on the Masa name.

Depends on engine/ephemeris.py, engine/panchang.py, engine/masa.py,
engine/time_systems.py (for get_vara), engine/config_loader.py.
No PyQt / GPIO dependencies -- pure Python, testable standalone.
"""

import os
import yaml
from datetime import datetime, timedelta, timezone

from ephemeris import init_ephemeris, datetime_to_julday
from panchang import get_tithi_number
from masa import get_masa_details, get_sun_rashi
from time_systems import get_vara
from config_loader import load_settings


def _jd_to_ist_datetime(jd_ut: float) -> datetime:
    """Julian Day (UT) -> IST datetime, for weekday lookups."""
    import swisseph as swe
    y, m, d, h = swe.revjul(jd_ut)
    hour = int(h)
    minute = int((h - hour) * 60)
    second = int((((h - hour) * 60) - minute) * 60)
    dt_utc = datetime(y, m, d, hour, minute, second, tzinfo=timezone.utc)
    return dt_utc + IST_OFFSET


IST_OFFSET = timedelta(hours=5, minutes=30)

# Our Rashi order (0=Mesha) vs the source data's sankranti_index order
# (0=Makar). Makar is 9 positions after Mesha in our own ordering.
SANKRANTI_INDEX_OFFSET = 9


def load_festivals() -> list:
    """Load config/festivals.yaml (relative to this file's location)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    festivals_path = os.path.join(script_dir, "..", "config", "festivals.yaml")
    with open(festivals_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("festivals", [])


def our_rashi_to_sankranti_index(our_rashi_index: int) -> int:
    """Convert our Rashi index (0=Mesha) to the source data's
    sankranti_index convention (0=Makar)."""
    return (our_rashi_index - SANKRANTI_INDEX_OFFSET) % 12


def get_masa_number(masa_name: str) -> int:
    """Convert a Masa name back to its 1-12 amant number."""
    from masa import MASA_NAMES
    base_name = masa_name.split(" (")[0]  # strip "(Kshaya -- ...)" suffix if present
    return MASA_NAMES.index(base_name) + 1


def get_todays_festivals(jd_at_sunrise: float, jd_yesterday_same_time: float) -> list:
    """
    Find every festival matching today. jd_at_sunrise should be the
    Julian Day (UT) of TODAY's sunrise -- that's the moment classical
    tithi_at_sunrise rules check against. jd_yesterday_same_time is
    used only to detect a Sankranti (Sun Rashi change) in the last day.
    """
    festivals = load_festivals()
    matches = []

    masa = get_masa_details(jd_at_sunrise)
    if not masa["is_adhik"] and not masa["is_kshaya"]:
        masa_number = get_masa_number(masa["name"])
        tithi_number = get_tithi_number(jd_at_sunrise)

        for f in festivals:
            if f.get("rule") == "tithi_at_sunrise":
                if f.get("lunar_month") == masa_number and f.get("tithi") == tithi_number:
                    matches.append(f)

    today_rashi = get_sun_rashi(jd_at_sunrise)
    yesterday_rashi = get_sun_rashi(jd_yesterday_same_time)
    if today_rashi != yesterday_rashi:
        sankranti_idx = our_rashi_to_sankranti_index(today_rashi)
        for f in festivals:
            if f.get("rule") == "sankranti" and f.get("sankranti_index") == sankranti_idx:
                matches.append(f)

    # tithi_and_weekday: e.g. Somavati Amavasya (any Amavasya on a
    # Monday), Shani Amavasya (any Amavasya on a Saturday). Checked
    # unconditionally -- NOT gated by the Adhik/Kshaya guard above,
    # since this doesn't depend on the Masa name at all.
    tithi_number_unconditional = get_tithi_number(jd_at_sunrise)
    today_vara = get_vara(_jd_to_ist_datetime(jd_at_sunrise))
    for f in festivals:
        if f.get("rule") == "tithi_and_weekday":
            if f.get("tithi") == tithi_number_unconditional and f.get("vara") == today_vara:
                matches.append(f)

    return matches


# =============================================================================
# Quick manual test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    from config_loader import get_location
    from sun_times import get_sun_times_details

    lat, lon = get_location()

    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc + IST_OFFSET

    sun_today = get_sun_times_details(now_ist, lat, lon)
    jd_sunrise_today = sun_today["sunrise_jd"]
    jd_sunrise_yesterday = jd_sunrise_today - 1.0  # roughly 24h earlier, close enough for Sankranti detection

    matches = get_todays_festivals(jd_sunrise_today, jd_sunrise_yesterday)

    print(f"Checking festivals for sunrise: {sun_today['sunrise_ist']}")
    print()
    if matches:
        for f in matches:
            aliases = f.get("aliases")
            alias_str = f" (aka {', '.join(aliases)})" if aliases else ""
            print(f"  * {f['name']}{alias_str}")
    else:
        print("  (no festivals today)")

    all_festivals = load_festivals()
    print()
    print(f"Total festivals loaded from config: {len(all_festivals)}")
