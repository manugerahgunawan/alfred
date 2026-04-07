# Alfred — Hackathon Submission

> *"Be present at work. Be present at home. Alfred handles the rest."*

---

## 1. Problem Statement

Working adults in Southeast and South Asia live in a permanent state of context-switching between two domains that no existing tool bridges:

- **Professional life** — meetings, clients, deadlines, board presentations, "special projects" that cannot be missed.
- **Family life** — ageing parents, school runs, medical appointments, domestic helpers, birthdays, the small thousand things that hold a household together.

The boundary between "work" and "home" does not exist cleanly in this region. A supplier call collides with a parent's physiotherapy. A board meeting lands on top of a school concert. A midnight deadline overlaps with a child's fever. The cognitive tax of manually reconciling these conflicts — flipping between five calendars, three chat apps, and a mental list — falls entirely on the individual.

The result is a daily, invisible toll:

- **Decision fatigue** — every reschedule is a new negotiation with yourself.
- **Dropped balls** — the things that get forgotten are almost always the family ones, because work has deadlines and family has guilt.
- **No single source of truth** — your spouse, helper, parents, and assistant all hold different fragments of your life.
- **No tool understands both sides** — productivity apps optimise work; caregiver apps optimise family; nothing optimises *the collision between them*.

This is the problem Alfred is built to solve: **the cross-domain coordination problem of the sandwich generation**.

---

## 2. Brief About the Idea

**Alfred** is a multi-agent AI butler — named after Batman's Alfred Pennyworth — that holds the full picture of a user's professional and household life simultaneously and acts on it.

Alfred is **not a chatbot**. It is a persistent, multi-agent coordination system built on Google's Agent Development Kit (ADK) that:

- **Classifies** user intents across Work and Home domains in natural language.
- **Delegates** to specialised sub-agents (WorkAgent, HomeAgent, ResponseFormatter), each with its own scope, instructions, and tool access.
- **Executes** real actions through Google Workspace via an MCP (Model Context Protocol) server — Calendar, Gmail, Contacts.
- **Detects** cross-domain scheduling conflicts before they become crises.
- **Resolves** them by proposing changes, getting confirmation, executing across services, and **emailing the affected contacts automatically**.
- **Remembers** everything in Firestore: a persistent household graph and an append-only audit trail of every action taken.
- **Speaks** with the voice and discretion of a butler — dry, witty, impeccable — so the user gets one trusted interface instead of ten chaotic apps.

The target user is the **sandwich-generation professional**: simultaneously an employee, a parent, and a child to ageing parents — who today reschedules life manually, five tabs at a time, and pays for it in stress and sleep.

The metaphor matters. Bruce Wayne can be Batman *because* Alfred handles Wayne Manor. Our users have their own Gotham — a board to answer to, a family to protect, projects that cannot fail. Alfred is the system that lets them be present at both.

---

## 3. Explain the Solution

### 3a. How we approached the problem using ADK + MCP

We mapped the hackathon's multi-agent requirement directly onto Google ADK's primitives, and we made the deliberate choice to use **MCP for all tool access** so that the agent code stays focused on reasoning while the integration surface stays reusable and swappable.

| Hackathon requirement | How Alfred implements it |
|---|---|
| Multi-agent orchestration | ADK `Agent` + `SequentialAgent`. `alfred_root` (the orchestrator) routes into `alfred_core_workflow`, a sequential pipeline of `work_agent` → `home_agent` → `response_formatter`. Each sub-agent has its own model, instructions, tools, and `output_key` so downstream agents can read upstream context. |
| Tool access across systems | A single `McpToolset` connected via `StreamableHTTPConnectionParams` to a remote Workspace MCP server (`workspace-mcp-…run.app/mcp`) hosted on Cloud Run. **Per-user OAuth tokens** are injected at request time via a `ContextVar` (`token_context`), so a single deployed agent serves many users without cross-tenant leakage. |
| Real Google Workspace actions | MCP exposes: `add_event`, `manage_event` (create/update/delete), `list_events`, `send_gmail_message`, `search_contacts`, `add_contact`, `get_contact`. Vertex-incompatible tools (e.g. `modify_gmail_message_labels`) are filtered out via a `tool_filter` lambda. |
| Persistent memory | Cloud Firestore, **keyed per user** via `get_user_email()` (looked up against `oauth2/v3/userinfo` and cached). Each household document is namespaced by the authenticated email; `agentActions` is an append-only ledger of every action with `agent`, `intent`, `action`, and `timestamp`. |
| Multi-tenant auth | Full Google OAuth2 + OpenID Connect flow handled by a **FastAPI login wrapper (`web_login.py`)** that acts as a gatekeeper in front of the ADK Web UI. Issues, refreshes, and isolates per-user access tokens via `SESSION_TOKEN_STORE` and `ContextVar`s. Scopes: `calendar`, `gmail.modify`, `gmail.send`, `contacts`, `openid/email/profile`. |
| Cold-start friendly | Firestore and Cloud Logging clients are **lazy-initialised** (`get_db()`, `setup_cloud_logging()`) so module import never blocks Cloud Run health checks. |
| Observability | `google.cloud.logging.Client().setup_logging()` is called at startup, so every `logging.info/warning/error` from the agents auto-streams to Cloud Logging. |
| Hackathon-grade deployability | Vertex AI for the model (Gemini 2.5 Flash), Cloud Run for the MCP server, Firestore for state, ADC for auth, ADK Web UI for local dev — runnable end-to-end with `adk web .` |

