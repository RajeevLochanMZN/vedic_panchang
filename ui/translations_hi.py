"""
ui/translations_hi.py

Shared translation tables + Devanagari font loader for the Hindi UI
build. This is a SEPARATE, standalone module -- nothing in the
English UI (page_home.py, page_panchang.py, ...) imports or is
affected by this file. Hindi pages (page_home_hi.py, and later
page_panchang_hi.py / page_calendar_hi.py) import from here so all
three share one translation table and one font-loading routine
instead of duplicating them.

NUMERALS: by explicit decision, all numbers (clock digits, dates,
Vikram Samvat year, Ghati/Pal/Vipal, "15" in muhurta counts, etc.)
stay in international form (0-9), even though headings/values are in
Devanagari script. Nothing in this file or page_home_hi.py converts
digits to Devanagari numerals (०-९) -- Python's default str()/f-string
formatting already produces plain 0-9, so this is simply a matter of
never routing numeric output through a digit-translation step.

STATUS: everything is now filled in and confirmed against real source
files -- headings, captions, and value tables (Vara, Paksha, Masa,
Ritu, Samvatsara, Tithi, Muhurta, Pahar, Nakshatra, Yoga, Karana,
Rashi, Ayana) for Home + Dainik Panchang; LOCATION_HI (extend as you
add locations); FESTIVAL_HI (all 71 distinct names from
config/festivals.yaml); and ECLIPSE_TYPE_ROOT_HI/ECLIPSE_DESCRIPTOR_HI
(confirmed against the actual engine/eclipse.py -- only 3 possible
type strings exist: "Solar", "Lunar", "Lunar (Penumbral)").
"""

import os
from PyQt5.QtGui import QFontDatabase


# =============================================================================
# Fixed UI captions -- headings, labels, static phrases. These are
# standard terms with one broadly-accepted Devanagari spelling, so
# they're filled in directly (no engine-matching needed).
# =============================================================================

# Page-1 (Home) field headings, keyed exactly like page_layout.yaml's
# page_home entries so page_home_hi.py can do HEADINGS_HI[key].
HEADINGS_HI = {
    "tithi": "तिथि",
    "vara": "वार",
    "paksha": "पक्ष",
    "masa": "मास",
    "ritu": "ऋतु",
    "vikram_samvat": "विक्रम संवत्",
    "samvatsara": "संवत्सर",
    "muhurta": "मुहूर्त",
    "pahar": "पहर",
    # Page 2 (Dainik Panchang) field headings, keyed exactly like
    # page_layout.yaml's page_panchang_left/page_panchang_right entries.
    "nakshatra": "नक्षत्र",
    "yoga": "योग",
    "karana": "करण",
    "chandra_rashi": "चंद्र राशि",
    "surya_rashi": "सूर्य राशि",
    "abhijit": "अभिजित मुहूर्त",
    "brahma": "ब्रह्म मुहूर्त",
    "ayana": "अयन",
    "sunrise": "सूर्योदय",
    "sunset": "सूर्यास्त",
    "moonrise": "चंद्रोदय",
    "moonset": "चंद्रास्त",
    "dinman": "दिनमान (दिन)",
    "ratriman": "रात्रिमान (रात्रि)",
    "day_length": "दिन की अवधि",
    "eclipse": "ग्रहण",
}

# Left-panel clock captions. IST/GMT/LMT are kept as Roman abbreviations
# (they're used as-is in Hindi almanacs/news too) -- flag if you'd
# rather have भाप्रस/ग्रीमास्ट/स्थानीय समय etc. spelled out instead.
CAPTION_IST = "IST"
CAPTION_VEDIC_TIME = "वैदिक समय"
CAPTION_GHATI = "घटी"
CAPTION_PAL = "पल"
CAPTION_VIPAL = "विपल"
CAPTION_GMT = "GMT"
CAPTION_LMT = "LMT"

