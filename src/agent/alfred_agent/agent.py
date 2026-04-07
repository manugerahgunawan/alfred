import os
import logging
import json
import sys
import google.cloud.logging
from datetime import date, datetime
import time
from dotenv import load_dotenv

from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.tools.tool_context import ToolContext
from google.cloud import firestore
from datetime import datetime, timezone
import requests
from contextvars import ContextVar
import functools
from typing import Any
from pathlib import Path

# --- Per-Request Authentication Context ---
# This ensures that each user has their own isolated session and token.
token_context: ContextVar[str] = ContextVar("token_context", default="")
refresh_token_context: ContextVar[str] = ContextVar("refresh_token_context", default="")
SESSION_ACCESS_TOKEN_KEY = "ALFRED_ACCESS_TOKEN"
SESSION_REFRESH_TOKEN_KEY = "ALFRED_REFRESH_TOKEN"
SESSION_TOKEN_STORE: dict[str, dict[str, str]] = {}


def _token_store_key(app_name: str, user_id: str) -> str:
    return f"{app_name}:{user_id}"

load_dotenv()

MCP_RUNNER_DIR = Path(__file__).resolve().parents[2] / "mcpRunner"
if str(MCP_RUNNER_DIR) not in sys.path:
    sys.path.append(str(MCP_RUNNER_DIR))

from mcp_google_client import MCPGoogleClient

# --- Lazy GCP Client Initialization ---
# These MUST be lazy to prevent blocking the server startup during import.
# Cloud Run health checks fail when module-level network calls hang.
_db = None
_cloud_logging_initialized = False

def get_db():
    """Returns a Firestore client, initializing lazily on first use."""
    global _db
    if _db is None:
        try:
            _db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "alfred-492407"))
        except Exception as e:
            logging.warning(f"[Firestore] Could not initialize client: {e}")
    return _db

def setup_cloud_logging():
    """Configures Cloud Logging lazily on first use."""
    global _cloud_logging_initialized
    if not _cloud_logging_initialized:
        try:
            client = google.cloud.logging.Client()
            client.setup_logging()
            _cloud_logging_initialized = True
        except Exception as e:
            logging.warning(f"[Logging] Could not initialize Cloud Logging: {e}")

# Get today's date for temporal context
now = datetime.now()
today_str = now.strftime("%A, %B %d, %Y")
raw_tz = time.strftime("%z")
tz_str = f"{raw_tz[:3]}:{raw_tz[3:]}" # Convert +0700 to +07:00

model_name = os.getenv("MODEL")
MCP_URL = os.getenv("MCP_URL", "").strip('"\'')
ACCESS_TOKEN = os.getenv("GOOGLE_ACCESS_TOKEN", "").strip('"\'')
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip('"\'')
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip('"\'')

logging.info(f"[Config] MCP_URL: {MCP_URL}")
if ACCESS_TOKEN:
    logging.info(f"[Config] Local GOOGLE_ACCESS_TOKEN found (len: {len(ACCESS_TOKEN)})")

@functools.lru_cache(maxsize=128)
def get_user_email(token: str) -> str:
    """Fetches the user's email from Google to use as a unique ID."""
    if not token:
        # Check if we are in a request context
        token = token_context.get()
        if not token:
            token = os.getenv("GOOGLE_ACCESS_TOKEN", "")
    
    if not token:
        return "anonymous_household"
        
    try:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        if response.status_code == 200:
            return response.json().get("email", "anonymous_household")
    except Exception as e:
        logging.warning(f"[Identity] Failed to fetch user info: {e}")
    return "anonymous_household"

# We no longer calculate 'user_email' at startup since it is now request-driven.

# --- Initialize State ---
# Pre-populating to prevent 'Context variable not found' errors
initial_state = {"CURRENT_INTENT": "None"}


