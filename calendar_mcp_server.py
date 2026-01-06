#!/usr/bin/env python3
"""Google Calendar MCP Server - Manage calendar events via Google Calendar API.

NOTE: Uses home_timezone from accounts.json (defaults to America/Chicago).
If the laptop's timezone differs from home, create_event will require jetlag=True
to prevent accidental scheduling mistakes when traveling.
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

SCOPES = ['https://www.googleapis.com/auth/calendar']

DIR = Path(__file__).parent
CREDENTIALS_FILE = list(DIR.glob("client_secret_*.json"))[0]
CONFIG_FILE = DIR / "accounts.json"


def load_config():
    """Load accounts configuration."""
    if not CONFIG_FILE.exists():
        return {"accounts": {"default": "calendar_token.json"}, "default_account": "default", "home_timezone": "America/Chicago"}
    return json.loads(CONFIG_FILE.read_text())


config = load_config()
# Calendar uses separate token files with calendar_ prefix
ACCOUNTS = {k: f"calendar_{v}" for k, v in config.get("accounts", {"default": "token.json"}).items()}
DEFAULT_ACCOUNT = config.get("default_account", list(ACCOUNTS.keys())[0])
HOME_TIMEZONE = config.get("home_timezone", "America/Chicago")

# Timezone offset mapping for common US timezones
TIMEZONE_OFFSETS = {
    "America/New_York": (-5, -4),
    "America/Chicago": (-6, -5),
    "America/Denver": (-7, -6),
    "America/Los_Angeles": (-8, -7),
}


def is_in_home_timezone() -> bool:
    """Check if the system is currently in the configured home timezone."""
    offset_hours = -time.timezone // 3600
    if time.daylight and time.localtime().tm_isdst:
        offset_hours = -time.altzone // 3600
    expected_offsets = TIMEZONE_OFFSETS.get(HOME_TIMEZONE, (-6, -5))
    return offset_hours in expected_offsets

mcp = FastMCP("calendar")


def get_calendar_service(account: str = ""):
    """Get authenticated Calendar service for specified account."""
    account = account or DEFAULT_ACCOUNT
    if account not in ACCOUNTS:
        raise ValueError(f"Unknown account: {account}. Valid accounts: {list(ACCOUNTS.keys())}")

    token_file = DIR / ACCOUNTS[account]
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json())

    return build('calendar', 'v3', credentials=creds)


@mcp.tool()
def list_events(days: int = 7, max_results: int = 20, account: str = "") -> str:
    """List upcoming calendar events.

    Args:
        days: Number of days to look ahead (default 7)
        max_results: Maximum number of events to return (default 20)
        account: Account name from accounts.json. Uses default if not specified.
    """
    service = get_calendar_service(account)
    now = datetime.utcnow().isoformat() + 'Z'
    end = (datetime.utcnow() + timedelta(days=days)).isoformat() + 'Z'

    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        timeMax=end,
        maxResults=max_results,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    if not events:
        return "No upcoming events found."

    output = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end_time = event['end'].get('dateTime', event['end'].get('date'))
        attendees = event.get('attendees', [])
        attendee_list = ", ".join([a.get('email', '') for a in attendees[:5]])
        if len(attendees) > 5:
            attendee_list += f" (+{len(attendees) - 5} more)"

        output.append(
            f"ID: {event['id']}\n"
            f"Summary: {event.get('summary', 'No title')}\n"
            f"Start: {start}\n"
            f"End: {end_time}\n"
            f"Location: {event.get('location', 'No location')}\n"
            f"Attendees: {attendee_list or 'None'}\n"
        )

    return "\n---\n".join(output)


@mcp.tool()
def get_event(event_id: str, account: str = "") -> str:
    """Get details of a specific calendar event.

    Args:
        event_id: The ID of the event to retrieve
        account: Account name from accounts.json. Uses default if not specified.
    """
    service = get_calendar_service(account)
    event = service.events().get(calendarId='primary', eventId=event_id).execute()

    attendees = event.get('attendees', [])
    attendee_info = "\n".join([
        f"  - {a.get('email')} ({a.get('responseStatus', 'unknown')})"
        for a in attendees
    ])

    return (
        f"Summary: {event.get('summary', 'No title')}\n"
        f"Start: {event['start'].get('dateTime', event['start'].get('date'))}\n"
        f"End: {event['end'].get('dateTime', event['end'].get('date'))}\n"
        f"Location: {event.get('location', 'No location')}\n"
        f"Description: {event.get('description', 'No description')}\n"
        f"Organizer: {event.get('organizer', {}).get('email', 'Unknown')}\n"
        f"Attendees:\n{attendee_info or '  None'}\n"
        f"Link: {event.get('htmlLink', 'No link')}"
    )


@mcp.tool()
def create_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: str = "",
    jetlag: bool = False,
    account: str = ""
) -> str:
    """Create a new calendar event.

    Times are interpreted in the configured home_timezone (see accounts.json).

    Args:
        summary: Event title
        start_time: Start time in ISO format (e.g., "2024-01-15T10:00:00")
        end_time: End time in ISO format (e.g., "2024-01-15T11:00:00")
        description: Optional event description
        location: Optional event location
        attendees: Optional comma-separated list of attendee emails
        jetlag: Set to True if traveling outside your home timezone
        account: Account name from accounts.json. Uses default if not specified.
    """
    if not is_in_home_timezone() and not jetlag:
        offset_hours = -time.timezone // 3600
        if time.daylight and time.localtime().tm_isdst:
            offset_hours = -time.altzone // 3600
        return (
            f"ERROR: Laptop is not in home timezone {HOME_TIMEZONE} (detected UTC{offset_hours:+d}). "
            f"To create events while traveling, set jetlag=True to confirm you want "
            f"to schedule in {HOME_TIMEZONE} despite being in a different timezone."
        )

    service = get_calendar_service(account)

    event = {
        'summary': summary,
        'start': {'dateTime': start_time, 'timeZone': HOME_TIMEZONE},
        'end': {'dateTime': end_time, 'timeZone': HOME_TIMEZONE},
    }

    if description:
        event['description'] = description
    if location:
        event['location'] = location
    if attendees:
        event['attendees'] = [{'email': e.strip()} for e in attendees.split(',')]

    created = service.events().insert(calendarId='primary', body=event).execute()
    return f"Event created: {created.get('htmlLink')}"


@mcp.tool()
def delete_event(event_id: str, account: str = "") -> str:
    """Delete a calendar event.

    Args:
        event_id: The ID of the event to delete
        account: Account name from accounts.json. Uses default if not specified.
    """
    service = get_calendar_service(account)
    service.events().delete(calendarId='primary', eventId=event_id).execute()
    return f"Event {event_id} deleted successfully."


@mcp.tool()
def search_events(query: str, days: int = 30, max_results: int = 20, account: str = "") -> str:
    """Search for calendar events.

    Args:
        query: Search query (matches event titles and descriptions)
        days: Number of days to search ahead (default 30)
        max_results: Maximum number of results (default 20)
        account: Account name from accounts.json. Uses default if not specified.
    """
    service = get_calendar_service(account)
    now = datetime.utcnow().isoformat() + 'Z'
    end = (datetime.utcnow() + timedelta(days=days)).isoformat() + 'Z'

    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        timeMax=end,
        maxResults=max_results,
        singleEvents=True,
        orderBy='startTime',
        q=query
    ).execute()

    events = events_result.get('items', [])
    if not events:
        return f"No events matching '{query}' found."

    output = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        output.append(
            f"ID: {event['id']}\n"
            f"Summary: {event.get('summary', 'No title')}\n"
            f"Start: {start}\n"
        )

    return "\n---\n".join(output)


if __name__ == "__main__":
    mcp.run()