# Misc fixed phrases
PHRASE_TODAY = "आज:"           # festival banner prefix ("Today: X" -> "आज: X")
PHRASE_TILL = "तक"             # tithi_till: "(till 14:32:10)" -> "(14:32:10 तक)"
PHRASE_TO = "से"               # page_panchang_hi.py range labels: "(start to end)" -> "(start से end तक)"
PHRASE_DAY_NIGHT = {"Day": "दिन", "Night": "रात्रि"}  # muhurta's "Day 4/15" -> "दिन 4/15"

# page_panchang.py hardcodes these two literal value strings directly
# (not sourced from muhurta.py's DAY_MUHURTA_NAMES list, which has its
# own separate "Vidhi (Abhijit)" and "Brahma" day-muhurta entries --
# these two are the Shubh Muhurta concepts, a different pair of
# labels; see muhurta.py's own docstring on not conflating the two).
LABEL_ABHIJIT = "अभिजित"
LABEL_BRAHMA_SHUBH = "ब्रह्म"

# strftime("%A") always returns English weekday names regardless of
# locale, so this maps that fixed set directly -- not engine-dependent.
WEEKDAY_HI = {
    "Monday": "सोमवार", "Tuesday": "मंगलवार", "Wednesday": "बुधवार",
    "Thursday": "गुरुवार", "Friday": "शुक्रवार", "Saturday": "शनिवार",
    "Sunday": "रविवार",
}

# page_calendar.py's weekday_headers list (3-letter English abbreviations
# used for the calendar's column headers) -- short Hindi forms, distinct
# from WEEKDAY_HI's full names above.
WEEKDAY_SHORT_HI = {
    "Mon": "सोम", "Tue": "मंगल", "Wed": "बुध", "Thu": "गुरु",
    "Fri": "शुक्र", "Sat": "शनि", "Sun": "रवि",
}


def translate_weekday_short(english_abbr: str) -> str:
    return WEEKDAY_SHORT_HI.get(english_abbr, english_abbr)

# strftime("%B") month names (for the date_label "%d %B %Y" format),
# same reasoning as WEEKDAY_HI.
MONTH_HI = {
    "January": "जनवरी", "February": "फरवरी", "March": "मार्च",
    "April": "अप्रैल", "May": "मई", "June": "जून",
    "July": "जुलाई", "August": "अगस्त", "September": "सितंबर",
    "October": "अक्टूबर", "November": "नवंबर", "December": "दिसंबर",
}

# strftime("%b") abbreviated month names -- eclipse_banner.py's
# format_eclipse_time() uses this form ("28 Aug 08:03:52"), so a
# separate table from MONTH_HI's full names is needed.
MONTH_ABBR_HI = {
    "Jan": "जन", "Feb": "फर", "Mar": "मार्च", "Apr": "अप्र", "May": "मई",
    "Jun": "जून", "Jul": "जुल", "Aug": "अग", "Sep": "सित", "Oct": "अक्तू",
    "Nov": "नव", "Dec": "दिस",
}


def translate_month_abbr(english_abbr: str) -> str:
    return MONTH_ABBR_HI.get(english_abbr, english_abbr)


def hi_date_short(short_str: str) -> str:
    """
    Convert eclipse_banner.py's 'DD Mon HH:MM:SS' format (e.g.
    '28 Aug 08:03:52') into the same shape with a Hindi month
    abbreviation -- '28 अग 08:03:52'. Day number and time stay
    international-numeral, unchanged. Falls back to the original
    string unchanged if it isn't in the expected 3-part shape.
    """
    parts = short_str.split(" ", 2)
    if len(parts) == 3:
        day, mon, time = parts
        return f"{day} {translate_month_abbr(mon)} {time}"
    return short_str


# City/place names are free-text user config (settings.yaml), not a
# fixed engine enum -- this table only covers names actually in use,
# add more as needed. Falls back to the English name if not listed,
# same pattern as translate_value().
LOCATION_HI = {
    "Ujjain": "उज्जैन",
}


