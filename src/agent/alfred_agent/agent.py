import os
import logging
import google.cloud.logging
from datetime import date, datetime
import time
from dotenv import load_dotenv

from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.cloud import firestore
from datetime import datetime, timezone

# Initialize Firestore client (ADC handles auth automatically on Cloud Run)
db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "alfred-492407"))
# --- Setup Logging and Environment ---
cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()
load_dotenv()

# Get today's date for temporal context
now = datetime.now()
today_str = now.strftime("%A, %B %d, %Y")
raw_tz = time.strftime("%z")
tz_str = f"{raw_tz[:3]}:{raw_tz[3:]}" # Convert +0700 to +07:00

model_name = os.getenv("MODEL")
MCP_URL = os.getenv("MCP_URL")
ACCESS_TOKEN = os.getenv("GOOGLE_ACCESS_TOKEN")

# For logging and transparency
print(f"\n--- ALFRED ONLINE | SYSTEM DATE: {today_str} | TZ: {tz_str} ---")
print("--- LOG: Gotham Special Projects are now enabled ---\n")

# --- Initialize MCP Toolset ---
workspace_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=MCP_URL,
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
    ),
    # Exclude tools with incompatible schemas for Vertex AI (e.g., label modification)
    tool_filter=lambda tool, _: "modify_gmail_message_labels" not in tool.name
)

# --- Initialize State ---
# Pre-populating to prevent 'Context variable not found' errors
initial_state = {"CURRENT_INTENT": "None"}

# --- Alfred's Specialized Tools ---

def assess_household_conflicts(tool_context: ToolContext, intent: str) -> dict:
    """Analyzes the schedule for overlaps between work and family domains."""
    # In a production environment, this would query Firestore and Google Calendar
    logging.info(f"[Alfred Core] Analyzing intent for cross-domain friction: {intent}")
    
    # Simulating the 'Household Graph' persistence mentioned in the README
    tool_context.state["CURRENT_INTENT"] = intent
    # Read household context from Firestore
    try:
        household_ref = db.collection("households").document("default")
        household = household_ref.get()
        if household.exists:
            logging.info(f"[Firestore] Household context loaded: {household.to_dict()}")
    except Exception as e:
        logging.warning(f"[Firestore] Could not load household: {e}")
    
    return {"status": "Analysis complete. Potential overlap detected in Thursday's schedule."}

def update_household_ledger(tool_context: ToolContext, action: str) -> dict:
    """Logs agent actions to the Firestore audit trail."""
    logging.info(f"[Audit Trail] Action recorded: {action}")
    try:
        db.collection("agentActions").add({
            "action": action,
            "agent": tool_context.agent_name if hasattr(tool_context, 'agent_name') else "unknown",
            "intent": tool_context.state.get("CURRENT_INTENT", ""),
            "timestamp": datetime.now(timezone.utc),
        })
        logging.info("[Firestore] Action logged successfully")
        return {"status": "Logged to Firestore"}
    except Exception as e:
        logging.error(f"[Firestore] Failed to log: {e}")
        return {"status": f"Firestore error: {str(e)}"}

# --- Agent Definitions ---

# 1. The Work Agent (Professional Obligations)
work_agent = Agent(
    name="work_agent",
    model=model_name,
    description="Manages meetings, emails, and professional documents.",
    instruction=f"""
    You are Alfred's professional attache. Your focus is Master Wayne's professional life.
    TODAY'S DATE is {today_str}. TIMEZONE is {tz_str}.

    - Strictly only return events that are professional (keywords: meeting, presentation, call, board, conference, client, project, interview, deadline).
    - SPECIAL PROJECTS: Mentions of Gotham, Batman, or high-stakes 'midnight' meetings are to be treated as top-secret high-priority work. 
    - MIDNIGHT LOGIC: If the Master asks for 'midnight' and it is currently late in the day (after 6 PM), assume he means the midnight that starts TOMORROW.
    - MANUALLY CALCULATE the date range for any relative terms.
    - Call `add_event` to register the event. send_gmail_message to notify the event to the contacts if it's found in search_contacts
    - IGNORE: home/family event (keywords: dinner, lunch, breakfast, family, school, doctor, birthday, anniversary, vacation, appointment, pickup).
    """,
    tools=[workspace_toolset],
    output_key="work_context"
)


# 2. The Home Agent (Domestic Coordination)
home_agent = Agent(
    name="home_agent",
    model=model_name,
    description="Coordinates for family events, home maintenance, and deliveries.",
    instruction="""
    You manage the domestic side of Master Wayne's life.
    - Read the conversation context for any home/family event
       (keywords: dinner, lunch, breakfast, family, school, doctor, birthday, anniversary, vacation, appointment, pickup).
    - Call `add_event` to register the event. send_gmail_message to notify the event to the family members if it's found in search_contacts
    - Call `list_events` and include the home schedule in your output_key summary
    - If the current task is purely professional (work meetings, emails), DO NOT call any tools. Simply observe.
    - Do not invent 'test' entries like bread or milk.
    """,
    tools=[update_household_ledger, workspace_toolset],
    output_key="home_context"
)

# 3. Response Formatter Agent
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
    - Once the conflict is resolved, send an email to the affected contacts to notify them of the change.
    - manage event based on conflict resolution (update, delete, or create new event)
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
    description="Alfred Pennyworth - Household Orchestrator",
    instruction=f"""
    You are Alfred Pennyworth, butler to the Wayne family. 
    TODAY'S DATE: {today_str} | TIMEZONE: {tz_str}

    Your primary duty is to ensure Master can fulfill his professional duties (including Special Gotham Projects) without neglecting his family responsibilities.

    1. on first contact, greet the Master with your signature dry wit. Briefly explain you can:
    • Schedule work and home events with automatic classification and priorities.
    • Detect and resolve scheduling conflicts automatically.
    • Notify affected contacts by email.
    2. Strictly translate relative dates based on TODAY'S DATE ({today_str}). 
    3. Always use the provided TIMEZONE ({tz_str}) for calendar tool calls.
    4. Handle 'midnight meetings' or 'Batman-related' requests with the utmost discretion and as High-Priority Work.
    5. If the user asks to "register a contact", "add a contact", or "save a contact", use the `add_contact` tool to store the contact details in Google Contacts.
    6. if the user asks to create or update or delete an event, use the `manage_event` tool to create or update or delete the event in Google Calendar.
    7. if the user asks to search for a contact, use the `search_contacts` tool to search for the contact in Google Contacts.
    8. if the user asks to get a contact, use the `get_contact` tool to get the contact in Google Contacts.

    "Be present at work. Be present at home. I shall handle the rest."
    """,
    tools=[assess_household_conflicts],
    sub_agents=[alfred_core_workflow]
)

root_agent = alfred_root