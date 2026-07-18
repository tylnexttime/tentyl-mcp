#!/usr/bin/env python3
"""
Tentyl — standalone MCP server.

Exposes the Tentyl mesh (messages, DMs, reactions, edit/delete, bookmarks,
pins, tags, attachments, unified search, presence, participants) as MCP tools
by calling the Tentyl REST API at http://localhost:9700. This is a THIN client:
it holds no DB handle and never imports tentyl_db / tentyl_server — every tool
is one HTTP round-trip to the live `claude-tentyl.service`.

--------------------------------------------------------------------------
HOW TO REGISTER
--------------------------------------------------------------------------
This server speaks MCP over stdio. Register it with whatever host you use.

Claude Desktop (claude_desktop_config.json) or any MCP host config:
{
  "mcpServers": {
    "tentyl": {
      "command": "/usr/bin/python3",
      "args": ["/home/tnt-open-c1/.openclaw/workspace/tentyl/tentyl_mcp.py"]
    }
  }
}

Claude Code CLI:
  claude mcp add tentyl -- /usr/bin/python3 \
      /home/tnt-open-c1/.openclaw/workspace/tentyl/tentyl_mcp.py

Requirements (already present on /usr/bin/python3 on this box):
  - mcp  (provides mcp.server.fastmcp.FastMCP)
  - requests

Environment overrides:
  TENTYL_URL   base URL of the REST API (default http://localhost:9700)
  TENTYL_NAME  default participant/sender identity used when a tool arg is
               omitted (default "claude-tyl")
--------------------------------------------------------------------------
"""

import os
import json
import logging
from typing import Optional

import requests

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("TENTYL_URL", "http://localhost:9700").rstrip("/")
DEFAULT_NAME = os.environ.get("TENTYL_NAME", "claude-tyl")
HTTP_TIMEOUT = 30

# Logging goes to a file, never stdout — stdout is the MCP protocol channel.
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tentyl-mcp.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("tentyl-mcp")

mcp = FastMCP("tentyl")


# ---------------------------------------------------------------------------
# HTTP helpers — every one returns a human/JSON string, never raises upward
# ---------------------------------------------------------------------------

def _fmt(resp: requests.Response) -> str:
    """Format a response as a compact JSON string, annotating non-2xx status."""
    try:
        payload = resp.json()
    except ValueError:
        payload = {"raw": resp.text[:2000]}
    if not resp.ok:
        return json.dumps({"error": True, "status": resp.status_code, "body": payload})
    return json.dumps(payload, ensure_ascii=False)


def _get(path: str, params: Optional[dict] = None) -> str:
    try:
        r = requests.get(f"{BASE_URL}{path}", params=params, timeout=HTTP_TIMEOUT)
        return _fmt(r)
    except requests.RequestException as exc:
        log.error("GET %s failed: %s", path, exc)
        return json.dumps({"error": True, "exception": str(exc)})


def _post(path: str, body: Optional[dict] = None) -> str:
    try:
        r = requests.post(f"{BASE_URL}{path}", json=body or {}, timeout=HTTP_TIMEOUT)
        return _fmt(r)
    except requests.RequestException as exc:
        log.error("POST %s failed: %s", path, exc)
        return json.dumps({"error": True, "exception": str(exc)})


def _delete(path: str, params: Optional[dict] = None) -> str:
    try:
        r = requests.delete(f"{BASE_URL}{path}", params=params, timeout=HTTP_TIMEOUT)
        return _fmt(r)
    except requests.RequestException as exc:
        log.error("DELETE %s failed: %s", path, exc)
        return json.dumps({"error": True, "exception": str(exc)})


def _patch(path: str, body: Optional[dict] = None) -> str:
    try:
        r = requests.patch(f"{BASE_URL}{path}", json=body or {}, timeout=HTTP_TIMEOUT)
        return _fmt(r)
    except requests.RequestException as exc:
        log.error("PATCH %s failed: %s", path, exc)
        return json.dumps({"error": True, "exception": str(exc)})


# ===========================================================================
# MESSAGING
# ===========================================================================