The cultural insight driving the design: **in SEA/SA households, work and family collide constantly**, and the person holding it together needs a system that understands *both sides at once*. We did not bolt on cross-domain conflict resolution as a feature — we made it the central mechanic of the orchestration layer.

### 3b. The real-world problem Alfred addresses, and the practical impact

**The problem in one sentence:** Adults with professional and caregiving responsibilities are forced to be their own coordinator across systems that were never designed to talk to each other.

**The practical impact Alfred creates:**

1. **Reduced cognitive load.** A working parent stops checking five calendars before rescheduling a family appointment — Alfred holds the unified view and surfaces the conflict on its own.
2. **Action, not alerts.** When a conflict is detected, Alfred *proposes a resolution*, asks for confirmation, *executes it across Calendar and Gmail*, and *emails the affected contacts* (clinic, school, helper) — all in a single turn.
3. **Receipts.** Every action lands in Firestore `agentActions` with timestamp, agent, and intent. The user can ask "what did Alfred do?" and get a real, auditable answer — not a black box.
4. **One voice, one persona.** Instead of ten apps each with their own UI, the user has one trusted butler who replies in a consistent tone and never loses context across sessions.
5. **Discretion for high-stakes work.** The "Gotham Special Projects" logic (Batman / midnight / high-stakes mentions) escalates priority without leaking detail into family-facing channels.
6. **Cultural fit.** Alfred is built for code-switching, multi-generational households, and the assumption that a domestic helper is part of the coordination loop — not an edge case.

### 3c. Core approach / workflow

Alfred follows a clean **route → delegate → resolve → execute → log → reply** loop on every turn:

```
User message
    │
    ▼
[ alfred_root ] ── classify intent, translate dates, read household ctx
    │
    ▼
[ alfred_core_workflow : SequentialAgent ]
    │
    ├─▶ [ work_agent ]   → MCP: list/add events, send mail   → out: work_context
    │
    ├─▶ [ home_agent ]   → MCP: list/add events, send mail   → out: home_context
    │                      Firestore: update_household_ledger
    │
    └─▶ [ response_formatter ]
            • read work_context + home_context
            • detect conflict
            • resolve: update / delete / create event via MCP
            • notify affected contact via send_gmail_message
            • reply in Alfred's voice
    │
    ▼
Firestore audit trail (agentActions) + Cloud Logging
    │
    ▼
Reply to the Master
```

**Demo turn (the Thursday clash):**

> *User:* "Dad's physio clashes with my board presentation Thursday."

1. `work_agent` calls `list_events` → board meeting Thu 10:00.
2. `home_agent` calls `list_events` → physio Thu 10:00.
3. `response_formatter` sees both contexts, detects the overlap, calls `manage_event` to move the physio to Friday 09:00.
4. `search_contacts` finds the clinic; `send_gmail_message` drafts and sends the reschedule email.
5. `update_household_ledger` writes the action into Firestore `agentActions`.
6. Alfred replies: *"The physio is on Friday, sir. The clinic has been duly informed. Your board meeting stands."*

---

## 4. Opportunities — Differentiation & USP

### How Alfred differs from existing ideas