def translate_location(english_name: str) -> str:
    return LOCATION_HI.get(english_name, english_name)


# eclipse_banner.py's "type" string, from engine/eclipse.py (now
# confirmed -- CONFIRMED exact set: get_next_solar_eclipse() always
# returns "Solar"; get_next_lunar_eclipse() returns "Lunar" or
# "Lunar (Penumbral)" (the latter only for penumbral-only eclipses
# with no umbral/partial phase) -- these 3 strings are the ONLY
# possible values, nothing else needs covering.
ECLIPSE_TYPE_ROOT_HI = {"Lunar": "चंद्र", "Solar": "सूर्य"}
ECLIPSE_DESCRIPTOR_HI = {"Penumbral": "उपछाया"}


def translate_eclipse_type(type_str: str) -> str:
    if " (" in type_str and type_str.endswith(")"):
        root, _, rest = type_str.partition(" (")
        descriptor = rest[:-1]
        root_hi = ECLIPSE_TYPE_ROOT_HI.get(root, root)
        descriptor_hi = ECLIPSE_DESCRIPTOR_HI.get(descriptor, descriptor)
        return f"{root_hi} ({descriptor_hi})"
    return ECLIPSE_TYPE_ROOT_HI.get(type_str, type_str)


# Eclipse banner phrase pieces (Home page's single-line style)
LABEL_ECLIPSE_WORD = "ग्रहण"  # "चंद्र ग्रहण:" = "Lunar eclipse:"
PHRASE_NOT_VISIBLE_TEMPLATE = "{location} में दिखाई नहीं देगा"  # "(will not be visible in <location>)"