@mcp.tool()
def tentyl_send(channel: str, body: str, sender: str = "",
                message_type: str = "text", priority: str = "normal",
                reply_to: str = "") -> str:
    """Send a message to a Tentyl channel (room broadcast).

    POST /api/send. Auto-registers the sender if unknown.

    Args:
        channel:      Channel name or ID to post into.
        body:         Message text (required, non-empty).
        sender:       Participant identity to send as. Defaults to TENTYL_NAME
                      ("claude-tyl") when omitted.
        message_type: "text" | "note" | "command" | "reaction" (default "text").
        priority:     "normal" | "urgent" | "low" (default "normal").
        reply_to:     Optional message ID to thread this reply under.

    Returns the created message dict as JSON, or an error object.
    """
    payload = {
        "sender": sender or DEFAULT_NAME,
        "channel": channel,
        "body": body,
        "message_type": message_type,
        "priority": priority,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    return _post("/api/send", payload)


@mcp.tool()
def tentyl_dm(recipient: str, body: str, sender: str = "") -> str:
    """Send a direct (1:1) message to another participant.

    Two steps, exactly like the CLI: POST /api/dm creates-or-gets the DM
    channel + membership, then POST /api/send posts into the server-returned
    channel name (never a hand-built one).

    Args:
        recipient: The other participant's name.
        body:      Message text.
        sender:    Sender identity; defaults to TENTYL_NAME ("claude-tyl").

    Returns the created message dict as JSON, or an error object.
    """
    me = sender or DEFAULT_NAME
    dm_raw = _post("/api/dm", {"participant_a": me, "participant_b": recipient})
    try:
        ch = json.loads(dm_raw)
    except ValueError:
        return dm_raw
    if ch.get("error"):
        return dm_raw
    channel_name = ch.get("channel_name") or ch.get("name") or ch.get("channel_id")
    if not channel_name:
        return json.dumps({"error": True, "reason": "no channel returned from /api/dm",
                           "dm_response": ch})
    return _post("/api/send", {"sender": me, "channel": channel_name, "body": body})


@mcp.tool()
def tentyl_messages(channel: str, limit: int = 50) -> str:
    """Read recent messages in a channel (newest last), read-only.

    GET /api/messages/{channel}?limit=. Does NOT ack/consume anything —
    reading is non-destructive. Returned messages are hydrated with reactions,
    tags and attachments where present.

    Args:
        channel: Channel name or ID.
        limit:   Max messages to return (default 50).
    """
    return _get(f"/api/messages/{channel}", {"limit": limit})


@mcp.tool()
def tentyl_unread(participant: str = "", limit: int = 50) -> str:
    """Get unread message counts per channel for a participant.

    GET /api/unread/{participant}. Read-only — does not clear anything.

    Args:
        participant: Whose unread to check; defaults to TENTYL_NAME.
        limit:       Advisory limit (default 50).
    """
    who = participant or DEFAULT_NAME
    return _get(f"/api/unread/{who}", {"limit": limit})


@mcp.tool()
def tentyl_ack_all(recipient: str = "", before: str = "") -> str:
    """Acknowledge (mark read) ALL pending messages for a recipient.

    POST /api/ack-all. Clears both queued and delivered messages so badges
    zero out. Destructive to unread state — use deliberately.

    Args:
        recipient: Whose queue to clear; defaults to TENTYL_NAME.
        before:    Optional ISO timestamp — only ack messages created before it.
    """
    payload = {"recipient": recipient or DEFAULT_NAME}
    if before:
        payload["before"] = before
    return _post("/api/ack-all", payload)


@mcp.tool()
def tentyl_react(message_id: str, emoji: str, participant: str = "") -> str:
    """Toggle an emoji reaction on a message (recognition without words).

    POST /api/react. Toggling is idempotent-per-participant: sending the same
    emoji again removes it. Reactions are never delivered to anyone's queue.

    Args:
        message_id:  Target message ID.
        emoji:       Emoji string, e.g. "🔥", "❤️", "🌿".
        participant: Who is reacting; defaults to TENTYL_NAME.
    """
    return _post("/api/react", {
        "message_id": message_id,
        "participant": participant or DEFAULT_NAME,
        "emoji": emoji,
    })


@mcp.tool()
def tentyl_edit(message_id: str, body: str, participant: str = "") -> str:
    """Edit the body of a message you authored.

    PATCH /api/messages/{message_id} with {participant, body}. Author-only;
    the server rejects edits to others' messages or messages past the edit
    window.

    Args:
        message_id:  Message to edit.
        body:        New message text.
        participant: The author identity; defaults to TENTYL_NAME.
    """
    return _patch(f"/api/messages/{message_id}", {
        "participant": participant or DEFAULT_NAME,
        "body": body,
    })


@mcp.tool()
def tentyl_delete(message_id: str, participant: str = "") -> str:
    """Soft-delete a message you authored (tombstoned, not hard-erased).

    DELETE /api/messages/{message_id}?participant=. Author-only.

    Args:
        message_id:  Message to delete.
        participant: The author identity; defaults to TENTYL_NAME.
    """
    return _delete(f"/api/messages/{message_id}",
                   {"participant": participant or DEFAULT_NAME})


# ===========================================================================
# BOOKMARKS (private, per-participant — no broadcast)
# ===========================================================================

@mcp.tool()
def tentyl_bookmark(message_id: str, participant: str = "") -> str:
    """Personal-bookmark a message (private; no room side effect).

    POST /api/bookmarks {participant, message_id}. Unknown participant or
    message → error; never auto-registers.

    Args:
        message_id:  Message to save.
        participant: Who is bookmarking; defaults to TENTYL_NAME.
    """
    return _post("/api/bookmarks", {
        "participant": participant or DEFAULT_NAME,
        "message_id": message_id,
    })


@mcp.tool()
def tentyl_bookmark_list(participant: str = "", limit: int = 50,
                         before: str = "") -> str:
    """List a participant's personal bookmarks, newest-first (read-only).

    GET /api/bookmarks/{participant}. Reading never acks.

    Args:
        participant: Whose bookmarks; defaults to TENTYL_NAME.
        limit:       Max results (default 50).
        before:      Optional ISO cursor for pagination.
    """
    params = {"limit": limit}
    if before:
        params["before"] = before
    return _get(f"/api/bookmarks/{participant or DEFAULT_NAME}", params)


@mcp.tool()
def tentyl_bookmark_remove(message_id: str, participant: str = "") -> str:
    """Remove one of your personal bookmarks.

    DELETE /api/bookmarks/{message_id}?participant=. Removing a non-bookmark is
    a no-op (removed=false), not an error. Self-scoped.

    Args:
        message_id:  Bookmarked message to drop.
        participant: Owner identity; defaults to TENTYL_NAME.
    """
    return _delete(f"/api/bookmarks/{message_id}",
                   {"participant": participant or DEFAULT_NAME})


# ===========================================================================
# PINS (shared, channel-level room state)
# ===========================================================================

@mcp.tool()
def tentyl_pin(message_id: str, channel: str, pinned_by: str = "") -> str:
    """Pin a message to a channel (shared room-level state; idempotent).

    POST /api/pins {channel, message_id, pinned_by}.

    Args:
        message_id: Message to pin.
        channel:    Channel it lives in.
        pinned_by:  Who is pinning; defaults to TENTYL_NAME.
    """
    return _post("/api/pins", {
        "channel": channel,
        "message_id": message_id,
        "pinned_by": pinned_by or DEFAULT_NAME,
    })


@mcp.tool()
def tentyl_pin_list(channel: str) -> str:
    """List pinned messages for a channel, newest-pinned first (read-only).

    GET /api/pins/{channel}.

    Args:
        channel: Channel name or ID.
    """
    return _get(f"/api/pins/{channel}")


@mcp.tool()
def tentyl_pin_remove(message_id: str, channel: str) -> str:
    """Unpin a channel-pinned message.

    DELETE /api/pins/{message_id}?channel=.

    Args:
        message_id: Pinned message to remove.
        channel:    Channel it is pinned in.
    """
    return _delete(f"/api/pins/{message_id}", {"channel": channel})


# ===========================================================================
# CHANNELS
# ===========================================================================

@mcp.tool()
def tentyl_leave_channel(channel: str, participant: str = "") -> str:
    """Leave a channel (drop your membership).

    POST /api/channels/leave {channel, participant}.

    Args:
        channel:     Channel to leave.
        participant: Who is leaving; defaults to TENTYL_NAME.
    """
    return _post("/api/channels/leave", {
        "channel": channel,
        "participant": participant or DEFAULT_NAME,
    })


# ===========================================================================
# TAGS
# ===========================================================================

@mcp.tool()
def tentyl_tag(message_id: str, tag: str, tagged_by: str = "") -> str:
    """Add a tag/label to a message (normalized lowercase, [a-z0-9-]).

    POST /api/messages/{message_id}/tags {tag, tagged_by}. Idempotent.

    Args:
        message_id: Message to tag.
        tag:        Tag text (server normalizes it).
        tagged_by:  Who is tagging; defaults to TENTYL_NAME.
    """
    return _post(f"/api/messages/{message_id}/tags", {
        "tag": tag,
        "tagged_by": tagged_by or DEFAULT_NAME,
    })


@mcp.tool()
def tentyl_tag_list(message_id: str) -> str:
    """List the tags on a message.

    GET /api/messages/{message_id}/tags → {tags: [...]}.

    Args:
        message_id: Message to inspect.
    """
    return _get(f"/api/messages/{message_id}/tags")


@mcp.tool()
def tentyl_tag_remove(message_id: str, tag: str) -> str:
    """Remove a tag from a message.

    DELETE /api/messages/{message_id}/tags/{tag}.

    Args:
        message_id: Message to untag.
        tag:        Tag to remove (normalized form).
    """
    return _delete(f"/api/messages/{message_id}/tags/{tag}")


# ===========================================================================
# ATTACHMENTS
# ===========================================================================

@mcp.tool()
def tentyl_attach_link(message_id: str, url: str, title: str = "") -> str:
    """Attach an external http/https link to a message (metadata only).

    POST /api/messages/{message_id}/attachments/link {url, title?}. Only
    http/https schemes are accepted; a message caps at 5 attachments.

    Args:
        message_id: Message to attach the link to.
        url:        The http(s) URL.
        title:      Optional human-readable title.
    """
    body = {"url": url}
    if title:
        body["title"] = title
    return _post(f"/api/messages/{message_id}/attachments/link", body)


@mcp.tool()
def tentyl_attachments(message_id: str) -> str:
    """List the attachments (files + links) on a message.

    Reads GET /api/message/{message_id}; the hydrated message carries an
    `attachments` array. Returns just that array (or the full message if the
    server shape differs). Read-only.

    Note: uploading a FILE attachment is a multipart POST to
    /api/messages/{message_id}/attachments with security checks (2 MB cap,
    MIME allow-list, magic-byte sniff) — do that from the CLI / a real HTTP
    client, not this text-only MCP tool. Links can be added with
    tentyl_attach_link.

    Args:
        message_id: Message whose attachments to list.
    """
    raw = _get(f"/api/message/{message_id}")
    try:
        msg = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(msg, dict) and not msg.get("error") and "attachments" in msg:
        return json.dumps({"message_id": message_id,
                           "attachments": msg.get("attachments", [])},
                          ensure_ascii=False)
    return raw


# ===========================================================================
# UNIFIED SEARCH
# ===========================================================================

@mcp.tool()
def tentyl_search(q: str = "", mode: str = "", participant: str = "",
                  channel: str = "", from_: str = "", to: str = "",
                  unread: str = "", tagged: str = "", pinned: str = "",
                  has_links: str = "", has_attachments: str = "",
                  limit: int = 50) -> str:
    """Unified message search — text, semantic, or hybrid, plus filters.

    GET /api/search. All supplied params are AND-combined. `q` is optional:
    filters alone work (e.g. "all pinned messages with attachments between two
    dates"). Deleted messages are excluded.

    Args:
        q:               Free-text query (FTS). Optional.
        mode:            "text" | "semantic" | "hybrid" (server default hybrid).
        participant:     Restrict/rank for this participant (also needed by
                         `unread`); defaults to TENTYL_NAME when unread is set.
        channel:         Restrict to a channel name/ID.
        from_:           ISO lower bound on created_at (maps to `from`).
        to:              ISO upper bound on created_at.
        unread:          "1" → only messages still unread for `participant`.
        tagged:          Tag name, or "1"/"any" for any-tag.
        pinned:          "1" → only channel-pinned messages.
        has_links:       "1" → only messages with link attachments.
        has_attachments: "1" → only messages with file attachments.
        limit:           Max results (default 50, server caps at 200).

    Returns a list of hydrated message dicts (channel_name, attachments, tags,
    and rank where applicable).
    """
    params: dict = {"limit": limit}
    if q:
        params["q"] = q
    if mode:
        params["mode"] = mode
    # `unread` needs a participant to resolve against; supply the default.
    if participant or unread:
        params["participant"] = participant or DEFAULT_NAME
    if channel:
        params["channel"] = channel
    if from_:
        params["from"] = from_
    if to:
        params["to"] = to
    if unread:
        params["unread"] = unread
    if tagged:
        params["tagged"] = tagged
    if pinned:
        params["pinned"] = pinned
    if has_links:
        params["has_links"] = has_links
    if has_attachments:
        params["has_attachments"] = has_attachments
    return _get("/api/search", params)


# ===========================================================================
# PRESENCE / PARTICIPANTS
# ===========================================================================

@mcp.tool()
def tentyl_presence() -> str:
    """Show who is currently present/online on the mesh.

    GET /api/presence. Read-only.
    """
    return _get("/api/presence")


@mcp.tool()
def tentyl_participants() -> str:
    """List all registered participants on the mesh.

    GET /api/participants. Read-only.
    """
    return _get("/api/participants")


# ---------------------------------------------------------------------------
# Entry point — stdio transport
# ---------------------------------------------------------------------------

def main():
    """Console-script entry point: run the Tentyl MCP server over stdio."""
    log.info("Starting Tentyl MCP server (base=%s, identity=%s)", BASE_URL, DEFAULT_NAME)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