| Dimension | Existing tools (Motion, Reclaim, Notion AI, Superhuman, Carely, CareZone) | Alfred |
|---|---|---|
| Domain scope | Work **OR** family, rarely both | Work **AND** family as one unified system |
| Unit of use | The individual user | The **household graph** — members, roles, dependencies |
| Core mechanic | Scheduling and reminders | Cross-domain conflict **resolution with execution** |
| Action surface | Suggestions and alerts | Real Workspace actions via MCP — events created, mail sent, contacts looked up |
| Memory | Per-session, per-app | Persistent in Firestore + auditable `agentActions` ledger |
| Cultural fit | Built for Western single-user professionals | Built for SEA/SA multigenerational households, code-switching, helpers |
| Persona | Generic assistant | Alfred Pennyworth — dry, witty, discreet; "Gotham Special Projects" logic |
| Transparency | Black box | Every action timestamped and queryable in Firestore |
| Extensibility | Plug-in marketplaces | Add a new sub-agent in `sub_agents=[…]`, add a new tool by extending the MCP server — no infra change |

### Unique Selling Point

> **Alfred is the only ADK-based multi-agent system whose primary design challenge is the *collision point* between a user's professional and family responsibilities — not optimising either one in isolation.**

Three things make this real and not just a slogan:

1. **The household is the unit, not the individual.** Firestore stores members, priorities, and shared context. Conflict detection runs across the whole household, not just one person's calendar.
2. **Tool use is real, not simulated.** The MCP server is production-hosted on Cloud Run and talks to live Google Workspace APIs. When Alfred says "the clinic has been informed," an email actually went out.
3. **The persona is the interface.** A butler is not a chatbot — a butler holds context, exercises judgment, and never makes you repeat yourself. Alfred's tone, discretion, and unified voice are part of the product, not decoration.

---

## 5. List of Features Offered by the Solution

1. **Multi-agent orchestration on Google ADK** — `alfred_root` (orchestrator) + `SequentialAgent` pipeline of `work_agent` → `home_agent` → `response_formatter`, each with its own model, instructions, tools, and output channel.
2. **Automatic domain classification** — events are auto-routed as Work or Home using keyword and context rules baked into agent instructions (Work: meeting, board, client, deadline… / Home: dinner, school, doctor, birthday…).
3. **Cross-domain conflict detection and resolution in a single turn** — overlaps are surfaced *and fixed* before the user has to ask twice.
4. **Real Google Workspace actions through MCP**
   - **Calendar:** `add_event`, `manage_event` (create / update / delete), `list_events`
   - **Gmail:** `send_gmail_message` for notifying affected contacts
   - **Contacts:** `search_contacts`, `add_contact`, `get_contact`
5. **Contact-aware notifications** — when a conflict is resolved, Alfred looks up the affected party in Google Contacts and emails them automatically with the new arrangement.
6. **Persistent household graph in Firestore** — `households/default` stores members, priorities, and context across sessions; survives restarts and redeploys.
7. **Append-only audit trail (`agentActions`)** — every action is logged with `agent`, `intent`, `action`, `timestamp`. The user always has receipts.
8. **Temporal intelligence** — current date and timezone are injected into every agent instruction at startup; "midnight after 6 PM" automatically defaults to tomorrow.
9. **"Gotham Special Projects" mode** — mentions of Batman, midnight ops, or high-stakes meetings escalate to top-priority Work and are handled with discretion.
10. **Persona-consistent replies** — `response_formatter` delivers every reply in Alfred Pennyworth's dry, witty butler voice. No bullet-point walls.
11. **Cloud Logging out of the box** — `google.cloud.logging.Client().setup_logging()` streams every agent log to GCP for live observability.
12. **Local dev = production parity** — `adk web .` runs the same agent locally against the same Cloud Run MCP server; only the auth token differs.
13. **Vertex-safe tool filtering** — incompatible tools (e.g. `modify_gmail_message_labels`) are filtered out at MCP toolset construction time so the agent never sees an unusable schema.
14. **Multi-user OAuth gatekeeper (`web_login.py`)** — a FastAPI wrapper in front of the ADK Web UI handles Google sign-in, scope consent, refresh-token storage, and per-request token injection. One deployed agent safely serves many households.
15. **Per-user household namespacing** — Firestore documents are keyed by the authenticated user's email, not a shared `default` doc, so households never see each other's data.
16. **Pluggable sub-agents** — adding `FinanceAgent`, `CareAgent`, or `TravelAgent` is one Python entry in the `sub_agents=[…]` list; the orchestration layer needs no changes.

---

## 6. Process Flow Diagram

A simple, single-turn view of what happens when a user sends Alfred a message.