# Festival names -- keyed exactly against every distinct `name:`
# value in config/festivals.yaml (as uploaded). get_todays_festivals()
# only ever returns the `name` field (not `aliases`), so aliases
# don't need entries here. "Putrada Ekadashi" appears twice in the
# yaml (Pausha and Shravana occurrences) with the same name string --
# one entry here covers both.
FESTIVAL_HI = {
    "Makar Sankranti": "मकर संक्रांति", "Baisakhi": "बैसाखी",
    "Karka Sankranti": "कर्क संक्रांति", "Sakat Chauth": "सकट चौथ",
    "Putrada Ekadashi": "पुत्रदा एकादशी", "Vasant Panchami": "वसंत पंचमी",
    "Ratha Saptami": "रथ सप्तमी", "Bhishma Ashtami": "भीष्म अष्टमी",
    "Maha Shivaratri": "महाशिवरात्रि", "Holika Dahan": "होलिका दहन",
    "Holi": "होली", "Ugadi": "उगादी", "Gudi Padwa": "गुड़ी पड़वा",
    "Cheti Chand": "चेटी चंड", "Gauri Teej": "गौरी तीज",
    "Ram Navami": "राम नवमी", "Mahavir Jayanti": "महावीर जयंती",
    "Hanuman Jayanti": "हनुमान जयंती", "Chaitra Purnima": "चैत्र पूर्णिमा",
    "Chaitra Navaratri": "चैत्र नवरात्रि", "Akshaya Tritiya": "अक्षय तृतीया",
    "Parashurama Jayanti": "परशुराम जयंती", "Sita Navami": "सीता नवमी",
    "Narasimha Jayanti": "नरसिंह जयंती", "Buddha Purnima": "बुद्ध पूर्णिमा",
    "Shani Jayanti": "शनि जयंती", "Ganga Dussehra": "गंगा दशहरा",
    "Vat Savitri": "वट सावित्री", "Jagannath Rath Yatra": "जगन्नाथ रथ यात्रा",
    "Guru Purnima": "गुरु पूर्णिमा", "Nag Panchami": "नाग पंचमी",
    "Hariyali Teej": "हरियाली तीज", "Raksha Bandhan": "रक्षा बंधन",
    "Janmashtami": "जन्माष्टमी", "Kajari Teej": "कजरी तीज",
    "Hartalika Teej": "हरतालिका तीज", "Ganesh Chaturthi": "गणेश चतुर्थी",
    "Rishi Panchami": "ऋषि पंचमी", "Radha Ashtami": "राधा अष्टमी",
    "Vaman Jayanti": "वामन जयंती", "Anant Chaturdashi": "अनंत चतुर्दशी",
    "Mahalaya Amavasya": "महालया अमावस्या", "Sharad Navaratri": "शरद नवरात्रि",
    "Durga Ashtami": "दुर्गा अष्टमी", "Maha Navami": "महा नवमी",
    "Dussehra": "दशहरा", "Sharad Purnima": "शरद पूर्णिमा",
    "Karva Chauth": "करवा चौथ", "Ahoi Ashtami": "अहोई अष्टमी",
    "Dhanteras": "धनतेरस", "Narak Chaturdashi": "नरक चतुर्दशी",
    "Diwali": "दिवाली", "Kali Puja": "काली पूजा",
    "Govardhan Puja": "गोवर्धन पूजा", "Bhai Dooj": "भाई दूज",
    "Chhath Puja": "छठ पूजा", "Skanda Sashti": "स्कंद षष्ठी",
    "Gopashtami": "गोपाष्टमी", "Tulsi Vivah": "तुलसी विवाह",
    "Kartik Purnima": "कार्तिक पूर्णिमा", "Gita Jayanti": "गीता जयंती",
    "Dattatreya Jayanti": "दत्तात्रेय जयंती", "Nirjala Ekadashi": "निर्जला एकादशी",
    "Devshayani Ekadashi": "देवशयनी एकादशी",
    "Devutthana Ekadashi": "देवउत्थान एकादशी",
    "Mokshada Ekadashi": "मोक्षदा एकादशी", "Mauni Amavasya": "मौनी अमावस्या",
    "Vat Savitri Amavasya": "वट सावित्री अमावस्या",
    "Hariyali Amavasya": "हरियाली अमावस्या",
    "Somavati Amavasya": "सोमवती अमावस्या", "Shani Amavasya": "शनि अमावस्या",
    # Pitrupaksh (Shraddha Paksha) -- added per user request, matches
    # the 15 new entries in config/festivals.yaml (lunar_month 6,
    # tithi 15-29). "Pitrupaksh" transliterated as पितृपक्ष throughout,
    # per user's explicit naming request (not "Shraddha").
    "Pitrupaksh Purnima": "पितृपक्ष पूर्णिमा",
    "Pitrupaksh Pratipada": "पितृपक्ष प्रतिपदा",
    "Pitrupaksh Dwitiya": "पितृपक्ष द्वितीया",
    "Pitrupaksh Tritiya": "पितृपक्ष तृतीया",
    "Pitrupaksh Chaturthi": "पितृपक्ष चतुर्थी",
    "Pitrupaksh Panchami": "पितृपक्ष पंचमी",
    "Pitrupaksh Shashthi": "पितृपक्ष षष्ठी",
    "Pitrupaksh Saptami": "पितृपक्ष सप्तमी",
    "Pitrupaksh Ashtami": "पितृपक्ष अष्टमी",
    "Pitrupaksh Navami": "पितृपक्ष नवमी",
    "Pitrupaksh Dashami": "पितृपक्ष दशमी",
    "Pitrupaksh Ekadashi": "पितृपक्ष एकादशी",
    "Pitrupaksh Dwadashi": "पितृपक्ष द्वादशी",
    "Pitrupaksh Trayodashi": "पितृपक्ष त्रयोदशी",
    "Pitrupaksh Chaturdashi": "पितृपक्ष चतुर्दशी",
}


# =============================================================================
# Value translation tables -- keyed EXACTLY against the name lists in
# masa.py / time_systems.py / panchang.py / muhurta.py, so lookups are
# exact-match, not guessed.
# =============================================================================

