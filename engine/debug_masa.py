"""
Diagnostic: prints the exact lunar-month boundaries, Sankranti count,
and Sun's Rashi at several points, to pin down why Masa is showing
"Shravana" when real Panchang sources all say "Bhadrapada" today.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

from ephemeris import init_ephemeris, datetime_to_julday, get_sun_longitude
from masa import (
    get_masa_details, get_sun_rashi, find_previous_new_moon,
    find_next_new_moon, count_sankrantis, MASA_NAMES,
)

script_dir = os.path.dirname(os.path.abspath(__file__))
ephe_path = os.path.join(script_dir, "..", "data", "ephe")
init_ephemeris(ephe_path=ephe_path)

IST = timedelta(hours=5, minutes=30)
now_utc = datetime.now(timezone.utc)
jd_now = datetime_to_julday(now_utc)
now_ist = now_utc + IST

print(f"Current IST time: {now_ist}")
print(f"Sun longitude now: {get_sun_longitude(jd_now):.4f} degrees")
print(f"Sun Rashi index now: {get_sun_rashi(jd_now)} ({MASA_NAMES[get_sun_rashi(jd_now)]}-mapped)")
print()

month_start = find_previous_new_moon(jd_now)
month_end = find_next_new_moon(jd_now)

def jd_to_ist_str(jd):
    import swisseph as swe
    y, m, d, h = swe.revjul(jd)
    hh = int(h); mm = int((h-hh)*60); ss = int((((h-hh)*60)-mm)*60)
    dt = datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc) + IST
    return dt.strftime("%Y-%m-%d %H:%M:%S IST")

print(f"Lunar month start (prev new moon): {jd_to_ist_str(month_start)}")
print(f"Lunar month end   (next new moon): {jd_to_ist_str(month_end)}")
print(f"Sun Rashi at month start: {get_sun_rashi(month_start)} ({MASA_NAMES[get_sun_rashi(month_start)]})")
print(f"Sun Rashi at month end  : {get_sun_rashi(month_end)} ({MASA_NAMES[get_sun_rashi(month_end)]})")
print()

sankranti_count, transitions_into = count_sankrantis(month_start, month_end)
print(f"Sankranti count in this month: {sankranti_count}")
print(f"Rashi(s) transitioned into: {transitions_into} -> names: {[MASA_NAMES[r] for r in transitions_into]}")
print()

masa = get_masa_details(jd_now)
print(f"ENGINE RESULT -- Masa: {masa['name']}, is_adhik={masa['is_adhik']}, is_kshaya={masa['is_kshaya']}")
print()
print("Real-world reference: today should be Bhadrapada, Krishna Ashtami")
