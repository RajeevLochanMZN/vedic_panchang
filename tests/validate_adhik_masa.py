"""
tests/validate_adhik_masa.py

Historical validation: tests engine/masa.py's Adhik Masa detection
against a real, well-documented Adhik Masa year -- 2023's "Adhik
Shravana", which ran July 18 to August 16, 2023 (confirmed across
many independent sources, all agreeing: no Sun-Rashi transition
occurred during that span, which is exactly our zero-Sankranti
detection rule).

This is unlike the other engine test blocks, which always use
"now" -- this one lets you validate against an arbitrary historical
date, and is the first entry toward the tests/validate_panchang.py
this project always meant to have.
"""

import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

from ephemeris import init_ephemeris, datetime_to_julday
from masa import get_masa_details

IST_OFFSET = timedelta(hours=5, minutes=30)


def check_date(label: str, year: int, month: int, day: int, expect_adhik: bool):
    """Check the Masa on a given IST calendar date at noon (a safe
    mid-day point, well clear of any midnight/date-boundary edge
    cases)."""
    dt_ist = datetime(year, month, day, 12, 0, 0)
    dt_utc = (dt_ist - IST_OFFSET).replace(tzinfo=timezone.utc)
    jd = datetime_to_julday(dt_utc)

    masa = get_masa_details(jd)

    status = "PASS" if masa["is_adhik"] == expect_adhik else "FAIL"
    print(f"[{status}] {label} ({year}-{month:02d}-{day:02d}): "
          f"{masa['name']}, is_adhik={masa['is_adhik']}, "
          f"month runs {masa['month_start_ist']} to {masa['month_end_ist']}, "
          f"sankrantis={masa['sankranti_count']}")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    print("Adhik Masa 2023 validation")
    print("Real-world confirmed: Adhik Shravana ran July 18 - Aug 16, 2023")
    print()

    # Well inside the confirmed Adhik Maas window -- should detect is_adhik=True
    check_date("Mid-Adhik-Maas", 2023, 8, 1, expect_adhik=True)

    # A few days before it starts -- should be a NORMAL month, not Adhik
    check_date("Before Adhik Maas", 2023, 7, 10, expect_adhik=False)

    # A few days after it ends -- should be back to normal (Nija Shravana)
    check_date("After Adhik Maas", 2023, 8, 25, expect_adhik=False)

    # A random ordinary month for comparison -- should never be Adhik
    check_date("Ordinary month (control)", 2023, 1, 15, expect_adhik=False)
