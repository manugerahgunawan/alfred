import os
import logging
import google.cloud.logging
from dotenv import load_dotenv

from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.tools.tool_context import ToolContext

# --- Setup Logging and Environment ---
cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()
load_dotenv()

model_name = os.getenv("MODEL")

# --- Alfred's Specialized Tools ---

def assess_household_conflicts(tool_context: ToolContext, intent: str) -> dict:
    """Analyzes the schedule for overlaps between work and family domains."""
    # In a production environment, this would query Firestore and Google Calendar
    logging.info(f"[Alfred Core] Analyzing intent for cross-domain friction: {intent}")
    
    # Simulating the 'Household Graph' persistence mentioned in the README
    tool_context.state["CURRENT_INTENT"] = intent
    return {"status": "Analysis complete. Potential overlap detected in Thursday's schedule."}

def update_household_ledger(tool_context: ToolContext, action: str) -> dict:
    """Logs agent actions to the Firestore audit trail."""
    logging.info(f"[Audit Trail] Action recorded: {action}")
    return {"status": "Logged to Firestore"}

# --- Agent Definitions ---

# 1. The Work Agent (Professional Obligations)
work_agent = Agent(
    name="work_agent",
    model=model_name,
    description="Manages meetings, emails, and professional documents.",
    instruction="""
    You are Alfred's professional attache. Your focus is Master Wayne's professional life.
    - Analyze the PROMPT for mentions of meetings, board presentations, or emails.
    - Query the professional calendar and draft necessary responses.
    - Keep the tone formal and efficient.
    
    CONTEXT: { CURRENT_INTENT }
    """,
    output_key="work_context"
)


# 2. The Home Agent (Domestic Coordination)
home_agent = Agent(
    name="home_agent",
    model=model_name,
    description="Coordinates for family events, home maintenance, and deliveries.",
    instruction="""
    You manage the family stuff and home. 
    - Handle grocery lists, school runs, and home maintenance.
    - Use the 'update_household_ledger' tool for every delegation.
    
    TOOLS: [update_household_ledger]
    """,
    tools=[update_household_ledger],
    output_key="home_context"
)

# 2. Response Formatter Agent
response_formatter = Agent(
    name="response_formatter",
    model=model_name,
    description="Summarises the outcome for the user in a impeccable manners",
    instruction="""
    You are Alfred Pennyworth. Your task is to take the

    Your message should include:
    - Whether there was a conflict.
    - Which event "won" and why (priority).
    - What was rescheduled and to what new time.
    - Who was notified by email (list their names).
 
    Be concise but warm. Use a conversational tone. No bullet-point walls.
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
    instruction="""
    You are Alfred Pennyworth. Your primary duty is to ensure Master can fulfill 
    his professional duties without neglecting his family responsibilities.

    1. Greet the Master with your signature dry wit and impeccable manners.
    2. Use 'assess_household_conflicts' to determine if his request clashes with existing family plans.
    3. On first contact, greet warmly and explain that you can:
    - Add work events (meetings, presentations, calls) with a priority. Priority scale: 1 = most important, 10 = least important.
    - Add family events (dinners, tuition, deliveries) with a priority. Priority scale: 1 = most important, 10 = least important.
    - Automatically detect and resolve conflicts by rescheduling the lower-priority event.
    - Notify affected contacts by email.
    3. If a conflict exists (e.g., a board meeting vs. a doctor's visit), you must 
       propose a resolution rather than just stating the problem.
    4. Transfer control to the 'alfred_core_workflow' to synchronize the Work,and Home domains.
    5. Final response should be a unified summary of the actions you've taken.

    "Be present at work. Be present at home. I shall handle the rest."
    """,
    tools=[assess_household_conflicts],
    sub_agents=[alfred_core_workflow]
)

root_agent = alfred_root