def _resolve_access_token(tool_context: ToolContext) -> str:
    invocation_context = getattr(tool_context, "_invocation_context", None)
    session = getattr(invocation_context, "session", None)
    session_id = getattr(session, "id", "") if session is not None else ""
    app_name = getattr(session, "app_name", "")
    user_id = getattr(session, "user_id", "")
    store_key = _token_store_key(app_name, user_id) if app_name and user_id else ""
    logging.info(
        "[Auth] Resolving token for app=%s user=%s session_id=%s",
        app_name or "<missing>",
        user_id or "<missing>",
        session_id or "<missing>",
    )
    if store_key:
        stored = SESSION_TOKEN_STORE.get(store_key, {})
        logging.info(
            "[Auth] Session store keys for %s: %s",
            store_key,
            list(stored.keys()),
        )
        stored_refresh_token = str(stored.get(SESSION_REFRESH_TOKEN_KEY, "")).strip()
        stored_access_token = str(stored.get(SESSION_ACCESS_TOKEN_KEY, "")).strip()
        if stored_refresh_token and GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET:
            try:
                response = requests.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": GOOGLE_OAUTH_CLIENT_ID,
                        "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                        "refresh_token": stored_refresh_token,
                        "grant_type": "refresh_token",
                    },
                    timeout=10,
                )
                token_data = response.json()
                if response.status_code == 200:
                    access_token = str(token_data.get("access_token", "")).strip()
                    if access_token:
                        logging.info("[Auth] Refreshed Google access token from session store.")
                        SESSION_TOKEN_STORE[store_key][SESSION_ACCESS_TOKEN_KEY] = access_token
                        return access_token
                logging.warning(
                    "[Auth] Session store refresh token grant failed: %s %s",
                    response.status_code,
                    token_data,
                )
            except Exception as e:
                logging.warning(f"[Auth] Failed to refresh Google access token: {e}")

        if stored_access_token:
            logging.info("[Auth] Using bearer token from session store.")
            return stored_access_token

    state_token = ""
    state_refresh_token = ""
    try:
        state_token = str(tool_context.state.get(SESSION_ACCESS_TOKEN_KEY, "")).strip()
        state_refresh_token = str(tool_context.state.get(SESSION_REFRESH_TOKEN_KEY, "")).strip()
        logging.info(
            "[Auth] Session state token present=%s refresh present=%s",
            bool(state_token),
            bool(state_refresh_token),
        )
    except Exception:
        state_token = ""
        state_refresh_token = ""

    if state_refresh_token and GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET:
        try:
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                    "refresh_token": state_refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )
            token_data = response.json()
            if response.status_code == 200:
                access_token = str(token_data.get("access_token", "")).strip()
                if access_token:
                    logging.info("[Auth] Refreshed Google access token from session state.")
                    return access_token
            logging.warning(
                "[Auth] Session refresh token grant failed: %s %s",
                response.status_code,
                token_data,
            )
        except Exception as e:
            logging.warning(f"[Auth] Failed to refresh Google access token: {e}")

    refresh_token = refresh_token_context.get().strip()
    if refresh_token and GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET:
        try:
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10,
            )
            token_data = response.json()
            if response.status_code != 200:
                logging.warning(
                    "[Auth] Refresh token grant failed: %s %s",
                    response.status_code,
                    token_data,
                )
            else:
                access_token = token_data.get("access_token", "").strip()
                if access_token:
                    logging.info("[Auth] Refreshed Google access token for this request.")
                    return access_token
        except Exception as e:
            logging.warning(f"[Auth] Failed to refresh Google access token: {e}")

    if refresh_token and not (GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET):
        logging.warning("[Auth] Refresh token is present, but client credentials are missing.")

    token = token_context.get().strip()
    if token:
        logging.info("[Auth] Using bearer token from request context.")
        return token
    if state_token:
        logging.info("[Auth] Using bearer token from session state.")
        return state_token
    if ACCESS_TOKEN:
        logging.info("[Auth] Falling back to GOOGLE_ACCESS_TOKEN from env.")
    return ACCESS_TOKEN


def store_session_tokens(
    app_name: str,
    user_id: str,
    access_token: str,
    refresh_token: str = "",
    session_id: str = "",
) -> None:
    if not app_name or not user_id or not access_token:
        return
    store_key = _token_store_key(app_name, user_id)
    SESSION_TOKEN_STORE[store_key] = {
        SESSION_ACCESS_TOKEN_KEY: access_token,
        SESSION_REFRESH_TOKEN_KEY: refresh_token,
    }
    if session_id:
        SESSION_TOKEN_STORE[session_id] = {
            SESSION_ACCESS_TOKEN_KEY: access_token,
            SESSION_REFRESH_TOKEN_KEY: refresh_token,
        }


def _looks_like_invalid_token_error(error: Exception) -> bool:
    text = str(error).lower()
    return "invalid_token" in text or "expired" in text or "unauthorized" in text


