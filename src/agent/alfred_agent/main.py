"""Cloud Run entrypoint with Firestore session persistence.

Uses ADK's service registry (via ../services.py) to resolve the
firestore:// session URI. This file is only needed for custom deployments
that don't use `adk deploy cloud_run`.
"""

import os

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

# agents_dir = parent directory containing the alfred_agent package
AGENTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "alfred-492407")
SESSION_URI = f"firestore://{PROJECT}"

app = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    session_service_uri=SESSION_URI,
    allow_origins=["*"],
    web=True,
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
