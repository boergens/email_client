#!/usr/bin/env python3
"""Gmail MCP Server - Read and send emails via Gmail API."""

import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr
import mimetypes
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
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

DIR = Path(__file__).parent
CREDENTIALS_FILE = list(DIR.glob("client_secret_*.json"))[0]
CONFIG_FILE = DIR / "accounts.json"


def load_config():
    """Load accounts configuration."""
    if not CONFIG_FILE.exists():
        return {"accounts": {"default": "token.json"}, "default_account": "default"}
    return json.loads(CONFIG_FILE.read_text())


config = load_config()
ACCOUNTS = config.get("accounts", {})
DEFAULT_ACCOUNT = config.get("default_account", list(ACCOUNTS.keys())[0])

mcp = FastMCP("gmail")


def get_gmail_service(account: str = ""):
    """Get authenticated Gmail service for specified account."""
    account = account or DEFAULT_ACCOUNT
    if account not in ACCOUNTS:
        raise ValueError(f"Unknown account: {account}. Valid accounts: {list(ACCOUNTS.keys())}")

    account_info = ACCOUNTS[account]
    token_file = DIR / account_info["token"]
    expected_email = account_info["email"]
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
            # Verify the authenticated email matches expected
            oauth2_service = build('oauth2', 'v2', credentials=creds)
            user_info = oauth2_service.userinfo().get().execute()
            actual_email = user_info.get('email')
            if actual_email != expected_email:
                raise ValueError(
                    f"Wrong account! Expected {expected_email} but authenticated as {actual_email}. "
                    f"Please re-authenticate with the correct Google account."
                )
        token_file.write_text(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


@mcp.tool()
def list_emails(max_results: int = 10, query: str = "", account: str = "") -> str:
    """List recent emails from inbox.

    Args:
        max_results: Maximum number of emails to return (default 10)
        query: Gmail search query (e.g., "from:example@gmail.com", "is:unread", "subject:hello")
        account: Account name from accounts.json. Uses default if not specified.
    """
    service = get_gmail_service(account)
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
def read_email(email_id: str, account: str = "") -> str:
    """Read the full content of a specific email.

    Args:
        email_id: The ID of the email to read (from list_emails)
        account: Account name from accounts.json. Uses default if not specified.
    """
    service = get_gmail_service(account)
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


def text_to_html(text: str) -> str:
    """Convert plain text to HTML with proper paragraph tags."""
    import html
    paragraphs = text.strip().split('\n\n')
    html_parts = []
    for p in paragraphs:
        # Escape HTML entities and convert single newlines to <br>
        escaped = html.escape(p.strip())
        escaped = escaped.replace('\n', '<br>\n')
        html_parts.append(f'<p>{escaped}</p>')
    return '\n'.join(html_parts)


@mcp.tool()
def send_email(to: str, subject: str, body: str, cc: str = "", bcc: str = "", reply_to_id: str = "", attachments: str = "", account: str = "") -> str:
    """Send an email.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text)
        cc: Optional CC recipients (comma-separated email addresses)
        bcc: Optional BCC recipients (comma-separated email addresses)
        reply_to_id: Optional email ID to reply to (adds In-Reply-To header)
        attachments: Optional comma-separated list of file paths to attach
        account: Account name from accounts.json. Uses default if not specified.
    """
    service = get_gmail_service(account)

    message = MIMEMultipart('mixed')

    # Get sender info and set From header with display name
    sender_email, sender_name = get_user_email(service)
    message['From'] = formataddr((sender_name, sender_email))
    message['To'] = to
    if cc:
        message['Cc'] = cc
    if bcc:
        message['Bcc'] = bcc
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

    # Create alternative part for text/html body
    text_part = MIMEMultipart('alternative')
    text_part.attach(MIMEText(body, 'plain'))
    text_part.attach(MIMEText(text_to_html(body), 'html'))
    message.attach(text_part)

    # Handle attachments
    if attachments:
        for filepath in attachments.split(','):
            filepath = filepath.strip()
            if not filepath:
                continue
            path = Path(filepath).expanduser()
            if not path.exists():
                return f"Error: Attachment not found: {filepath}"

            mime_type, _ = mimetypes.guess_type(str(path))
            if mime_type is None:
                mime_type = 'application/octet-stream'
            main_type, sub_type = mime_type.split('/', 1)

            with open(path, 'rb') as f:
                attachment = MIMEBase(main_type, sub_type)
                attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            attachment.add_header('Content-Disposition', 'attachment', filename=path.name)
            message.attach(attachment)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

    send_body = {'raw': raw}
    if thread_id:
        send_body['threadId'] = thread_id

    sent = service.users().messages().send(userId='me', body=send_body).execute()
    return f"Email sent successfully. Message ID: {sent['id']}"


@mcp.tool()
def search_emails(query: str, max_results: int = 20, account: str = "") -> str:
    """Search emails using Gmail's search syntax.

    Args:
        query: Gmail search query. Examples:
               - "from:someone@example.com"
               - "subject:invoice"
               - "is:unread"
               - "after:2024/01/01 before:2024/02/01"
               - "has:attachment"
        max_results: Maximum number of results (default 20)
        account: Account name from accounts.json. Uses default if not specified.
    """
    return list_emails(max_results=max_results, query=query, account=account)


if __name__ == "__main__":
    mcp.run()
