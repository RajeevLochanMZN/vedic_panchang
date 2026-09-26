"""
hardware/rtc.py

DS3231 real-time clock support, over raw I2C (bus 1, address 0x68 --
confirmed via `sudo i2cdetect -y 1` showing 68 in the grid).

WHY RAW I2C INSTEAD OF THE KERNEL "hwclock" APPROACH: many DS3231
tutorials add `dtoverlay=i2c-rtc,ds3231` to /boot/firmware/config.txt
so the RTC shows up as a proper kernel device (/dev/rtc0), then use
the standard `hwclock -s`/`hwclock -w` command-line tool. That's a
perfectly good approach too, but it needs an extra one-time system
config change + reboot, and can interact with Raspberry Pi OS's
built-in `fake-hwclock` package (a software stand-in used when no
real RTC is present). Since direct I2C access already works with
zero extra setup (confirmed via i2cdetect), this file talks to the
DS3231's registers directly instead -- one less moving part.

DESIGN (agreed with the user):
  1. On every boot, sync the Pi's SYSTEM clock FROM the RTC first,
     so it has *a* correct time immediately, even before network/NTP
     is available. Call sync_system_clock_from_rtc() for this, once,
     early at app startup.
  2. Opportunistically -- NOT on every boot, only roughly once a
     month -- write the corrected time back ONTO the RTC, but only
     once the system clock has itself already been NTP-corrected
     (otherwise we might overwrite a battery-backed accurate RTC
     time with an inaccurate un-synced system clock!). Call
     maybe_sync_rtc_from_system() for this periodically (e.g. from
     an existing periodic timer in the UI) -- it's cheap to call
     often, since it does nothing most of the time.
  This file deliberately does NOT touch the RTC's built-in "aging
  offset" calibration register -- the DS3231's stock accuracy
  (roughly +/-2ppm, ~1 minute/year) was judged more than good enough
  for this project's realistic offline stretches (discussed and
  explicitly decided against a self-calibrating approach as
  unnecessary complexity for the accuracy gain).
  This file does NOT replace the datetime.now()/datetime.now(timezone.utc)
  calls used throughout every UI page -- the RTC's only job is to
  keep the Pi's own system clock correct across power-offs; once
  that's done, everything else in the project keeps working exactly
  as it always has.

PREREQUISITE the user's setup script still needs to add (not yet
written): setting the Linux SYSTEM clock is a privileged operation,
so sync_system_clock_from_rtc() below needs to run `sudo date -s`.
For this to work non-interactively (no password prompt blocking
app startup), a passwordless sudo rule for exactly this command is
needed, e.g. a line like:
    rajeevlochan ALL=(ALL) NOPASSWD: /usr/bin/date -s *
in a file under /etc/sudoers.d/. Until that's added, the sync will
simply fail gracefully (see the try/except below) and the system
clock will just be whatever it already was (e.g. NTP, if online).

Reading/writing the RTC chip's own registers over I2C does NOT need
sudo -- only the "apply that time to the Linux system clock" step
does.
"""

import json
import os
import subprocess
from datetime import datetime, timedelta

import smbus  # from the python3-smbus apt package (already installed)

I2C_BUS = 1
DS3231_ADDRESS = 0x68

# DS3231 register map (standard, from the datasheet) -- each of these
# holds one time field, encoded in BCD (Binary-Coded Decimal), NOT
# plain binary -- e.g. the number 34 is stored as the byte 0x34, not
# 0x22. The two BCD helper functions below handle that conversion.
REG_SECONDS = 0x00
REG_MINUTES = 0x01
REG_HOURS = 0x02
REG_DAY_OF_WEEK = 0x03  # 1-7, DS3231 doesn't care which day is "1", only that it's consistent
REG_DATE = 0x04         # day of month
REG_MONTH = 0x05        # bit 7 of this byte is the "century" flag, see _read_rtc below
REG_YEAR = 0x06         # 00-99, always interpreted as 2000-2099 for this project

