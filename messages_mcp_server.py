#!/usr/bin/env python3
"""Apple Messages MCP Server - Read and send iMessages/SMS via macOS."""

import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

MESSAGES_DB = Path.home() / "Library/Messages/chat.db"

mcp = FastMCP("messages")


def get_messages_db():
    """Get connection to Messages database."""
    return sqlite3.connect(str(MESSAGES_DB))


@mcp.tool()
def list_conversations(limit: int = 20) -> str:
    """List recent conversations.

    Args:
        limit: Maximum number of conversations to return (default 20)
    """
    conn = get_messages_db()
    cursor = conn.cursor()

    query = """
    SELECT
        chat.chat_identifier,
        chat.display_name,
        MAX(message.date) as last_message_date,
        (SELECT text FROM message m2
         WHERE m2.ROWID = (
             SELECT MAX(m3.ROWID) FROM message m3
             JOIN chat_message_join cmj2 ON m3.ROWID = cmj2.message_id
             WHERE cmj2.chat_id = chat.ROWID
         )) as last_message
    FROM chat
    JOIN chat_message_join ON chat.ROWID = chat_message_join.chat_id
    JOIN message ON chat_message_join.message_id = message.ROWID
    GROUP BY chat.ROWID
    ORDER BY last_message_date DESC
    LIMIT ?
    """

    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "No conversations found."

    output = []
    for row in rows:
        chat_id, display_name, last_date, last_msg = row
        name = display_name or chat_id
        preview = (last_msg[:80] + "...") if last_msg and len(last_msg) > 80 else (last_msg or "")
        output.append(
            f"Chat: {name}\n"
            f"ID: {chat_id}\n"
            f"Last message: {preview}\n"
        )

    return "\n---\n".join(output)


@mcp.tool()
def read_conversation(chat_identifier: str, limit: int = 30) -> str:
    """Read messages from a specific conversation.

    Args:
        chat_identifier: The phone number or email of the conversation (e.g., "+15551234567")
        limit: Maximum number of messages to return (default 30)
    """
    conn = get_messages_db()
    cursor = conn.cursor()

    query = """
    SELECT
        message.text,
        message.is_from_me,
        message.date,
        handle.id as sender
    FROM message
    JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
    JOIN chat ON chat_message_join.chat_id = chat.ROWID
    LEFT JOIN handle ON message.handle_id = handle.ROWID
    WHERE chat.chat_identifier = ?
    ORDER BY message.date DESC
    LIMIT ?
    """

    cursor.execute(query, (chat_identifier, limit))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return f"No messages found for {chat_identifier}."

    output = []
    for text, is_from_me, date, sender in reversed(rows):
        if not text:
            continue
        who = "Me" if is_from_me else (sender or "Them")
        # Convert Apple's timestamp (nanoseconds since 2001-01-01)
        if date:
            ts = datetime(2001, 1, 1) + __import__('datetime').timedelta(seconds=date / 1e9)
            time_str = ts.strftime("%Y-%m-%d %H:%M")
        else:
            time_str = "Unknown time"
        output.append(f"[{time_str}] {who}: {text}")

    return "\n".join(output)


@mcp.tool()
def send_message(to: str, message: str) -> str:
    """Send an iMessage or SMS.

    Args:
        to: Phone number or email address of recipient
        message: The message text to send
    """
    script = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{to}" of targetService
        send "{message.replace('"', '\\"')}" to targetBuddy
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return f"Failed to send message: {result.stderr}"

    return f"Message sent to {to}"


@mcp.tool()
def search_messages(query: str, limit: int = 30) -> str:
    """Search messages by text content.

    Args:
        query: Text to search for in messages
        limit: Maximum number of results (default 30)
    """
    conn = get_messages_db()
    cursor = conn.cursor()

    search_query = """
    SELECT
        message.text,
        message.is_from_me,
        message.date,
        chat.chat_identifier,
        chat.display_name
    FROM message
    JOIN chat_message_join ON message.ROWID = chat_message_join.message_id
    JOIN chat ON chat_message_join.chat_id = chat.ROWID
    WHERE message.text LIKE ?
    ORDER BY message.date DESC
    LIMIT ?
    """

    cursor.execute(search_query, (f"%{query}%", limit))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return f"No messages matching '{query}' found."

    output = []
    for text, is_from_me, date, chat_id, display_name in rows:
        who = "Me" if is_from_me else "Them"
        chat_name = display_name or chat_id
        if date:
            ts = datetime(2001, 1, 1) + __import__('datetime').timedelta(seconds=date / 1e9)
            time_str = ts.strftime("%Y-%m-%d %H:%M")
        else:
            time_str = "Unknown"
        output.append(
            f"[{time_str}] {chat_name}\n"
            f"{who}: {text}\n"
        )

    return "\n---\n".join(output)


if __name__ == "__main__":
    mcp.run()
