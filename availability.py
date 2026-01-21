#!/usr/bin/env python3
"""Check availability across multiple calendars.

Usage:
    python availability.py                    # Check today
    python availability.py 2026-01-22         # Check specific date
    python availability.py 2026-01-22 3       # Check 3 days starting from date

Config file (availability_calendars.json):
{
    "calendars": [
        {"id": "primary", "account": "personal"},
        {"id": "shared@example.com", "account": "personal"}
    ],
    "work_hours": {"start": 8, "end": 17}
}
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DIR = Path(__file__).parent
CONFIG_FILE = DIR / "accounts.json"
CALENDARS_FILE = DIR / "availability_calendars.json"
TIMEZONE = "America/Chicago"


def load_accounts():
    """Load accounts configuration."""
    config = json.loads(CONFIG_FILE.read_text())
    return {k: {"token": f"calendar_{v['token']}", "email": v["email"]}
            for k, v in config.get("accounts", {}).items()}


def load_calendar_config():
    """Load calendar configuration for availability checking."""
    if not CALENDARS_FILE.exists():
        raise FileNotFoundError(f"Config file not found: {CALENDARS_FILE}")
    return json.loads(CALENDARS_FILE.read_text())


def get_credentials(account: str):
    """Get credentials for specified account."""
    accounts = load_accounts()
    if account not in accounts:
        raise ValueError(f"Unknown account: {account}")

    token_file = DIR / accounts[account]["token"]
    if not token_file.exists():
        raise ValueError(f"No token file for account: {account}. Run calendar_mcp_server first.")

    creds = Credentials.from_authorized_user_file(str(token_file))
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json())

    return creds


def get_busy_times(calendars: list, start: datetime, end: datetime) -> list:
    """Query freebusy API for all calendars and return merged busy periods."""
    # Group calendars by account
    by_account = {}
    for cal in calendars:
        account = cal.get("account")
        if account not in by_account:
            by_account[account] = []
        by_account[account].append(cal["id"])

    all_busy = []

    for account, cal_ids in by_account.items():
        creds = get_credentials(account)
        service = build('calendar', 'v3', credentials=creds)

        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "timeZone": TIMEZONE,
            "items": [{"id": cal_id} for cal_id in cal_ids]
        }

        result = service.freebusy().query(body=body).execute()

        for cal_id, cal_data in result.get("calendars", {}).items():
            for busy in cal_data.get("busy", []):
                busy_start = datetime.fromisoformat(busy["start"].replace("Z", "+00:00"))
                busy_end = datetime.fromisoformat(busy["end"].replace("Z", "+00:00"))
                all_busy.append((busy_start, busy_end))

    return merge_busy_periods(all_busy)


def merge_busy_periods(periods: list) -> list:
    """Merge overlapping busy periods."""
    if not periods:
        return []

    sorted_periods = sorted(periods, key=lambda x: x[0])
    merged = [sorted_periods[0]]

    for start, end in sorted_periods[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def get_free_slots(busy_periods: list, day_start: datetime, day_end: datetime) -> list:
    """Calculate free slots given busy periods and work hours."""
    tz = ZoneInfo(TIMEZONE)
    free = []
    current = day_start

    for busy_start, busy_end in busy_periods:
        busy_start_local = busy_start.astimezone(tz)
        busy_end_local = busy_end.astimezone(tz)

        # Clamp to work hours
        if busy_end_local <= day_start or busy_start_local >= day_end:
            continue

        busy_start_clamped = max(busy_start_local, day_start)
        busy_end_clamped = min(busy_end_local, day_end)

        if current < busy_start_clamped:
            free.append((current, busy_start_clamped))

        current = max(current, busy_end_clamped)

    if current < day_end:
        free.append((current, day_end))

    return free


def format_time(dt: datetime) -> str:
    """Format datetime for display."""
    return dt.strftime("%-I:%M %p")


def format_duration(start: datetime, end: datetime) -> str:
    """Format duration in hours/minutes."""
    mins = int((end - start).total_seconds() / 60)
    if mins >= 60:
        hours = mins // 60
        remaining = mins % 60
        if remaining:
            return f"{hours}h {remaining}m"
        return f"{hours}h"
    return f"{mins}m"


def main():
    config = load_calendar_config()
    calendars = config["calendars"]
    work_start_hour = config.get("work_hours", {}).get("start", 8)
    work_end_hour = config.get("work_hours", {}).get("end", 17)

    # Parse arguments
    tz = ZoneInfo(TIMEZONE)
    if len(sys.argv) > 1:
        start_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        start_date = datetime.now(tz).date()

    num_days = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    print(f"Checking availability across {len(calendars)} calendar(s)")
    print(f"Work hours: {work_start_hour}:00 AM - {work_end_hour % 12 or 12}:00 PM Central\n")

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)
        day_start = datetime(current_date.year, current_date.month, current_date.day,
                            work_start_hour, 0, tzinfo=tz)
        day_end = datetime(current_date.year, current_date.month, current_date.day,
                          work_end_hour, 0, tzinfo=tz)

        # Query full day for busy times
        query_start = datetime(current_date.year, current_date.month, current_date.day, 0, 0, tzinfo=tz)
        query_end = query_start + timedelta(days=1)

        busy = get_busy_times(calendars, query_start, query_end)
        free_slots = get_free_slots(busy, day_start, day_end)

        day_name = current_date.strftime("%A, %B %-d, %Y")
        print(f"=== {day_name} ===")

        if not free_slots:
            print("  No availability")
        else:
            for slot_start, slot_end in free_slots:
                duration = format_duration(slot_start, slot_end)
                print(f"  {format_time(slot_start)} - {format_time(slot_end)} ({duration})")
        print()


if __name__ == "__main__":
    main()
