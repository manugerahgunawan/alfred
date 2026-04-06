# Using Google ADK Agent with the Workspace MCP Server

This guide shows how to wire your **Google ADK (Agent Development Kit)** agent so it can call Gmail, Calendar, and Contacts tools via the hosted MCP server — no manual HTTP needed.

**MCP Server URL:** `https://workspace-mcp-181562945855.asia-southeast2.run.app/mcp`

---

## How It Works

```
Your ADK Agent
    │
    ▼  (StreamableHTTPConnectionParams)
McpToolset  ─── Bearer Token ──►  Cloud Run MCP Server
                                        │
                                        ▼  (validates token with Google)
                                   Gmail / Calendar / Contacts APIs
```

The `McpToolset` acts as a bridge: it connects to the server, discovers all available tools, and hands them to your agent automatically. The server identifies **who** is calling based on the Bearer token — so each user gets their own data.

---

## Prerequisites

```bash
pip install google-adk
```

Also complete the [get_token.py flow](./README.md) first so you have a valid `GOOGLE_ACCESS_TOKEN` in your `.env`.

---

## Minimal Working Example

```python
# agent_with_mcp.py
import asyncio
import os
from contextlib import AsyncExitStack
from dotenv import load_dotenv

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types

load_dotenv()

MCP_URL = "https://workspace-mcp-181562945855.asia-southeast2.run.app/mcp"
ACCESS_TOKEN = os.getenv("GOOGLE_ACCESS_TOKEN")


async def main():
    if not ACCESS_TOKEN:
        raise ValueError("GOOGLE_ACCESS_TOKEN not set. Run get_token.py first.")

    async with AsyncExitStack() as stack:
        # 1. Connect McpToolset to the remote server
        toolset = McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=MCP_URL,
                headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            )
        )
        tools, _ = await stack.enter_async_context(toolset)

        # 2. Create the agent with those tools
        agent = Agent(
            model="gemini-2.0-flash",
            name="workspace_agent",
            instruction=(
                "You are a helpful assistant with access to the user's "
                "Gmail, Google Calendar, and Contacts. "
                "Use the available tools to answer questions accurately."
            ),
            tools=tools,
        )

        # 3. Run a test query
        session_service = InMemorySessionService()
        session = await session_service.create_session(
            app_name="workspace_agent",
            user_id="user_01",
        )
        runner = Runner(
            agent=agent,
            app_name="workspace_agent",
            session_service=session_service,
        )

        query = "What are my 3 most recent unread emails?"
        print(f"\nQuery: {query}\n")

        async for event in runner.run_async(
            user_id="user_01",
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text=query)],
            ),
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    print("Agent:", part.text)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Multi-User Pattern

Since the server is stateless, you just swap the token per user. In a real app, store each user's token and pass it into the toolset:

```python
async def build_agent_for_user(user_access_token: str):
    toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=MCP_URL,
            headers={"Authorization": f"Bearer {user_access_token}"},
        )
    )
    async with AsyncExitStack() as stack:
        tools, _ = await stack.enter_async_context(toolset)
        agent = Agent(
            model="gemini-2.0-flash",
            name="workspace_agent",
            instruction="You have access to Gmail, Calendar, and Contacts.",
            tools=tools,
        )
        return agent, stack
```

---

## Available Tools

Once connected, ADK will automatically discover these tools from the server:

| Tool Name | Description |
|-----------|-------------|
| `search_gmail_messages` | Search inbox with a Gmail query string |
| `get_gmail_message` | Get a specific message by ID |
| `send_gmail_message` | Draft and send an email |
| `get_events` | List calendar events |
| `create_event` | Create a new calendar event |
| `search_contacts` | Search Google Contacts |
| `get_contact` | Get a specific contact |

> The full list is auto-fetched at runtime — run `tools/list` via `mcp_google_client.py` to see the latest.

---

## Token Expiry

Google access tokens expire after **1 hour**. For long-running agents:
- Re-run `get_token.py` to refresh your token before starting the agent, OR
- Implement a token refresh loop using the `refresh_token` from the OAuth response

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` | Token expired or wrong scopes | Re-run `get_token.py` |
| `MCP initialization failed` | Wrong URL | Confirm URL ends with `/mcp` not `/` |
| `Tool not found` | Server tier doesn't include that tool | Check server deploy flags (`--tools contacts gmail calendar`) |
| `No module named google.adk` | ADK not installed | `pip install google-adk` |
