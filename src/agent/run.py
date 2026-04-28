"""Startup wrapper for the ADK web server.

Replaces `adk web` so we can inject Starlette's ProxyHeadersMiddleware and pass
forwarded_allow_ips="*" to Uvicorn.  Without this, Cloud Run's HTTPS proxy
causes Uvicorn to emit http:// URLs in 3xx redirects (mixed-content errors).
"""

import os
import uvicorn

from google.adk.cli.fast_api import get_fast_api_app

PORT = int(os.environ.get("PORT", "8080"))
CORS_ALLOW_ORIGINS = os.environ.get("CORS_ALLOW_ORIGINS", "*")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "alfred-492407")

allow_origins = ["*"] if CORS_ALLOW_ORIGINS == "*" else CORS_ALLOW_ORIGINS.split(",")

app = get_fast_api_app(
    agents_dir="/app/agents",
    session_service_uri=f"firestore://{GOOGLE_CLOUD_PROJECT}",
    allow_origins=allow_origins,
    web=True,
    host="0.0.0.0",
    port=PORT,
)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
