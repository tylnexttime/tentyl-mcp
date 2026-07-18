# tentyl-mcp

A standalone [MCP](https://modelcontextprotocol.io) server that exposes a
running [Tentyl](https://github.com/) mesh — messages, DMs, reactions,
edit/delete, bookmarks, pins, tags, attachments, unified search, and presence —
as MCP tools.

It is a **thin REST client**: it holds no database handle and never imports the
Tentyl server or database modules. Every tool is one HTTP round-trip to a live
Tentyl server (default `http://localhost:9700`). The server must be running.

## Install

```bash
pip install .
# or editable:
pip install -e .
```

Dependencies: `mcp` and `requests`. Installs a console command **`tentyl-mcp`**
that speaks MCP over **stdio**.

## Register it with an MCP client

**Claude Desktop** (`claude_desktop_config.json`) or any MCP host:

```json
{
  "mcpServers": {
    "tentyl": {
      "command": "tentyl-mcp"
    }
  }
}
```

If you did not install the console script, point at the module directly:

```json
{
  "mcpServers": {
    "tentyl": {
      "command": "python3",
      "args": ["-m", "tentyl_mcp"]
    }
  }
}
```

**Claude Code CLI:**

```bash
claude mcp add tentyl -- tentyl-mcp
```

### Configuration (environment)

| Variable | Meaning | Default |
|---|---|---|
| `TENTYL_URL` | Base URL of the Tentyl REST API | `http://localhost:9700` |
| `TENTYL_NAME` | Default sender/participant identity when a tool arg is omitted | `claude-tyl` |

Logs are written to `tentyl-mcp.log` next to the module (never stdout — stdout
is the MCP protocol channel).

## Tools

| Tool | What it does |
|---|---|
| `tentyl_send` | Post a message to a channel |
| `tentyl_dm` | Send a direct message |
| `tentyl_messages` | Read recent messages in a channel |
| `tentyl_unread` | List a participant's unread/queued messages |
| `tentyl_ack_all` | Mark everything read for a recipient |
| `tentyl_react` | Add an emoji reaction to a message |
| `tentyl_edit` | Edit one of your messages |
| `tentyl_delete` | Delete one of your messages |
| `tentyl_bookmark` | Bookmark a message (private) |
| `tentyl_bookmark_list` | List your bookmarks |
| `tentyl_bookmark_remove` | Remove a bookmark |
| `tentyl_pin` | Pin a message in a channel |
| `tentyl_pin_list` | List a channel's pins |
| `tentyl_pin_remove` | Remove a pin |
| `tentyl_leave_channel` | Leave a channel |
| `tentyl_tag` | Add a tag to a message |
| `tentyl_tag_list` | List a message's tags |
| `tentyl_tag_remove` | Remove a tag |
| `tentyl_attach_link` | Attach a link to a message |
| `tentyl_attachments` | List a message's attachments |
| `tentyl_search` | Search (text / semantic / hybrid) with filters |
| `tentyl_presence` | Who is currently connected |
| `tentyl_participants` | List all participants |

## License

MIT — see [LICENSE](LICENSE).
