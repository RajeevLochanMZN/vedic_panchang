"""
ui/city_names_hi.py  --  show the clock's city in Hindi when we know it.

The city name comes from settings.yaml (typed by the user on the Wi-Fi setup page),
so its spelling can be anything.  city_hi(name, lat, lon) finds the Hindi name like this:

  0. A trailing state code as the ESP32 setup page writes it ("Muzaffarnagar, UP")
     is ignored while matching (the full typed text is still what is shown if
     nothing is found).
  1. Typed in Hindi already (Devanagari letters)        -> shown as typed.
  2. SPELLING-TOLERANT NAME MATCH.  Both the typed name and every table name /
     alias are "normalised" (lower case, no spaces / punctuation, doubled letters
     collapsed, w->v, ph->f, z->j ...), so "Muzzafarnagar", "Muzaffar Nagar" and
     "muzafarnagar" all become the same key.  If there is no exact match, the
     closest key is taken when it is similar enough (difflib, >= 0.84) AND clearly
     better than the second-best.
     Safety: the matched city must lie within 60 km of the clock's coordinates --
     a mistyped name can never pick a city on the other side of the country.
  3. BADLY MISSPELT + RIGHT PLACE: if the name matches nothing, but the clock's
     coordinates are within 5 km of a table city AND the typed name still looks a
     bit like that city (similarity >= 0.68), that city is used.  A name that looks
     nothing like it ("My Home", "Shastri Nagar") is a label the person chose on
     purpose and is shown as typed.
  4. Otherwise: the typed name is shown as typed (English).

The table is config/cities_hi.yaml (editable, no code change).
"""
import difflib
import math
import os
import re

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_TABLE = os.path.join(_HERE, "..", "config", "cities_hi.yaml")

NAME_MATCH_CUTOFF = 0.84      # how similar a misspelling must be (0..1)
NAME_MATCH_MARGIN = 0.04      # best match must beat the second best by this much
NAME_MAX_KM = 60.0            # a name match must be this close to our coordinates
COORD_ONLY_KM = 5.0           # radius for the 'badly misspelt' rule
COORD_ONLY_MIN_SIMILARITY = 0.68   # ... and how much the name must still look like the city

_cache = None


def normalise(text):
    """'Muzzafar-Nagar ' -> 'muzafarnagar'  (spelling-tolerant key)."""
    t = text.lower()
    t = re.sub(r"[^a-z]", "", t)            # drop spaces, dots, digits, accents
    t = t.replace("ph", "f").replace("w", "v").replace("z", "j").replace("q", "k")
    t = re.sub(r"(.)\1+", r"\1", t)         # collapse doubled letters
    return t


def _load():
    global _cache
    if _cache is None:
        try:
            with open(_TABLE, "r", encoding="utf-8") as f:
                cities = yaml.safe_load(f).get("cities", [])
        except Exception as e:                  # table missing / broken: just show typed names
            print("[city_names_hi] could not read cities_hi.yaml:", e)
            cities = []
        keys = {}                               # normalised name -> city dict
        for c in cities:
            for n in [c["en"]] + list(c.get("aliases", [])):
                keys.setdefault(normalise(n), c)
        _cache = (cities, keys)
    return _cache


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180.0
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742.0 * math.asin(math.sqrt(a))


def has_devanagari(text):
    return any("\u0900" <= ch <= "\u097f" for ch in text)


def city_hi(name, lat=None, lon=None):
    """Hindi name of the city if known, else `name` unchanged.  See module docstring."""
    name = (name or "").strip()
    if not name or has_devanagari(name):
        return name
    cities, keys = _load()
    if not cities:
        return name

    def near(c, km):
        return lat is None or lon is None or _km(lat, lon, c["lat"], c["lon"]) <= km

    core = re.sub(r",\s*[A-Za-z]{2}\s*$", "", name)      # "Agra, UP" -> "Agra"
    key = normalise(core)
    # 2a. exact (after normalising)
    c = keys.get(key)
    if c is not None and near(c, NAME_MAX_KM):
        return c["hi"]
    # 2b. close misspelling
    if len(key) >= 4:
        scored = sorted(((difflib.SequenceMatcher(None, key, k).ratio(), k) for k in keys),
                        reverse=True)
        if scored and scored[0][0] >= NAME_MATCH_CUTOFF:
            c = keys[scored[0][1]]
            # runner-up = best key that belongs to a DIFFERENT Hindi name (two spellings
            # of the same city, or two cities with the same Hindi name, do not compete)
            second = next((r for r, k in scored[1:] if keys[k]["hi"] != c["hi"]), 0.0)
            if scored[0][0] - second >= NAME_MATCH_MARGIN and near(c, NAME_MAX_KM):
                return c["hi"]
    # 3. badly misspelt, but the coordinates say it is that city
    if lat is not None and lon is not None:
        best = min(cities, key=lambda x: _km(lat, lon, x["lat"], x["lon"]))
        if _km(lat, lon, best["lat"], best["lon"]) <= COORD_ONLY_KM:
            names = [best["en"]] + list(best.get("aliases", []))
            sim = max(difflib.SequenceMatcher(None, key, normalise(n)).ratio() for n in names)
            if sim >= COORD_ONLY_MIN_SIMILARITY:
                return best["hi"]
    # 4. unknown: as typed
    return name


if __name__ == "__main__":
    tests = [("Muzaffarnagar", 29.4667, 77.7333), ("Muzzafarnagar", 29.47, 77.70),
             ("muzaffar nagar", 29.47, 77.70), ("Muzafarnagr", 29.47, 77.70),
             ("Bangalore", 12.97, 77.59), ("Banaras", 25.32, 82.97), ("Meerrut", 28.98, 77.71),
             ("Merut", 28.98, 77.71), ("Haridvar", 29.95, 78.16), ("Gurgaon", 28.46, 77.03),
             ("Kashipur", 29.21, 78.96), ("Delhi", 28.61, 77.21), ("My Home", 29.4667, 77.7333),
             ("Muzaffarnagar, UP", 29.471, 77.703), ("Agra, UP", 27.183, 78.017), ("Mzfrngr", 29.47, 77.70), ("Shastri Nagar", 29.4667, 77.7333), ("Aligarh", 27.88, 78.08), ("Muzaffarpur", 26.12, 85.39), ("मेरठ", 28.98, 77.71)]
    for n, la, lo in tests:
        print("%-16s -> %s" % (n, city_hi(n, la, lo)))