```
        ┌─────────────────────────────┐
        │           USER              │
        │   "Dad's physio clashes     │
        │    with my board Thu"       │
        └──────────────┬──────────────┘
                       │ natural language
                       ▼
        ┌─────────────────────────────┐
        │         ALFRED ROOT         │
        │   classify · route · greet  │
        └──────────────┬──────────────┘
                       │
                       ▼
        ┌─────────────────────────────┐
        │   alfred_core_workflow      │
        │     (SequentialAgent)       │
        └──────────────┬──────────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
  ┌─────────┐    ┌─────────┐    ┌──────────────┐
  │  WORK   │ ─▶ │  HOME   │ ─▶ │  RESPONSE    │
  │  AGENT  │    │  AGENT  │    │  FORMATTER   │
  └────┬────┘    └────┬────┘    └──────┬───────┘
       │              │                │
       │ list_events  │ list_events    │ resolve conflict
       │ add_event    │ manage_event   │ manage_event
       │ send_mail    │ send_mail      │ send_mail
       ▼              ▼                ▼
  ┌──────────────────────────────────────────┐
  │       MCP SERVER  (Cloud Run)            │
  │  Calendar · Gmail · Contacts             │
  └────────────────────┬─────────────────────┘
                       │
                       ▼
  ┌──────────────────────────────────────────┐
  │   GOOGLE WORKSPACE APIs (live)           │
  └────────────────────┬─────────────────────┘
                       │
                       ▼
  ┌──────────────────────────────────────────┐
  │   FIRESTORE  ·  agentActions audit log   │
  │   { agent, intent, action, timestamp }   │
  └────────────────────┬─────────────────────┘
                       │
                       ▼
        ┌─────────────────────────────┐
        │     ALFRED REPLIES          │
        │ "The physio is on Friday,   │
        │  sir. Clinic informed."     │
        └─────────────────────────────┘
```

**Use-case in one line:** *one user message → multiple agents → real Workspace actions → audit log → one polished reply.*

---

## 7. Wireframes / Mock Diagrams

A simple 4-screen mock of the user-facing surface.

```
┌──────────────────────┐  ┌──────────────────────┐
│   HOME DASHBOARD     │  │     ALFRED CHAT      │
│ ──────────────────── │  │ ──────────────────── │
│  Good morning, sir.  │  │  A: "Dad's physio    │
│  Today's agenda:     │  │      moved to Fri.   │
│                      │  │      Clinic notified"│
│  [WORK]              │  │                      │
│  • Board meeting     │  │  You: "Also remind   │
│    Thu 10:00         │  │        me to call    │
│  • Supplier call     │  │        the clinic"   │
│    Thu 15:00         │  │                      │
│                      │  │  A: "Naturally, sir."│
│  [HOME]              │  │                      │
│  • Dad physio  ⚠     │  │ ─────────────────────│
│    Thu 10:00 CLASH   │  │  [ Tell Alfred…   ]  │
│  • School concert    │  │                      │
│    Fri 18:00         │  │                      │
│ ──────────────────── │  │                      │
│  [ Tell Alfred… ]    │  │                      │
└──────────────────────┘  └──────────────────────┘

┌──────────────────────┐  ┌──────────────────────┐
│       FAMILY         │  │   ALERTS / ACTIONS   │
│ ──────────────────── │  │ ──────────────────── │
│  ┌────────────────┐  │  │  ⚠  CONFLICT         │
│  │ Dad   (Parent) │  │  │  Board meeting and   │
│  │ Physio Thu     │  │  │  physio Thu 10:00    │
│  └────────────────┘  │  │  [Resolve] [Later]   │
│  ┌────────────────┐  │  │                      │
│  │ Mei  (Child)   │  │  │  ── Alfred's log ──  │
│  │ Concert Fri    │  │  │  ✓ Physio → Fri 9am  │
│  └────────────────┘  │  │  ✓ Clinic emailed    │
│  ┌────────────────┐  │  │  ✓ Helper notified   │
│  │ Siti (Helper)  │  │  │  ✓ Logged Firestore  │
│  │ On duty        │  │  │                      │
│  └────────────────┘  │  │                      │
│                      │  │                      │
│  [ + Add member ]    │  │                      │
└──────────────────────┘  └──────────────────────┘

       Bottom tabs:  Home · Chat · Family · Alerts
```

