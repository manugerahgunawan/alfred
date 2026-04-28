# Agent Instructions

## Language
All code, comments, documentation, commit messages, and descriptions MUST be in English. No exceptions.

## Project
Alfred — multi-agent AI butler on Google ADK + Gemini. Cross-domain orchestration between work and home life.

## Package Manager
- **Frontend**: `npm install`, `npm run dev` (Vite + React)
- **Backend**: `pip install -r src/agent/alfred_agent/requirements.txt` (google-adk, FastAPI, Firestore)

## File-Scoped Commands
| Task | Command |
|------|---------|
| Frontend dev | `npm run dev` |
| Frontend build | `npm run build` |
| Typecheck | `npm run lint` |
| Backend start | `cd src/agent/alfred_agent && python agent.py` |

## Commit Attribution
AI commits MUST include:
```
Co-Authored-By: <agent-model> <noreply@anthropic.com>
```

## Key Conventions
- Agent hierarchy: `alfred_root` → `work_agent` / `home_agent` → `output_formatter`
- Auth: `SessionAwareCredentialService` resolves per-user OAuth tokens via `token_context` ContextVar
- MCP tools: `SessionAwareMcpToolset` injects Authorization headers from session context
- Firestore: session persistence via `FirestoreSessionService`; data keyed by user email for multi-tenant isolation
- Secrets: never hardcode — use `.env` (gitignored) or Secret Manager
- `token_context` / `refresh_token_context` ContextVars carry per-request auth; never share across users

## Critical Files
- `src/agent/alfred_agent/agent.py` — agent definitions, credential service, MCP toolset
- `src/agent/alfred_agent/web_login.py` — OAuth2 flow, session cookies, gatekeeper middleware
- `src/agent/alfred_agent/mcp_google_client.py` — MCP protocol client for Google Workspace
- `src/agent/firestore_session_service.py` — Firestore-backed ADK session service
- `src/agent/services.py` — service registry for ADK
