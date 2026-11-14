Festival rule "one date = the day with the most daytime" - dial card AND both Calendar pages
============================================================================================
Copy, commit, push, git pull on the Pi (restart the clock):
  engine/festival_span.py          the rule (new, replaces the earlier version; adds a cache: each tithi is worked out once)
  engine/calendar_festivals.py     NEW  festivals of every day of a month by that rule (used by both Calendar pages)
  ui/page_calendar_hi.py           your landscape Calendar, 6 small changes (diff below)
  ui/page_calendar_portrait_hi.py  portrait Calendar (the earlier file, now using the helper)

page_calendar_hi.py changes (all the rest is untouched):
  + from calendar_festivals import for_month
  ~ get_day_panchang_summary_hi(..., month_festivals=None): uses month_festivals.names_on(date) when given,
    otherwise the old tithi-at-sunrise lookup (fallback)
  + month_fest = for_month(year, month, lat, lon) once per month in _render_current_month, passed to each day
  If calendar_festivals cannot build (missing engine module) it prints a line and the old rule is used.

Landscape: the dial card (page_vedic_dial_hi.py) is the same class for landscape and portrait, so it
already uses festival_span.py; the landscape Calendar now uses the same helper.  Sankranti festivals still
come from festivals.py, as on the card.  Your tests for festival_span probably expect the old "8/9" lists.
Checked with real sun/moon positions (Nov 2026): 6 Dhanteras | 7 Narak Chaturdashi | 8 Diwali | 10 Govardhan Puja |
11 Bhai Dooj | 15 Skanda Shashthi + Chhath Puja, identical on the card and on both Calendar pages' code path.
