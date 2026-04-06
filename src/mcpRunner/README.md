# Google Workspace MCP Runner

Connect to the hosted Google Workspace MCP server and call Gmail, Calendar, and Contacts tools via Python.

**Hosted MCP Server:** `https://workspace-mcp-181562945855.asia-southeast2.run.app/`

> [!IMPORTANT]
> **Team Note:** The MCP service is already deployed and running. You **do not** need to build or deploy anything. Your focus is strictly on integrating your agents using the [ADK Agent Guide](./adk_agent_guide.md).

---

## Prerequisites

- Python 3.10+
- A Google account that has been granted access to the GCP OAuth app

---

## Setup

### 1. Install dependencies

From this directory (`src/mcpRunner/`):

```bash
pip install -r requirements.txt
```

### 2. Configure your `.env`

Copy the root-level `.env.example` to `.env` (at the project root):

```bash
# From the project root
cp .env.example .env
```

Then fill in your Google OAuth credentials in `.env`:

```env
GOOGLE_OAUTH_CLIENT_ID="your-client-id.apps.googleusercontent.com"
GOOGLE_OAUTH_CLIENT_SECRET="your-client-secret"
```

> Ask the project owner for the `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` values.
> Also make sure `http://localhost:8080` is added as an **Authorized Redirect URI** in the GCP Console for this OAuth client.

### 3. Get your access token

Run the token helper from this directory:

```bash
python get_token.py
```

This will:

1. Open a browser tab → authorize with your Google account
2. Exchange the code for an access token
3. **Automatically write** `GOOGLE_ACCESS_TOKEN=...` into your root `.env`

### 4. Run the multi-user test

```bash
python test_mcp_multiuser.py
```

Expected output:
```
--- Initializing MCP Client ---
Step 1: Listing Tools (Verifying Auth)...
Success! Found N tools.
Step 2: Testing Gmail...
Step 3: Testing Contacts...
Step 4: Testing Calendar...
```

---

## File Reference

| File | Purpose |
| :--- | :--- |
| `get_token.py` | OAuth flow — opens browser, saves token to `.env` |
| `mcp_google_client.py` | Reusable async MCP client class |
| `test_mcp_multiuser.py` | End-to-end test: lists tools + calls Gmail/Contacts/Calendar |
| `requirements.txt` | Python dependencies (`httpx`, `python-dotenv`) |
| `adk_agent_guide.md` | Guide for Google ADK Agent integration |

---

## How It Works

The server uses **stateless OAuth** — each request includes a Bearer token (your Google access token). The server validates it against Google's identity endpoint to identify who is making the call. This means:

- ✅ **Multi-user by design** — each teammate uses their own token
- ✅ No shared session or server-side login state
- ✅ Data returned is scoped to the authenticated user's Google account