**Why these four screens?**
- **Home Dashboard** — the unified work+home view, with conflicts visually flagged.
- **Chat** — the natural-language interface to Alfred himself.
- **Family** — the household graph: members, roles, recurring needs.
- **Alerts** — proactive conflict surfacing and the running action log (the "receipts").

---

## 8. Architecture Diagram

A simple layered view of the system. Each box is a real, deployed component.

```
┌──────────────────────────────────────────────────────────────┐
│                       CLIENT LAYER                           │
│   ADK Web UI (local)   │   React + Vite (Firebase Hosting)   │
└──────────────────────────────┬───────────────────────────────┘
                               │  HTTPS
                               ▼
┌──────────────────────────────────────────────────────────────┐
│        AUTH GATEKEEPER  —  web_login.py  (FastAPI)           │
│   Google OAuth2 + OIDC  ·  scope consent  ·  refresh tokens  │
│   per-user SESSION_TOKEN_STORE  →  token_context (ContextVar)│
└──────────────────────────────┬───────────────────────────────┘
                               │  authenticated request
                               ▼
┌──────────────────────────────────────────────────────────────┐
│       ADK AGENT RUNTIME  (Cloud Run · asia-southeast2)       │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │              alfred_root  (Agent)                    │   │
│   │   model: gemini-2.5-flash via Vertex AI              │   │
│   │   tools: assess_household_conflicts                  │   │
│   └────────────────────────┬─────────────────────────────┘   │
│                            ▼                                 │
│   ┌──────────────────────────────────────────────────────┐   │
│   │       alfred_core_workflow (SequentialAgent)         │   │
│   │  ┌────────────┐  ┌────────────┐  ┌────────────────┐  │   │
│   │  │ work_agent │─▶│ home_agent │─▶│   response_    │  │   │
│   │  │            │  │            │  │   formatter    │  │   │
│   │  │ out:       │  │ out:       │  │                │  │   │
│   │  │ work_ctx   │  │ home_ctx   │  │ → user reply   │  │   │
│   │  └─────┬──────┘  └─────┬──────┘  └────────┬───────┘  │   │
│   └────────┼───────────────┼──────────────────┼──────────┘   │
└────────────┼───────────────┼──────────────────┼──────────────┘
             │               │                  │
             └───────────────┴──────────────────┘
                             │  HTTPS + Bearer token
                             ▼
┌──────────────────────────────────────────────────────────────┐
│            MCP LAYER  —  workspace-mcp (Cloud Run)           │
│                                                              │
│   add_event     manage_event     list_events                 │
│   send_gmail_message                                         │
│   search_contacts   add_contact   get_contact                │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                   GOOGLE WORKSPACE APIs                      │
│   Calendar  ·  Gmail  ·  People (Contacts)  ·  Meet          │
└──────────────────────────────────────────────────────────────┘

         ╔════════════════════════════════════════════╗
         ║         STATE & OBSERVABILITY              ║
         ║ ────────────────────────────────────────── ║
         ║  Firestore  (keyed by user email)          ║
         ║   ├── households/{email}   (context)       ║
         ║   └── agentActions         (audit ledger)  ║
         ║                                            ║
         ║  Cloud Logging  (auto-attached at boot)    ║
         ║                                            ║
         ║  Vertex AI       (Gemini 2.5 Flash)        ║
         ║  ADC + OAuth     (Workspace auth)          ║
         ╚════════════════════════════════════════════╝
```

**How to read it:**
- **Top to bottom = request flow.** A user message enters at the client, hits the ADK agent runtime, descends through the sub-agent pipeline, calls the MCP server, which calls live Google Workspace APIs.
- **Side panel = cross-cutting concerns.** Firestore (memory + audit), Cloud Logging (observability), Vertex AI (model), and ADC (auth) are used by every layer above.
- **Two Cloud Run services.** One hosts the ADK agent runtime, the other hosts the MCP server. Decoupling them means the MCP layer is independently versionable and reusable by any other agent we build later.

---

## 9. Technologies / Google Services Used

