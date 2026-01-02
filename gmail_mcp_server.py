#!/usr/bin/env python3
"""Gmail MCP Server - Read and send emails via Gmail API."""

import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
]

DIR = Path(__file__).parent
CREDENTIALS_FILE = list(DIR.glob("client_secret_*.json"))[0]
TOKEN_FILE = DIR / "token.json"

mcp = FastMCP("gmail")


def get_gmail_service():
    """Get authenticated Gmail service."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


@mcp.tool()
def list_emails(max_results: int = 10, query: str = "") -> str:
    """List recent emails from inbox.

    Args:
        max_results: Maximum number of emails to return (default 10)
        query: Gmail search query (e.g., "from:example@gmail.com", "is:unread", "subject:hello")
    """
    service = get_gmail_service()
    results = service.users().messages().list(
        userId='me',
        maxResults=max_results,
        q=query or "in:inbox"
    ).execute()

    messages = results.get('messages', [])
    if not messages:
        return "No emails found."

    output = []
    for msg in messages:
        msg_data = service.users().messages().get(
            userId='me',
            id=msg['id'],
            format='metadata',
            metadataHeaders=['From', 'Subject', 'Date']
        ).execute()

        headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
        snippet = msg_data.get('snippet', '')[:100]

        output.append(f"ID: {msg['id']}\n"
                     f"From: {headers.get('From', 'Unknown')}\n"
                     f"Subject: {headers.get('Subject', 'No subject')}\n"
                     f"Date: {headers.get('Date', 'Unknown')}\n"
                     f"Preview: {snippet}...\n")

    return "\n---\n".join(output)


@mcp.tool()
def read_email(email_id: str) -> str:
    """Read the full content of a specific email.

    Args:
        email_id: The ID of the email to read (from list_emails)
    """
    service = get_gmail_service()
    msg = service.users().messages().get(userId='me', id=email_id, format='full').execute()

    headers = {h['name']: h['value'] for h in msg['payload']['headers']}

    body = ""
    payload = msg['payload']

    if 'body' in payload and payload['body'].get('data'):
        body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
    elif 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain' and part['body'].get('data'):
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                break
            elif part['mimeType'] == 'text/html' and part['body'].get('data') and not body:
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')

    return (f"From: {headers.get('From', 'Unknown')}\n"
            f"To: {headers.get('To', 'Unknown')}\n"
            f"Subject: {headers.get('Subject', 'No subject')}\n"
            f"Date: {headers.get('Date', 'Unknown')}\n"
            f"\n{body}")


def get_user_email(service):
    """Get the authenticated user's email and name."""
    profile = service.users().getProfile(userId='me').execute()
    email = profile.get('emailAddress', '')
    # Get display name from settings if available
    settings = service.users().settings().sendAs().get(userId='me', sendAsEmail=email).execute()
    display_name = settings.get('displayName', '')
    return email, display_name


@mcp.tool()
def send_email(to: str, subject: str, body: str, reply_to_id: str = "") -> str:
    """Send an email.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)
        reply_to_id: Optional email ID to reply to (adds In-Reply-To header)
    """
    service = get_gmail_service()

    message = MIMEMultipart()

    # Get sender info and set From header with display name
    sender_email, sender_name = get_user_email(service)
    message['From'] = formataddr((sender_name, sender_email))
    message['To'] = to
    message['Subject'] = subject

    thread_id = None
    if reply_to_id:
        orig = service.users().messages().get(userId='me', id=reply_to_id, format='metadata',
                                               metadataHeaders=['Message-ID']).execute()
        orig_headers = {h['name']: h['value'] for h in orig['payload']['headers']}
        thread_id = orig.get('threadId')
        if 'Message-ID' in orig_headers:
            message['In-Reply-To'] = orig_headers['Message-ID']
            message['References'] = orig_headers['Message-ID']

    message.attach(MIMEText(body, 'plain'))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

    send_body = {'raw': raw}
    if thread_id:
        send_body['threadId'] = thread_id

    sent = service.users().messages().send(userId='me', body=send_body).execute()
    return f"Email sent successfully. Message ID: {sent['id']}"


@mcp.tool()
def search_emails(query: str, max_results: int = 20) -> str:
    """Search emails using Gmail's search syntax.

    Args:
        query: Gmail search query. Examples:
               - "from:someone@example.com"
               - "subject:invoice"
               - "is:unread"
               - "after:2024/01/01 before:2024/02/01"
               - "has:attachment"
        max_results: Maximum number of results (default 20)
    """
    return list_emails(max_results=max_results, query=query)


if __name__ == "__main__":
    mcp.run()