# time_systems.py's VARA_NAMES (Monday=0..Sunday=6 order)
VARA_HI = {
    "Somvar": "सोमवार", "Mangalvar": "मंगलवार", "Budhvar": "बुधवार",
    "Guruvar": "गुरुवार", "Shukravar": "शुक्रवार", "Shanivar": "शनिवार",
    "Ravivar": "रविवार",
}

# panchang.py's NAKSHATRA_NAMES (27). Note "Shravana" appears here
# AND in MASA_HI (as a Masa name) -- no collision since they're
# separate dicts/categories, but worth knowing they're spelled
# slightly differently in Devanagari (Nakshatra: श्रवण, Masa: श्रावण).
NAKSHATRA_HI = {
    "Ashwini": "अश्विनी", "Bharani": "भरणी", "Krittika": "कृत्तिका",
    "Rohini": "रोहिणी", "Mrigashira": "मृगशिरा", "Ardra": "आर्द्रा",
    "Punarvasu": "पुनर्वसु", "Pushya": "पुष्य", "Ashlesha": "आश्लेषा",
    "Magha": "मघा", "Purva Phalguni": "पूर्वा फाल्गुनी",
    "Uttara Phalguni": "उत्तरा फाल्गुनी", "Hasta": "हस्त", "Chitra": "चित्रा",
    "Swati": "स्वाति", "Vishakha": "विशाखा", "Anuradha": "अनुराधा",
    "Jyeshtha": "ज्येष्ठा", "Mula": "मूल", "Purva Ashadha": "पूर्वाषाढ़ा",
    "Uttara Ashadha": "उत्तराषाढ़ा", "Shravana": "श्रवण", "Dhanishta": "धनिष्ठा",
    "Shatabhisha": "शतभिषा", "Purva Bhadrapada": "पूर्वा भाद्रपदा",
    "Uttara Bhadrapada": "उत्तरा भाद्रपदा", "Revati": "रेवती",
}

# panchang.py's YOGA_NAMES (27). "Shukla"/"Brahma"/"Indra" also
# reappear here from other categories (Paksha/Muhurta) -- again no
# collision, separate dicts.
YOGA_HI = {
    "Vishkambha": "विष्कम्भ", "Priti": "प्रीति", "Ayushman": "आयुष्मान",
    "Saubhagya": "सौभाग्य", "Shobhana": "शोभन", "Atiganda": "अतिगण्ड",
    "Sukarma": "सुकर्मा", "Dhriti": "धृति", "Shula": "शूल", "Ganda": "गण्ड",
    "Vriddhi": "वृद्धि", "Dhruva": "ध्रुव", "Vyaghata": "व्याघात",
    "Harshana": "हर्षण", "Vajra": "वज्र", "Siddhi": "सिद्धि",
    "Vyatipata": "व्यतीपात", "Variyana": "वरीयान्", "Parigha": "परिघ",
    "Shiva": "शिव", "Siddha": "सिद्ध", "Sadhya": "साध्य", "Shubha": "शुभ",
    "Shukla": "शुक्ल", "Brahma": "ब्रह्म", "Indra": "इन्द्र", "Vaidhriti": "वैधृति",
}

# panchang.py's get_karana_name() -- 4 fixed names + the 7 movable
# names that cycle. get_karana_details()['name'] is always exactly
# one of these 11 strings, never combined with anything else.
KARANA_HI = {
    "Kimstughna": "किंस्तुघ्न", "Bava": "बव", "Balava": "बालव",
    "Kaulava": "कौलव", "Taitila": "तैतिल", "Garija": "गरज",
    "Vanija": "वणिज", "Vishti": "विष्टि", "Shakuni": "शकुनि",
    "Chatushpada": "चतुष्पाद", "Naga": "नाग",
}

