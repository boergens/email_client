# Communications Hub

This folder contains MCP tools for managing Kevin's email, calendar, and text messages.

## Address Book
Maintain `address_book.md` with contacts encountered. For each person, include:
- Email address
- Phone number
- Role/title
- Relationship to Kevin
- Communication style notes

Update this file when encountering new contacts or learning more about existing ones.

## Available Tools

### Gmail
- `list_emails` - List recent emails from inbox
- `read_email` - Read full email content
- `send_email` - Send emails (supports reply threading and CC)
- `search_emails` - Search with Gmail query syntax

### Calendar
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
- Preserve CC recipients from the original email when replying — do not remove anyone unless Kevin explicitly requests it
- Always confirm with Kevin before sending

### Calendar
- Times are interpreted as Central time (America/Chicago)
- Check for conflicts before creating new events

### Messages
- Text messages are typically more casual than email
- Always confirm with Kevin before sending
