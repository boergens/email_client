# Communications Hub

MCP tools for managing email, calendar, and text messages.

## Configuration

Copy `accounts.json.example` to `accounts.json` and configure your accounts:

```json
{
  "accounts": {
    "personal": "token_personal.json",
    "work": "token_work.json"
  },
  "default_account": "personal",
  "home_timezone": "America/Chicago"
}
```

## Available Tools

### Gmail
All Gmail tools accept an `account` parameter (configured in accounts.json).

- `list_emails` - List recent emails from inbox
- `read_email` - Read full email content
- `send_email` - Send emails (supports reply threading, CC, and BCC)
- `search_emails` - Search with Gmail query syntax

### Calendar
All Calendar tools accept an `account` parameter (configured in accounts.json).

- `list_events` - List upcoming calendar events
- `get_event` - Get details of a specific event
- `create_event` - Create a new calendar event
- `delete_event` - Delete a calendar event
- `search_events` - Search for calendar events

### Messages (iMessage/SMS)
- `list_conversations` - List recent conversations
- `read_conversation` - Read messages from a specific conversation
- `send_message` - Send an iMessage or SMS
- `search_messages` - Search messages by text content

## Guidelines

### Email
- Before drafting a reply, read recent emails with that person to understand the relationship and pick the appropriate tone automatically
- Check CC recipients from the email - they can dramatically shift tone (e.g., a VP on CC may require more formal/structured communication)
- Research CC recipients if unfamiliar to understand their role and adjust accordingly
- Preserve CC recipients from the original email when replying — do not remove anyone unless explicitly requested
- Always confirm before sending

### Calendar
- Times are interpreted in the configured home_timezone
- Check for conflicts before creating new events

### Messages
- Text messages are typically more casual than email
- Always confirm before sending