# Only re-sync the RTC chip from the (NTP-corrected) system clock
# this often at most -- see the module docstring for why monthly is
# plenty, given the DS3231's stock accuracy.
RTC_RESYNC_INTERVAL_DAYS = 30

# Small local file tracking when we last WROTE to the RTC chip (the
# RTC itself has no memory of this -- it only stores the current
# time, not a history).
_STATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "rtc_state.json"
)


def _bcd_to_int(bcd_byte: int) -> int:
    """Convert one BCD-encoded byte (e.g. 0x34) to a plain int (34)."""
    return (bcd_byte // 16) * 10 + (bcd_byte % 16)


def _int_to_bcd(value: int) -> int:
    """Convert a plain int (0-99) to one BCD-encoded byte for writing to the RTC."""
    return (value // 10) * 16 + (value % 10)


def _read_rtc() -> datetime:
    """
    Read the DS3231's current date/time directly over I2C.
    Returns a plain (timezone-naive) datetime -- the DS3231 has no
    concept of timezone, it just stores whatever wall-clock time was
    last written to it. This project always writes/reads IST-based
    system time, so treat this as "the Pi's local time", same as
    every other datetime.now() call elsewhere in the project.
    """
    bus = smbus.SMBus(I2C_BUS)
    try:
        second = _bcd_to_int(bus.read_byte_data(DS3231_ADDRESS, REG_SECONDS) & 0x7F)  # bit 7 unused
        minute = _bcd_to_int(bus.read_byte_data(DS3231_ADDRESS, REG_MINUTES))
        hour_byte = bus.read_byte_data(DS3231_ADDRESS, REG_HOURS)
        hour = _bcd_to_int(hour_byte & 0x3F)  # this project always writes 24-hour mode, so top 2 bits are unused
        date = _bcd_to_int(bus.read_byte_data(DS3231_ADDRESS, REG_DATE))
        month_byte = bus.read_byte_data(DS3231_ADDRESS, REG_MONTH)
        month = _bcd_to_int(month_byte & 0x1F)  # bit 7 is the century flag, masked off -- see note below
        year = _bcd_to_int(bus.read_byte_data(DS3231_ADDRESS, REG_YEAR))
    finally:
        bus.close()

    # This project always treats the RTC's 2-digit year as 20xx --
    # the DS3231's "century bit" toggling for the year-2100 rollover
    # is irrelevant for a device being built in 2026.
    full_year = 2000 + year

    return datetime(full_year, month, date, hour, minute, second)


def _write_rtc(dt: datetime) -> None:
    """Write a given datetime onto the DS3231's registers over I2C."""
    bus = smbus.SMBus(I2C_BUS)
    try:
        bus.write_byte_data(DS3231_ADDRESS, REG_SECONDS, _int_to_bcd(dt.second))
        bus.write_byte_data(DS3231_ADDRESS, REG_MINUTES, _int_to_bcd(dt.minute))
        bus.write_byte_data(DS3231_ADDRESS, REG_HOURS, _int_to_bcd(dt.hour))  # top bits 0 = 24-hour mode
        bus.write_byte_data(DS3231_ADDRESS, REG_DAY_OF_WEEK, dt.isoweekday())  # 1=Monday..7=Sunday, arbitrary but consistent
        bus.write_byte_data(DS3231_ADDRESS, REG_DATE, _int_to_bcd(dt.day))
        bus.write_byte_data(DS3231_ADDRESS, REG_MONTH, _int_to_bcd(dt.month))  # century bit left at 0, fine until year 2100
        bus.write_byte_data(DS3231_ADDRESS, REG_YEAR, _int_to_bcd(dt.year - 2000))
    finally:
        bus.close()


def sync_system_clock_from_rtc() -> bool:
    """
    Read the RTC chip and apply that time to the Pi's own system
    clock. Call this ONCE, early at app startup -- its whole purpose
    is giving the Pi a correct clock immediately on boot, before
    network/NTP has had any chance to run.

    Returns True on success, False if anything went wrong (missing
    sudo permission, RTC not responding, etc.) -- deliberately never
    raises, since a failure here should degrade gracefully (the
    system clock just stays whatever it already was) rather than
    crash the whole app over a clock nicety.
    """
    try:
        rtc_time = _read_rtc()
    except Exception as e:
        print(f"[rtc] Could not read RTC chip: {e}")
        return False

    formatted = rtc_time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Needs the passwordless-sudo rule described in the module
        # docstring -- without it, this fails harmlessly (caught
        # below) and the system clock is just left as-is.
        subprocess.run(
            ["sudo", "date", "-s", formatted],
            check=True,
            capture_output=True,
            timeout=5,
        )
        print(f"[rtc] System clock set from RTC: {formatted}")
        return True
    except Exception as e:
        print(f"[rtc] Could not set system clock from RTC (sudo permission not configured yet?): {e}")
        return False


def is_system_clock_ntp_synced() -> bool:
    """
    True if the Pi's system clock has itself already been corrected
    by NTP over the network. Used as a safety check before ever
    writing TO the RTC -- we never want to write an un-verified
    system clock value onto the battery-backed RTC.
    """
    try:
        result = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() == "yes"
    except Exception:
        return False


def _load_last_rtc_sync() -> datetime | None:
    """Read the timestamp of the last successful RTC write from the small local state file. None if never synced yet."""
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return datetime.fromisoformat(data["last_rtc_sync"])
    except Exception:
        return None  # file missing, corrupt, or never written -- treat as "never synced"


def _save_last_rtc_sync(when: datetime) -> None:
    """Record the timestamp of a successful RTC write to the small local state file."""
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_rtc_sync": when.isoformat()}, f)


def maybe_sync_rtc_from_system() -> bool:
    """
    Write the current (NTP-corrected) system time onto the RTC chip
    -- but ONLY if both of these are true:
      1. The system clock is currently NTP-synced (see
         is_system_clock_ntp_synced() above) -- never write an
         unverified time onto the RTC.
      2. At least RTC_RESYNC_INTERVAL_DAYS (30) have passed since
         the last time we did this -- the DS3231 doesn't need
         constant re-syncing (see module docstring).

    Cheap to call often (e.g. from an existing periodic UI timer) --
    it does nothing on most calls, only actually touches the RTC
    chip when a resync is actually due.

    Returns True if a sync actually happened, False otherwise
    (either not due yet, or not currently NTP-synced).
    """
    if not is_system_clock_ntp_synced():
        return False

    last_sync = _load_last_rtc_sync()
    now = datetime.now()
    if last_sync is not None and (now - last_sync) < timedelta(days=RTC_RESYNC_INTERVAL_DAYS):
        return False  # not due yet

    try:
        _write_rtc(now)
        _save_last_rtc_sync(now)
        print(f"[rtc] RTC chip re-synced from system clock: {now}")
        return True
    except Exception as e:
        print(f"[rtc] Could not write to RTC chip: {e}")
        return False


# =============================================================================
# Standalone test -- run directly on the Pi to check the RTC chip
# without needing the full app: `python3 hardware/rtc.py`
# =============================================================================

if __name__ == "__main__":
    print("Reading current RTC chip time...")
    try:
        print(f"RTC chip currently reads: {_read_rtc()}")
    except Exception as e:
        print(f"Could not read RTC: {e}")

    print(f"System clock NTP-synced right now? {is_system_clock_ntp_synced()}")

    print("\nAttempting to sync system clock FROM the RTC chip...")
    sync_system_clock_from_rtc()

    print("\nChecking whether an RTC-from-system resync is due...")
    did_sync = maybe_sync_rtc_from_system()
    print(f"Resync performed: {did_sync}")
