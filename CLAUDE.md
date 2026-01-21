# Communications Hub

MCP tools for managing email, calendar, and text messages.

## Address Book
Maintain `address_book.md` with contacts encountered. For each person, include:
- Email address
- Role/title
- Relationship to user
- Communication style notes

Update this file when encountering new contacts or learning more about existing ones.

## Configuration

Copy `accounts.json.example` to `accounts.json` and configure your accounts:

```json
{
  "accounts": {
    "personal": {"token": "token_personal.json", "email": "you@gmail.com"},
    "work": {"token": "token_work.json", "email": "you@company.com"}
  },
  "default_account": "personal",
  "home_timezone": "America/Chicago"
}
```

The `email` field is used to verify you authenticate with the correct Google account during OAuth.

## Available Tools

### Gmail
All Gmail tools accept an `account` parameter (configured in accounts.json).

- `list_emails` - List recent emails from inbox
- `read_email` - Read full email content (shows attachment info if present)
- `send_email` - Send emails (supports reply threading, CC, BCC, and attachments)
- `search_emails` - Search with Gmail query syntax
- `download_attachment` - Download an attachment from an email to ~/Downloads or specified path

### Calendar
All Calendar tools accept an `account` parameter (configured in accounts.json).

- `list_calendars` - List all calendars accessible to an account (including shared calendars)
- `list_events` - List upcoming calendar events (supports `calendar_id` for shared calendars)
- `get_event` - Get details of a specific event
- `create_event` - Create a new calendar event
- `delete_event` - Delete a calendar event
- `search_events` - Search for calendar events (supports `calendar_id` for shared calendars)

### Availability Script
Check combined availability across multiple calendars:

```bash
python availability.py                      # Check today
python availability.py -n 5                 # Next 5 weekdays
python availability.py -n 10 --weekends     # Include weekends
python availability.py -d 2026-01-22 -n 3   # Start from specific date
```

Configure calendars in `availability_calendars.json`:
```json
{
    "calendars": [
        {"id": "primary", "account": "kevin", "name": "Kevin"},
        {"id": "someone@gmail.com", "account": "kevin", "name": "Shared cal"}
    ],
    "work_hours": {"start": 8, "end": 17}
}
```

- Excludes weekends by default (use `--weekends` to include)
- For today, only shows future availability (rounds to next 15 min)
- Use `list_calendars` MCP tool to find calendar IDs

### Messages (iMessage/SMS)
- `list_conversations` - List recent conversations
- `read_conversation` - Read messages from a specific conversation
- `send_message` - Send an iMessage or SMS
- `search_messages` - Search messages by text content

### Browser Agent
Uses OpenAI's CUA (Computer-Using Agent) model to control a browser. Requires `OPENAI_API_KEY` in `.mcp.json`.

- `browser_task` - Execute a browser task (opens visible browser window)
- `browser_task_headless` - Execute a browser task without visible window

## Guidelines

### Email
- Before sending, check the address book for the recipient's `ai_transparent` setting to determine if the email should disclose it was drafted by Claude
- Before drafting a reply, read recent emails with that person to understand the relationship and pick the appropriate tone automatically
- Check CC recipients from the email - they can dramatically shift tone (e.g., a VP on CC may require more formal/structured communication)
- Research CC recipients if unfamiliar to understand their role and adjust accordingly
- Preserve CC recipients from the original email when replying — do not remove anyone unless explicitly requested
- Always confirm before sending
- When attaching images, always convert HEIC files to JPG first (use `sips -s format jpeg input.HEIC --out output.jpg`)

### Calendar
- Times are interpreted in the configured home_timezone
- Check for conflicts before creating new events

### Messages
- Text messages are typically more casual than email
- Always confirm before sending

### Browser Agent
- For purchases, the agent will navigate to checkout but you should manually enter payment info
- Use headless mode for simple data gathering, visible mode when you need to intervene
- Costs ~$0.01-0.05 per task depending on complexity (OpenAI API charges)