| Layer | Service | Why we chose it |
|---|---|---|
| Agent framework | **Google ADK** (`google.adk`) | Native multi-agent primitives — `Agent`, `SequentialAgent`, `ToolContext`, `output_key` — and first-class MCP support. Lets us focus on agent design instead of plumbing under hackathon time pressure. |
| LLM | **Vertex AI — Gemini 2.5 Flash** | Fast, cheap, strong tool-use / function-calling reliability, and excellent multilingual performance for SEA/SA code-switching. Vertex gives us managed quotas, IAM, and regional deployment. |
| Tool protocol | **MCP (Model Context Protocol)** via `McpToolset` + `StreamableHTTPConnectionParams` | Decouples tools from agent code. One MCP server exposes the entire Google Workspace surface and is reusable by any future ADK agent (FinanceAgent, CareAgent, etc.) without changing a line of orchestration logic. |
| MCP server hosting | **Cloud Run** | Serverless, scales to zero, one-command deploy, HTTPS by default, integrates natively with IAM. Ideal for stateless tool servers. |
| Database | **Cloud Firestore** | Document model fits the household graph naturally. Powers both persistent context (`households`) and the append-only audit log (`agentActions`). Real-time listeners enable a live UI later with no extra plumbing. |
| Observability | **Cloud Logging** (`google.cloud.logging`) | Auto-attached at agent startup. Every `logging.info/warning/error` from every sub-agent becomes a structured, searchable cloud log. Zero extra code. |
| Auth | **Google OAuth2 + OpenID Connect** via a custom **FastAPI gatekeeper (`web_login.py`)**, plus ADC for GCP-side calls | The gatekeeper handles the full per-user OAuth flow (consent → access token → refresh token → session store), then injects the user's token into the agent runtime via a `ContextVar`. ADC handles agent-to-GCP calls (Firestore, Logging, Vertex). Scopes: Calendar, Gmail modify+send, Contacts, OIDC. |
| Deployment region | **Cloud Run — `asia-southeast2` (Jakarta)** | Closest GCP region to the target SEA user base — lowest latency for Workspace + Vertex calls and keeps user data in-region. |
| Workspace APIs | **Google Calendar, Gmail, People (Contacts), Meet** | The actual action surface. Alfred's value is in how it *coordinates* these, not in replacing them. |
| Frontend hosting (optional) | **Firebase Hosting** | CDN-backed, one-command deploy, pairs natively with Firestore and Firebase Auth. |
| Forward path (production) | **AlloyDB AI** | When Alfred's memory grows large enough that semantic recall matters ("what did Alfred do last time Dad missed physio?"), AlloyDB AI gives us SQL + vector search in a single store, replacing Firestore for relational + semantic queries. |

### Why this AI stack and system design supports scalability and real-world deployment

**1. Horizontal scale by default.** Both Cloud Run services (the ADK agent runtime and the MCP server) scale from zero to thousands of concurrent sessions with no code change. The same deployment serves 10 users or 10,000.

**2. Stateless runtime, stateful memory.** The ADK runtime itself holds no per-user state — all memory lives in Firestore. Any instance can be killed, replaced, or scaled out without losing household context. This is the standard pattern for production-grade serverless systems.

**3. Extensibility without infra rewrites.**
- **Adding a sub-agent** (e.g. `FinanceAgent` for household budgeting, `CareAgent` for elderly health) is one new `Agent(...)` definition and one entry in `sub_agents=[…]`.
- **Adding a tool** is a change in the MCP server, not the agent. No agent redeploy needed.
- **Swapping the model** is one env variable (`MODEL=`).

**4. Schema-free state.** Firestore's document model means the household graph can evolve — new member types, new priority rules, new event categories — with zero migrations.

**5. Production auth path.** ADC + per-user OAuth tokens on the MCP server is the same authorization pattern Google uses for its own Workspace integrations, which means the security model is directly productionisable, not a hackathon shortcut.

**6. Observability and trust on day one.** Cloud Logging gives engineers structured logs; Firestore's `agentActions` collection gives users a human-readable audit log of every decision Alfred made. Both ship with the first deploy — not as a future "v2" promise.

**7. Decoupled MCP layer = reusable tool fabric.** The `workspace-mcp` Cloud Run service is independent of Alfred. Any future ADK agent we build (or any other team's agent) can connect to the same MCP endpoint with a Bearer token. The investment in the MCP layer compounds across products.

**8. A clear path to AlloyDB AI.** When Alfred's memory matures from "remember the household" to "remember the *history* of how I solved problems for this household," AlloyDB AI's SQL + vector search slots in behind the same Firestore-shaped interface. The migration is incremental, not a rewrite.

In short: the stack is **fast enough to ship in a hackathon, and serious enough to run in production** — which is exactly what a multi-agent assistant for real households needs.

---

*Alfred — built for the Google × Hack2skill Hackathon. Multi-agent AI on Google Cloud with ADK + MCP. For everyone who wants to show up fully at work without losing their family.*
