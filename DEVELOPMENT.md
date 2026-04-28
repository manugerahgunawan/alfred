# Alfred — Developer Guide

## Local Development

### Prerequisites

- Node.js 20+
- A Google Cloud project with the Alfred backend already deployed on Cloud Run
- A Google OAuth 2.0 client ID (Web Application type)

### 1. Clone and install

```bash
git clone <repo>
cd alfred
npm install
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in the two required values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `VITE_GOOGLE_OAUTH_CLIENT_ID` | Your Google OAuth 2.0 client ID |
| `VITE_ALFRED_BASE_URL` | Alfred backend Cloud Run URL (default already set) |

The `.env` file is gitignored and **never committed**. Sensitive values (client secret, access tokens) must never go in `VITE_*` variables — those are baked into the browser bundle at build time and visible to anyone who views source.

### 3. Register the OAuth redirect URI

In [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials):

1. Open your OAuth 2.0 client
2. Under **Authorised JavaScript origins**, add `http://localhost:8080` (or whatever port Vite uses)
3. Under **Authorised redirect URIs**, add the **same origin** (the implicit flow returns the token to `window.location.origin`)
4. For Cloud Run, also add `https://alfred-frontend-181562945855.asia-southeast2.run.app`

### 4. Start the dev server

```bash
npm run dev
```

Vite starts on `http://localhost:5173` by default (or `8080` if `--port 8080` is configured). Open that URL in your browser.

The backend is the **already-deployed Cloud Run service** — no local backend needed.

---

## Authentication Flow

Alfred uses the **Google OAuth 2.0 implicit flow** (browser-only, no server round-trip):

```
Browser                        Google Auth              Alfred Backend
   │                                │                         │
   │  1. Click "Sign in"            │                         │
   │─────────────────────────────>  │                         │
   │  redirect to accounts.google.com/o/oauth2/v2/auth        │
   │  ?response_type=token          │                         │
   │  &scope=email calendar gmail   │                         │
   │                                │                         │
   │  2. User picks account         │                         │
   │  <─────────────────────────────│                         │
   │  redirect back to origin/#access_token=ya29...           │
   │                                │                         │
   │  3. parseOAuthFragment()       │                         │
   │  reads token from URL hash     │                         │
   │  hash cleared immediately      │                         │
   │                                │                         │
   │  4. fetchUserEmail(token)      │                         │
   │─────────────────────────────────────────────────────────>│
   │  GET googleapis.com/userinfo   │                         │
   │  <─────────────────────────────│                         │
   │  { email: "user@gmail.com" }   │                         │
   │                                │                         │
   │  5. createAlfredSession()      │                         │
   │──────────────────────────────────────────────────────>   │
   │  POST /apps/alfred_agent/users/{email}/sessions          │
   │  body: { state: { ALFRED_ACCESS_TOKEN, ALFRED_TIMEZONE } }│
   │  <──────────────────────────────────────────────────────  │
   │  { id: "session-uuid" }        │                         │
   │                                │                         │
   │  6. Session stored in React state                        │
   │  App transitions to main UI    │                         │
```

**Why the access token is passed to the backend:** Alfred's MCP tools (Calendar, Gmail, Contacts) need to act on behalf of the user. The token is stored in ADK session state so the agent can authenticate API calls without prompting the user again.

---

## Data Flow — Sending a Message

```
User types a message
        │
        ▼
sendToAlfred(userId, sessionId, message)
        │
        ▼
POST /apps/alfred_agent/users/{email}/sessions/{sessionId}/run
Body: { new_message: { role: "user", parts: [{ text: "..." }] } }
        │
        ▼
ADK Backend (Cloud Run — alfred-agent)
  └── Alfred Core agent (Gemini 2.5 Flash via Vertex AI)
        │  classifies intent
        ├── WorkAgent  → Calendar, Gmail, Tasks MCP tools
        ├── CareAgent  → Calendar, Maps MCP tools
        └── HomeAgent  → Calendar, Tasks MCP tools
        │
        ▼
Response: SSE stream or JSON array of ADKRunEvent
        │
        ▼
parseSSEFinalText() / extractFinalText()
  finds event where is_final_response=true
        │
        ▼
Displayed in chat UI
```

**Session persistence:** Sessions are stored in **Firestore** (not in-memory). Each user's session survives server restarts and Cloud Run scaling events. The session retains the user's Google access token and timezone for the duration of the session.

---

## Project Structure

```
alfred/
├── src/
│   ├── api/
│   │   └── alfred.ts          # All backend calls + Google OAuth helpers
│   ├── App.tsx                # UI + state management
│   └── main.tsx               # React entry point
├── src/agent/                 # Backend (Python ADK agent)
│   ├── alfred_agent/          # Agent definition + tools
│   ├── services.py            # Registers firestore:// session URI scheme
│   ├── firestore_session_service.py
│   ├── run.py                 # Uvicorn startup with proxy_headers=True
│   └── Dockerfile
├── Dockerfile                 # Frontend (nginx static build)
├── cloudbuild.yaml            # Frontend Cloud Build config
├── vite.config.ts
└── .env                       # Local only — never committed
```

---

## Cloud Deployment

### Frontend

Built as a static site and served via nginx on Cloud Run.

