"""
Quick diagnostic: prints Sun/Moon longitudes and the combined Yoga
value at a few points around today, to help track down the Yoga
discrepancy.
"""
import os
from datetime import datetime, timedelta, timezone
from ephemeris import init_ephemeris, datetime_to_julday, get_sun_longitude, get_moon_longitude

script_dir = os.path.dirname(os.path.abspath(__file__))
ephe_path = os.path.join(script_dir, "..", "data", "ephe")
init_ephemeris(ephe_path=ephe_path)

IST = timedelta(hours=5, minutes=30)

# Check a few IST timestamps around today, including the reference's
# claimed boundary (03:43 AM IST on Aug 19).
checkpoints_ist = [
    datetime(2026, 8, 18, 3, 0, 0),
    datetime(2026, 8, 19, 3, 23, 0),   # our calculated Brahma START
    datetime(2026, 8, 19, 3, 43, 0),   # reference's claimed Brahma END
    datetime(2026, 8, 19, 12, 0, 0),
    datetime(2026, 8, 20, 3, 44, 0),   # our calculated Brahma END
]

YOGA_SPAN = 360.0 / 27.0

for dt_naive in checkpoints_ist:
    dt_utc = (dt_naive - IST).replace(tzinfo=timezone.utc)
    jd = datetime_to_julday(dt_utc)
    sun = get_sun_longitude(jd)
    moon = get_moon_longitude(jd)
    combined = (sun + moon) % 360.0
    yoga_num = int(combined / YOGA_SPAN) + 1
    print(f"{dt_naive} IST -> Sun={sun:.4f} Moon={moon:.4f} "
          f"Combined={combined:.4f} YogaSlot={yoga_num}")