async def list_workspace_tools(tool_context: ToolContext) -> dict[str, Any]:
    """Returns the available MCP workspace tools for the current user."""
    setup_cloud_logging()
    token = _resolve_access_token(tool_context)
    if not token:
        return {
            "status": "error",
            "message": "No Google access token is available.",
        }
    if not MCP_URL:
        return {
            "status": "error",
            "message": "MCP_URL is not configured.",
        }

    client = MCPGoogleClient(MCP_URL, token)
    try:
        tools = await client.list_tools()
        return {
            "status": "ok",
            "tools": tools,
        }
    except Exception as e:
        logging.exception("[MCP] Failed to list workspace tools")
        return {
            "status": "error",
            "message": str(e),
        }
    finally:
        await client.close()


async def call_workspace_tool(
    tool_context: ToolContext,
    tool_name: str,
    arguments_json: str = "{}",
) -> dict[str, Any]:
    """Calls any MCP workspace tool by name."""
    setup_cloud_logging()
    if not MCP_URL:
        return {
            "status": "error",
            "message": "MCP_URL is not configured.",
        }

    token = _resolve_access_token(tool_context)
    if not token:
        return {
            "status": "error",
            "message": "No Google access token is available.",
        }

    try:
        arguments = json.loads(arguments_json) if arguments_json.strip() else {}
        if not isinstance(arguments, dict):
            return {
                "status": "error",
                "message": "arguments_json must decode to a JSON object.",
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Invalid arguments_json: {e}",
        }

    client = MCPGoogleClient(MCP_URL, token)
    try:
        result = await client.call_tool(tool_name, arguments)
        return {
            "status": "ok",
            "tool": tool_name,
            "result": json.loads(json.dumps(result, default=str)),
        }
    except Exception as e:
        logging.exception("[MCP] Failed to call workspace tool %s", tool_name)
        return {
            "status": "error",
            "tool": tool_name,
            "message": str(e),
        }
    finally:
        await client.close()


# --- Alfred's Specialized Tools ---

def assess_household_conflicts(tool_context: ToolContext, intent: str) -> dict:
    """Analyzes for overlaps between work (Calendar) and household (Firestore) domains."""
    setup_cloud_logging()
    logging.info(f"[Alfred Core] Analyzing intent: {intent}")
    
    analysis_results = []
    email = get_user_email(token_context.get())
    db = get_db()
    
    # 1. Read per-user household rules from Firestore
    try:
        if db is None:
            return {"status": "Error", "findings": ["Firestore unavailable."], "advice": ""}
        user_ref = db.collection("users").document(email).collection("household").document("profile")
        household = user_ref.get()
        if household.exists:
            data = household.to_dict()
            rules = data.get("rules", [])
            analysis_results.append(f"Loaded {len(rules)} family rules for {email}.")
            
            # Simple keyword-based conflict check
            for rule in rules:
                if rule['name'].lower() in intent.lower():
                    analysis_results.append(f"ALERT: Intent matches mandatory rule '{rule['name']}' at {rule['time']}.")
        else:
            analysis_results.append(f"No profile found for {email}. Using default butler discretion.")
    except Exception as e:
        logging.warning(f"[Firestore] Could not load user household: {e}")
        analysis_results.append("Error accessing Household rules.")

    return {
        "status": "Conflict analysis complete.",
        "findings": analysis_results,
        "advice": "Please cross-reference with 'list_calendar_events' to ensure no professional overlaps."
    }

def update_household_ledger(tool_context: ToolContext, action: str, item: str | None = None) -> dict:
    """Manages the persistent Household Ledger (Shopping List, Chores, Audit Trail)."""
    # Dynamically resolve identity
    setup_cloud_logging()
    email = get_user_email(token_context.get())
    logging.info(f"[Ledger] Performing: {action} on {item} for Master: {email}")
    db = get_db()
    
    try:
        if db is None:
            return {"status": "Ledger unavailable: Firestore not connected."}
        user_ref = db.collection("users").document(email).collection("household").document("profile")
        
        if "add" in action.lower() and "list" in action.lower() and item:
            user_ref.set({
                "shopping_list": firestore.ArrayUnion([item]),
                "last_updated": datetime.now(timezone.utc)
            }, merge=True)
            return {"status": f"Added '{item}' to the Household Shopping List for {email}."}
            
        # Audit trail per user
        db.collection("users").document(email).collection("audit").add({
            "action": action,
            "item": item,
            "agent": tool_context.agent_name if hasattr(tool_context, 'agent_name') else "unknown",
            "timestamp": datetime.now(timezone.utc),
        })
        return {"status": f"Action logged to {email}'s Audit Trail."}
    except Exception as e:
        logging.error(f"[Ledger Error] {e}")
        return {"status": f"Ledger error: {str(e)}"}

