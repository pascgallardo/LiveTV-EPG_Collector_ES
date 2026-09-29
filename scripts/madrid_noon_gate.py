"""Decide whether this wake-up is 12:00 in mainland Spain.

GitHub Actions cron expressions are always evaluated in UTC and do not follow
daylight saving time, so a single schedule cannot express "12:00 in Europe/Madrid"
all year: mainland Spain is UTC+1 in winter (CET) and UTC+2 in summer (CEST).

The workflow is therefore woken at both candidate UTC hours (10:00 and 11:00) and
this gate lets only the one that is actually noon in Madrid run the collector.

Exit code 0 means "run", anything else means "skip".
"""
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")
TARGET_HOUR = 12
# Scheduled workflows can start a few minutes late, so accept a window instead of
# a single instant. It stays far below the one-hour gap between the two crons.
TOLERANCE_MINUTES = 30


def is_madrid_noon(now=None):
    """True when *now* is noon in Madrid.

    *now* defaults to the current time. A naive datetime is interpreted as UTC so
    the result never depends on the machine's local timezone.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(MADRID)
    if local.hour != TARGET_HOUR:
        return False
    return local.minute < TOLERANCE_MINUTES


def main():
    now = datetime.now(timezone.utc)
    local = now.astimezone(MADRID)
    if is_madrid_noon(now):
        print(f"Madrid local time is {local:%H:%M %Z} ({now:%H:%M} UTC): running the collector.")
        return 0
    print(f"Madrid local time is {local:%H:%M %Z} ({now:%H:%M} UTC): not noon, skipping.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
