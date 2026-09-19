"""
ui/eclipse_banner.py

Shared eclipse display LOGIC, reused by page_home.py (colored banner
style) and page_panchang.py (plain grid-row style). The two pages
intentionally look different, so this isn't a single visual widget --
it's the shared "should we show anything, and what does it say" logic
that was previously duplicated (and had duplicated formatting helpers)
in both pages.

Depends on engine/eclipse.py, engine/config_loader.py.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
from eclipse import get_next_eclipse

# Only show an eclipse if it's within this many days -- per the
# frozen spec ("only shown when one is occurring/upcoming"), not for
# something a year away that would just clutter the page.
VISIBILITY_WINDOW_DAYS = 3


def format_eclipse_time(ist_string: str) -> str:
    """Convert 'YYYY-MM-DD HH:MM:SS IST' into 'DD Mon HH:MM:SS'
    (abbreviated month, no year, no IST suffix)."""
    dt = datetime.strptime(ist_string, "%Y-%m-%d %H:%M:%S IST")
    return dt.strftime("%d %b %H:%M:%S")


def get_eclipse_display_info(jd_now: float, lat: float, lon: float, location_name: str):
    """
    Single source of truth for "is there a near-term eclipse, and
    what should be shown about it". Returns None if nothing should
    be displayed right now (no eclipse found, or it's more than
    VISIBILITY_WINDOW_DAYS away).

    On success, returns a dict:
        type            -- e.g. "Lunar", "Solar", "Lunar (Penumbral)"
        start_short      -- "28 Aug 08:03:52"
        end_short        -- "28 Aug 11:22:02"
        visibility_percent -- float, or None if not available
        visible_at_max   -- bool, or None if not available
        location_name    -- passed through, for convenience
    """
    eclipse = get_next_eclipse(jd_now, lat, lon)
    if not eclipse or "error" in eclipse:
        return None

    days_until = eclipse["max_jd"] - jd_now
    if not (0 <= days_until <= VISIBILITY_WINDOW_DAYS):
        return None

    return {
        "type": eclipse["type"],
        "start_short": format_eclipse_time(eclipse["start_ist"]),
        "end_short": format_eclipse_time(eclipse["end_ist"]),
        "visibility_percent": eclipse.get("visibility_percent"),
        "visible_at_max": eclipse.get("visible_at_max"),
        "location_name": location_name,
    }


def format_single_line(info: dict) -> str:
    """
    The Page 1 banner style: one combined sentence.
    e.g. "Lunar eclipse: 28 Aug 08:03:52 to 28 Aug 11:22:02, 93%
    (not visible at Ujjain)"
    """
    vis_text = ""
    if info["visibility_percent"] is not None:
        vis_text = f", {info['visibility_percent']:.0f}%"
        if info["visible_at_max"] is False:
            vis_text += f" (not visible at {info['location_name']})"
    return f"{info['type']} eclipse: {info['start_short']} to {info['end_short']}{vis_text}"


def format_two_lines(info: dict):
    """
    The Page 2 grid-row style: (type_value, line1, line2).
        type_value -- "Lunar" (goes on the main value line)
        line1      -- "28 Aug 08:03:52 to 28 Aug 11:22:02"
        line2      -- "93%, not visible in Ujjain" (or "" if no
                        visibility data at all)
    """
    line1 = f"{info['start_short']} to {info['end_short']}"
    line2 = ""
    if info["visibility_percent"] is not None:
        line2 = f"{info['visibility_percent']:.0f}%"
        if info["visible_at_max"] is False:
            line2 += f", not visible in {info['location_name']}"
    return info["type"], line1, line2