# rashi.py's RASHI_NAMES (12) -- shared by both Chandra Rashi and
# Surya Rashi, same list either way.
RASHI_HI = {
    "Mesha": "मेष", "Vrishabha": "वृषभ", "Mithuna": "मिथुन", "Karka": "कर्क",
    "Simha": "सिंह", "Kanya": "कन्या", "Tula": "तुला", "Vrishchika": "वृश्चिक",
    "Dhanu": "धनु", "Makara": "मकर", "Kumbha": "कुंभ", "Meena": "मीन",
}

# masa.py's get_paksha()
PAKSHA_HI = {"Shukla": "शुक्ल", "Krishna": "कृष्ण"}

# masa.py's MASA_NAMES -- BASE names only (no Adhik/Kshaya suffix).
# get_purnimanta_masa_name() can append " [ADHIK]" or
# " (Kshaya -- needs manual check)" to this; translate_masa() below
# strips that suffix, looks up the base name here, then re-appends
# the translated suffix -- a plain translate_value("masa", ...) call
# would miss on any Adhik/Kshaya month since the full string wouldn't
# match a key here.
MASA_HI = {
    "Chaitra": "चैत्र", "Vaishakha": "वैशाख", "Jyeshtha": "ज्येष्ठ",
    "Ashadha": "आषाढ़", "Shravana": "श्रावण", "Bhadrapada": "भाद्रपद",
    "Ashwin": "आश्विन", "Kartik": "कार्तिक", "Margashirsha": "मार्गशीर्ष",
    "Pausha": "पौष", "Magha": "माघ", "Phalguna": "फाल्गुन",
}
SUFFIX_ADHIK_EN = " [ADHIK]"
SUFFIX_ADHIK_HI = " [अधिक]"
SUFFIX_KSHAYA_EN = " (Kshaya -- needs manual check)"
SUFFIX_KSHAYA_HI = " (क्षय — मैन्युअल जांच आवश्यक)"

# masa.py's RITU_NAMES
RITU_HI = {
    "Vasanta": "वसंत", "Grishma": "ग्रीष्म", "Varsha": "वर्षा",
    "Sharad": "शरद", "Hemanta": "हेमंत", "Shishira": "शिशिर",
}

# masa.py's SAMVATSARA_NAMES, all 60, same order (Prabhava-first)
SAMVATSARA_HI = {
    "Prabhava": "प्रभव", "Vibhava": "विभव", "Shukla": "शुक्ल", "Pramoda": "प्रमोद",
    "Prajapati": "प्रजापति", "Angirasa": "अंगिरस", "Shrimukha": "श्रीमुख", "Bhava": "भव",
    "Yuva": "युवा", "Dhata": "धाता", "Ishvara": "ईश्वर", "Bahudhanya": "बहुधान्य",
    "Pramathi": "प्रमाथी", "Vikrama": "विक्रम", "Vrisha": "वृष", "Chitrabhanu": "चित्रभानु",
    "Svabhanu": "स्वभानु", "Tarana": "तारण", "Parthiva": "पार्थिव", "Vyaya": "व्यय",
    "Sarvajit": "सर्वजित्", "Sarvadhari": "सर्वधारी", "Virodhi": "विरोधी", "Vikriti": "विकृति",
    "Khara": "खर", "Nandana": "नंदन", "Vijaya": "विजय", "Jaya": "जय",
    "Manmatha": "मन्मथ", "Durmukhi": "दुर्मुखी", "Hemalambi": "हेमलंबी", "Vilambi": "विलंबी",
    "Vikari": "विकारी", "Sharvari": "शार्वरी", "Plava": "प्लव", "Shubhakrit": "शुभकृत्",
    "Shobhakrit": "शोभकृत्", "Krodhi": "क्रोधी", "Vishvavasu": "विश्वावसु", "Parabhava": "पराभव",
    "Plavanga": "प्लवंग", "Kilaka": "किलक", "Saumya": "सौम्य", "Sadharana": "साधारण",
    "Virodhikrit": "विरोधकृत्", "Paridhavi": "परिधावी", "Pramadi": "प्रमादी", "Ananda": "आनंद",
    "Rakshasa": "राक्षस", "Nala": "नल", "Pingala": "पिंगल", "Kalayukta": "कालयुक्त",
    "Siddharthi": "सिद्धार्थी", "Raudra": "रौद्र", "Durmati": "दुर्मति", "Dundubhi": "दुंदुभि",
    "Rudhirodgari": "रुधिरोद्गारी", "Raktakshi": "रक्ताक्षी", "Krodhana": "क्रोधन", "Kshaya": "क्षय",
}