```bash
gcloud builds submit \
  --config cloudbuild.yaml \
  --substitutions \
    "_VITE_ALFRED_BASE_URL=https://alfred-agent-gloaqqynxq-et.a.run.app,\
     _VITE_GOOGLE_OAUTH_CLIENT_ID=<your-client-id>" \
  --project=alfred-492407

gcloud run deploy alfred-frontend \
  --image=asia-southeast2-docker.pkg.dev/alfred-492407/cloud-run-source-deploy/alfred-frontend:latest \
  --region=asia-southeast2 \
  --project=alfred-492407
```

`VITE_*` variables are baked into the JavaScript bundle at **build time** via Docker build args. They cannot be changed at runtime — a new build is required to change them.

### Backend (ADK Agent)

```bash
cd src/agent
gcloud builds submit \
  --tag=asia-southeast2-docker.pkg.dev/alfred-492407/cloud-run-source-deploy/alfred-agent:latest \
  --project=alfred-492407 .

gcloud run deploy alfred-agent \
  --image=asia-southeast2-docker.pkg.dev/alfred-492407/cloud-run-source-deploy/alfred-agent:latest \
  --region=asia-southeast2 \
  --project=alfred-492407
```

The backend starts via `run.py` (not `adk web` directly) so that Uvicorn runs with `proxy_headers=True, forwarded_allow_ips="*"`. This is required because Cloud Run terminates TLS at its load balancer and forwards requests as HTTP internally — without proxy headers, any redirect the ADK framework generates would use `http://` instead of `https://`, causing Mixed Content errors in the browser.

---

## Related Documentation

### Backend — ADK Agent

| Document | Location | What it covers |
|---|---|---|
| Agent README | [`src/agent/alfred_agent/README.md`](src/agent/alfred_agent/README.md) | Full onboarding guide — software setup, Python venv, `.env` keys, running `adk web`, adding sub-agents and tools |
| Local Setup (Windows) | [`src/agent/alfred_agent/LOCAL_SETUP.md`](src/agent/alfred_agent/LOCAL_SETUP.md) | Step-by-step PowerShell guide for setting up Python, `gcloud` ADC, venv, running the agent locally and deploying to Cloud Run |
| Agent Architecture | [`src/agent/alfred_agent/architecture.md`](src/agent/alfred_agent/architecture.md) | Mermaid diagram of the agent hierarchy (`alfred_root` → `work_agent` / `home_agent` → `output_formatter`), Firestore data model, security and IAM design |

**Agent hierarchy at a glance:**

```
alfred_root  (Orchestrator — conflict detection, intent routing)
├── work_flow → work_agent   (Google Workspace: meetings, emails, tasks)
│                └── output_formatter
└── home_flow → home_agent   (Domestic: household coordination, audit log)
                  └── home_output_formatter
```

Each agent calls Google Workspace tools via the MCP server using the user's Google access token stored in ADK session state.

---

### MCP Layer — Google Workspace Tools

| Document | Location | What it covers |
|---|---|---|
| MCP Runner README | [`src/mcpRunner/README.md`](src/mcpRunner/README.md) | How to connect to the hosted MCP server, run `get_token.py` to obtain a Bearer token, and verify with `test_mcp_multiuser.py` |
| ADK Agent Guide | [`src/mcpRunner/adk_agent_guide.md`](src/mcpRunner/adk_agent_guide.md) | Code example wiring `McpToolset` into an ADK agent, multi-user token pattern, full list of available tools (Gmail, Calendar, Contacts), token expiry handling |
| MCP Server Deployment | [`src/mcpRunner/documentation.md`](src/mcpRunner/documentation.md) | How the MCP server itself is built and deployed to Cloud Run (reference only — server is already live) |

**MCP server:** `https://workspace-mcp-181562945855.asia-southeast2.run.app/mcp`

The MCP server is stateless — each request carries a Bearer token (the user's Google OAuth access token). The server validates it with Google's identity endpoint so each user gets their own Gmail/Calendar/Contacts data. No shared session state.

Available tools auto-discovered at runtime: `search_gmail_messages`, `get_gmail_message`, `send_gmail_message`, `get_events`, `create_event`, `manage_event`, `search_contacts`, `get_contact`.

---

### Concept & Product

| Document | Location | What it covers |
|---|---|---|
| Product README | [`README.md`](README.md) | Full concept doc — problem statement, solution design, agent workflow, wireframes, architecture diagram, tech stack rationale |
| Concept | [`concept.md`](concept.md) | Original concept notes |

---

## Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `VITE_GOOGLE_OAUTH_CLIENT_ID is not set` | `.env` missing or wrong key name | Check `.env` has `VITE_GOOGLE_OAUTH_CLIENT_ID=` |
| `redirect_uri_mismatch` from Google | Origin not registered in OAuth client | Add `http://localhost:<port>` to Authorised JavaScript origins in GCP Console |
| Mixed Content error on Cloud Run | Backend generating `http://` redirect URLs | Backend must run via `run.py` with `proxy_headers=True` |
| CORS error locally | Backend not allowing `http://localhost:*` | Backend uses `--allow_origins=*` by default; check `CORS_ALLOW_ORIGINS` env var on Cloud Run |
| `Session created but no ID returned` | ADK session endpoint returned unexpected shape | Check ADK version; response uses `id` or `session_id` field |
