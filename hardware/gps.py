"""
hardware/gps.py

NEO-6M/NEO-8M GPS module parsing (phase 2). Provides location
(and optionally time) when a fix is available; falls back to
RTC + configured settings.yaml location otherwise.
"""