# panchang.py's TITHI_NAMES (14) plus Purnima/Amavasya (the two
# special-cased 15th-tithi names) -- get_tithi_details()['name']
# is always one of these 16, never combined with Paksha text.
TITHI_HI = {
    "Pratipada": "प्रतिपदा", "Dwitiya": "द्वितीया", "Tritiya": "तृतीया",
    "Chaturthi": "चतुर्थी", "Panchami": "पंचमी", "Shashthi": "षष्ठी",
    "Saptami": "सप्तमी", "Ashtami": "अष्टमी", "Navami": "नवमी",
    "Dashami": "दशमी", "Ekadashi": "एकादशी", "Dwadashi": "द्वादशी",
    "Trayodashi": "त्रयोदशी", "Chaturdashi": "चतुर्दशी",
    "Purnima": "पूर्णिमा", "Amavasya": "अमावस्या",
}

# muhurta.py's DAY_MUHURTA_NAMES + NIGHT_MUHURTA_NAMES, merged into
# one table since current_muhurta_name can come from either list and
# only one shared "muhurta" category is looked up in the UI code.
# Note "Brahma" legitimately appears in both lists (day #9, night #8)
# per muhurta.py's own docstring -- same translation either way.
MUHURTA_HI = {
    # Day
    "Rudra": "रुद्र", "Uraga": "उरग", "Mitra": "मित्र", "Pitara": "पितर",
    "Vasu": "वसु", "Ambu": "अम्बु", "Vishwedeva": "विश्वेदेव",
    "Vidhi (Abhijit)": "विधि (अभिजित)", "Brahma": "ब्रह्म", "Indra": "इन्द्र",
    "Indragni": "इन्द्राग्नि", "Daitya": "दैत्य", "Varuna": "वरुण",
    "Aryama": "अर्यमा", "Bhaga": "भग",
    # Night (only new names beyond what the day list already covers)
    "Ishwara": "ईश्वर", "Ajaikapada": "अजैकपाद", "Ahirbudhnya": "अहिर्बुध्न्य",
    "Pusha": "पूषा", "Ashwini": "अश्विनी", "Yama": "यम", "Agni": "अग्नि",
    "Chandra": "चन्द्र", "Aditi": "अदिति", "Brihaspati": "बृहस्पति",
    "Vishnu": "विष्णु", "Surya": "सूर्य", "Tvashta": "त्वष्टा", "Samirana": "समीरण",
}

# muhurta.py's DAY_PAHAR_NAMES + NIGHT_PAHAR_NAMES
PAHAR_HI = {
    "Purvahna": "पूर्वाह्न", "Madhyahna": "मध्याह्न", "Aparahna": "अपराह्न", "Sayahna": "सायाह्न",
    "Pradosh": "प्रदोष", "Nishitha": "निशीथ", "Trijama": "त्रियामा", "Ushakal": "उषाकाल",
}

# masa.py's get_ayana()
AYANA_HI = {"Uttarayan": "उत्तरायण", "Dakshinayan": "दक्षिणायन"}