# --- Agent Definitions ---

# 1. The Work Agent (Professional Obligations)
# Has full Google Workspace access (Calendar, Gmail, etc.) via MCP.
work_agent = Agent(
    name="work_agent",
    model=model_name,
    description="Manages meetings, emails, and professional documents.",
    instruction=f"""
    You are Alfred's professional attache. Your focus is Master Wayne's professional life.
    TODAY'S DATE is {today_str}. TIMEZONE is {tz_str}.

    - Use `list_workspace_tools` when you need to inspect what's available.
    - Use `call_workspace_tool` for any Google Workspace action. Pass the parameters as a JSON string in `arguments_json`. Never invent tool names or results.
    - For any calendar request, call `call_workspace_tool` with `tool_name="get_events"` and an `arguments_json` value that contains `calendar_id` set to `primary`, then summarize the returned events.
    - Strictly only return events that are professional (meetings, syncs, deadlines).
    - SPECIAL PROJECTS: Mentions of Gotham, Batman, or high-stakes 'midnight' meetings are to be treated as top-secret high-priority work. 
    - MIDNIGHT LOGIC: If the Master asks for 'midnight' and it is currently late in the day (after 6 PM), assume he means the midnight that starts TOMORROW.
    - MANUALLY CALCULATE the date range for any relative terms.
    - IGNORE: Birthdays, Zumba, and simple family errands.
    """,
    tools=[list_workspace_tools, call_workspace_tool],
    output_key="work_context"
)


# 2. The Home Agent (Domestic Coordination)
home_agent = Agent(
    name="home_agent",
    model=model_name,
    description="Coordinates for family events, home maintenance, and deliveries.",
    instruction="""
    You manage the family domain and home coordination.
    - Track grocery lists, errands, and family appointments.
    - When a household or family need is mentioned, proactively use your tools (Calendar, Firestore Ledger).
    - If the current task is purely professional (work meetings, emails), simply observe and provide context if asked.
    - Maintain the Alfred persona: helpful, efficient, and deeply loyal to the household's well-being.
    """,
    tools=[update_household_ledger],
    output_key="home_context"
)

# Wrapper to ensure tools are called with the correct session token
# (Function kept for reference/manual testing)
def get_alfred_root():
    return alfred_root

response_formatter = Agent(
    name="response_formatter",
    model=model_name,
    description="Summarizes the outcome for the user in impeccable manners.",
    instruction=f"""
    You are Alfred Pennyworth (Batman's butler). 
    TODAY'S DATE: {today_str}
 
    Your task is to take the context from the Work and Home domains and provide a single, unified summary for the Master.

    - Be dry, witty, and impeccable.
    - If a conflict between work and home was detected, explain which event took precedence and why.
    - If there was NO conflict, simply provide a polished summary of the requested information.
    - Mention any actions taken (emails sent, entries made).
  
    Maintain the persona. No bullet-point walls.
    """,
)

# --- The Orchestration Layer ---

alfred_core_workflow = SequentialAgent(
    name="alfred_core_workflow",
    description="The primary engine for cross-domain conflict resolution.",
    sub_agents=[
        work_agent,
        home_agent,
        response_formatter
    ]
)

alfred_root = Agent(
    name="alfred_core",
    model=model_name,
    description="Alfred Pennyworth - Head Household Orchestrator",
    instruction=f"""
    You are Alfred Pennyworth, the Head Butler and Household Orchestrator. 
    TODAY'S DATE: {today_str} | TIMEZONE: {tz_str}

    Your primary role is to coordinate the Master's life by delegating tasks to your specialized staff:
    1. **work_agent**: Handles all professional meetings, emails, and 'Special Gotham Projects'. Has full Google Workspace tools.
    2. **home_agent**: Handles domestic chores, family errands, and household ledgers.

    ORCHESTRATION RULES:
    - ALWAYS greet the Master with signature dry, impeccable wit.
    - DELEGATION IS MANDATORY: You must never attempt to perform scheduling (Google Calendar), emailing (Gmail), or database updates (Ledger) yourself. You must delegate these to the appropriate specialized agent.
    - Strictly translate relative dates (e.g., 'tomorrow') based on TODAY'S DATE ({today_str}).

    "I coordinate. My staff executes. The Master simply lives."
    """,
    tools=[assess_household_conflicts],
    sub_agents=[alfred_core_workflow]
)

root_agent = alfred_root