_VALUE_TABLES = {
    "vara": VARA_HI, "paksha": PAKSHA_HI, "masa": MASA_HI, "ritu": RITU_HI,
    "samvatsara": SAMVATSARA_HI, "tithi": TITHI_HI, "muhurta": MUHURTA_HI,
    "pahar": PAHAR_HI, "nakshatra": NAKSHATRA_HI, "yoga": YOGA_HI,
    "karana": KARANA_HI, "rashi": RASHI_HI, "ayana": AYANA_HI,
    "festival": FESTIVAL_HI,
}


def translate_value(category: str, english_name: str) -> str:
    """
    Look up english_name in the table for `category` (one of
    _VALUE_TABLES' keys). Falls back to the English name unchanged if
    the table doesn't have this exact key -- so a name that's missing
    or unexpectedly formatted still shows something (in English)
    rather than a blank field.
    """
    table = _VALUE_TABLES.get(category, {})
    return table.get(english_name, english_name)


def translate_masa(name_with_suffix: str) -> str:
    """
    get_purnimanta_masa_name() returns a base MASA_NAMES entry with an
    optional " [ADHIK]" or " (Kshaya -- needs manual check)" suffix
    appended. Plain translate_value("masa", ...) would miss on any
    Adhik/Kshaya month since the full string (base + suffix) isn't a
    key in MASA_HI. This strips the known suffix, translates the base
    name, and re-appends the suffix's own Hindi translation.
    """
    if name_with_suffix.endswith(SUFFIX_ADHIK_EN):
        base = name_with_suffix[: -len(SUFFIX_ADHIK_EN)]
        return MASA_HI.get(base, base) + SUFFIX_ADHIK_HI
    if name_with_suffix.endswith(SUFFIX_KSHAYA_EN):
        base = name_with_suffix[: -len(SUFFIX_KSHAYA_EN)]
        return MASA_HI.get(base, base) + SUFFIX_KSHAYA_HI
    return MASA_HI.get(name_with_suffix, name_with_suffix)


def translate_weekday(english_weekday: str) -> str:
    return WEEKDAY_HI.get(english_weekday, english_weekday)


def translate_month(english_month: str) -> str:
    return MONTH_HI.get(english_month, english_month)


# =============================================================================
# Devanagari font loading
# =============================================================================

# Expected bundled font files, relative to data/fonts/ (sibling of
# data/ephe/ used by the ephemeris). Noto Sans Devanagari is free
# (OFL license) and has full coverage for Panchang text -- download
# both weights from Google Fonts and drop them at these two paths:
#   data/fonts/NotoSansDevanagari-Regular.ttf
#   data/fonts/NotoSansDevanagari-Bold.ttf
FONT_REGULAR_FILENAME = "NotoSansDevanagari-Regular.ttf"
FONT_BOLD_FILENAME = "NotoSansDevanagari-Bold.ttf"

_font_family_cache = None


def get_devanagari_font_family(fonts_dir: str = None) -> str:
    """
    Load the bundled Devanagari font into Qt's font database (once,
    cached) and return the font family name to use in stylesheets,
    e.g. f"font-family: '{get_devanagari_font_family()}';".

    fonts_dir defaults to ../data/fonts relative to this file (same
    convention as engine/ephemeris.py's ../data/ephe). Falls back to
    "Noto Sans Devanagari" (the family name Qt would register the
    font under anyway) even if loading fails, so a system-installed
    copy of the same font (e.g. via `apt install fonts-noto-devanagari`)
    still works without the bundled .ttf files being present.
    """
    global _font_family_cache
    if _font_family_cache is not None:
        return _font_family_cache

    if fonts_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        fonts_dir = os.path.join(script_dir, "..", "data", "fonts")

    family_name = "Noto Sans Devanagari"  # fallback / expected registered name
    for filename in (FONT_REGULAR_FILENAME, FONT_BOLD_FILENAME):
        font_path = os.path.join(fonts_dir, filename)
        if os.path.isfile(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    family_name = families[0]

    _font_family_cache = family_name
    return _font_family_cache
