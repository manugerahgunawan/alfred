import os
import logging
import secrets
import json
import sys
from urllib.parse import urlencode
import requests as http_requests
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
from google.adk.cli.fast_api import get_fast_api_app
from dotenv import load_dotenv

# Make the parent directory importable so we can import the package module
current_file_dir = os.path.dirname(os.path.abspath(__file__))
parent_agents_dir = os.path.dirname(current_file_dir)
if parent_agents_dir not in sys.path:
    sys.path.insert(0, parent_agents_dir)

# Import the token context from the package module used by ADK
from alfred_agent.agent import (
    token_context,
    refresh_token_context,
    SESSION_ACCESS_TOKEN_KEY,
    SESSION_REFRESH_TOKEN_KEY,
    store_session_tokens,
)

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AlfredGatekeeper")

# --- Configuration ---
CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
PORT = int(os.getenv("PORT", 8080))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Dynamic redirect URI based on environment
if ENVIRONMENT == "production":
    APP_BASE_URL = os.getenv("APP_BASE_URL", "https://alfredagent-181562945855.asia-southeast1.run.app")
else:
    APP_BASE_URL = f"http://localhost:{PORT}"

REDIRECT_URI = f"{APP_BASE_URL}/auth/callback"

# OAuth2 scopes: identity + all Workspace APIs the MCP server needs
SCOPES = " ".join([
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
])

# --- HTML Templates ---

def make_login_html(error_msg: str = "") -> str:
    error_block = f'<div class="error">{error_msg}</div>' if error_msg else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Waine Enterprises | Alfred Access</title>
    <style>
        body {{
            background-color: #0d1117;
            color: #c9d1d9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }}
        .container {{
            text-align: center;
            padding: 3rem;
            background: #161b22;
            border-radius: 12px;
            border: 1px solid #30363d;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
            max-width: 400px;
            width: 90%;
        }}
        .bat-logo {{ font-size: 4rem; margin-bottom: 0.5rem; }}
        h1 {{
            font-weight: 200;
            letter-spacing: 4px;
            color: #58a6ff;
            margin: 0;
            text-transform: uppercase;
        }}
        .subtitle {{
            color: #8b949e;
            margin-bottom: 2.5rem;
            font-size: 0.9rem;
            letter-spacing: 1px;
        }}
        .login-btn {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            background: #ffffff;
            color: #3c4043;
            border: 1px solid #dadce0;
            border-radius: 4px;
            padding: 10px 24px;
            font-size: 14px;
            font-weight: 500;
            text-decoration: none;
            cursor: pointer;
            transition: background 0.2s, box-shadow 0.2s;
        }}
        .login-btn:hover {{
            background: #f8f8f8;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }}
        .login-btn svg {{ width: 18px; height: 18px; }}
        .error {{
            margin-bottom: 1rem;
            padding: 0.75rem;
            background: #2d1b1b;
            border: 1px solid #f85149;
            border-radius: 6px;
            color: #f85149;
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="bat-logo">🦇</div>
        <h1>ALFRED</h1>
        <div class="subtitle">SECURE GATEKEEPER v3.0</div>
        {error_block}
        <a class="login-btn" href="/auth/login">
            <svg viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.25 0 5.87 1.12 8.04 2.96l5.96-5.96C34.18 3.34 29.45 1.5 24 1.5 14.93 1.5 7.17 6.95 3.8 14.73l7.01 5.45C12.6 13.69 17.83 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24c0-1.55-.14-3.05-.38-4.5H24v9h12.7c-.55 2.96-2.2 5.47-4.67 7.16l7.15 5.57C43.6 37.23 46.5 31.03 46.5 24z"/><path fill="#FBBC05" d="M10.81 28.82A14.54 14.54 0 0 1 9.5 24c0-1.67.28-3.29.81-4.82L3.3 13.73A22.48 22.48 0 0 0 1.5 24c0 3.63.86 7.06 2.38 10.1l6.93-5.28z"/><path fill="#34A853" d="M24 46.5c5.35 0 9.85-1.77 13.13-4.81l-6.43-4.99c-1.79 1.21-4.09 1.93-6.7 1.93-6.17 0-11.4-4.19-13.19-9.82l-6.93 5.28C7.17 41.05 14.93 46.5 24 46.5z"/></svg>
            Sign in with Google
        </a>
        <p style="color:#484f58;font-size:0.75rem;margin-top:2rem;">
            Access restricted to authorized personnel.<br>
            Workspace access required.
        </p>
    </div>
</body>
</html>"""

# --- ADK App Initialization ---

logger.info(f"--- ALFRED GATEKEEPER STARTING ON PORT {PORT} ---")
logger.info(f"Redirect URI: {REDIRECT_URI}")

try:
    adk_app = get_fast_api_app(agents_dir=parent_agents_dir, web=True)
    logger.info("[Gatekeeper] ADK Application initialized successfully.")
except Exception as e:
    logger.error(f"[Gatekeeper CRITICAL] Failed to initialize ADK app: {e}")
    adk_app = FastAPI()

# Remove the default ADK root redirect so our login page takes over
adk_app.router.routes = [r for r in adk_app.router.routes if r.path != "/"]

# --- Gatekeeper Middleware ---
@adk_app.middleware("http")
async def gatekeeper_middleware(request: Request, call_next):
    # Public auth routes — always pass through
    if request.url.path in ["/", "/auth/login", "/auth/callback", "/favicon.ico"]:
        return await call_next(request)

    if request.url.path.startswith("/public/") or request.url.path.startswith("/gatekeeper-assets"):
        return await call_next(request)

    # Check for session token cookie
    token = request.cookies.get("alfred_token")
    refresh_token = request.cookies.get("alfred_refresh_token")
    if not token:
        logger.info(f"[Gatekeeper] Unauthorized: {request.url.path} → redirecting to /")
        return RedirectResponse(url="/")

    # Inject per-request OAuth2 access token into context
    token_reset = token_context.set(token)
    refresh_token_reset = refresh_token_context.set(refresh_token or "")
    try:
        path = request.url.path
        session_id = None
        app_name = ""
        user_id = ""
        if request.method == "POST" and (
            path in ["/run", "/run_sse", "/run_live"]
            or (path.startswith("/apps/") and "/sessions" in path)
        ):
            if path.startswith("/apps/") and "/sessions" in path:
                parts = [p for p in path.split("/") if p]
                app_name = parts[1] if len(parts) >= 2 else ""
                user_id = parts[3] if len(parts) >= 4 else ""
                if app_name and user_id:
                    store_session_tokens(
                        app_name,
                        user_id,
                        token,
                        refresh_token or "",
                    )
                    logger.info(
                        "[Gatekeeper] Stored auth tokens for %s/%s via route %s",
                        app_name,
                        user_id,
                        path,
                    )
            body = await request.body()
            if body:
                try:
                    payload = json.loads(body)
                    if isinstance(payload, dict):
                        if path in ["/run", "/run_sse", "/run_live"]:
                            app_name = str(payload.get("app_name", "")).strip()
                            user_id = str(payload.get("user_id", "")).strip()
                            session_id = str(payload.get("session_id", "")).strip()
                            state_delta = payload.get("state_delta") or {}
                            if not isinstance(state_delta, dict):
                                state_delta = {}
                            state_delta[SESSION_ACCESS_TOKEN_KEY] = token
                            if refresh_token:
                                state_delta[SESSION_REFRESH_TOKEN_KEY] = refresh_token
                            payload["state_delta"] = state_delta
                        elif "/sessions" in path:
                            parts = [p for p in path.split("/") if p]
                            app_name = parts[1] if len(parts) >= 2 else app_name
                            user_id = parts[3] if len(parts) >= 4 else user_id
                            session_id = str(payload.get("session_id", "")).strip()
                            if not session_id:
                                session_id = ""
                            state = payload.get("state") or {}
                            if not isinstance(state, dict):
                                state = {}
                            state[SESSION_ACCESS_TOKEN_KEY] = token
                            if refresh_token:
                                state[SESSION_REFRESH_TOKEN_KEY] = refresh_token
                            payload["state"] = state
                        if app_name and user_id:
                            store_session_tokens(
                                app_name,
                                user_id,
                                token,
                                refresh_token or "",
                                session_id=session_id,
                            )
                            logger.info(
                                "[Gatekeeper] Stored auth tokens for %s/%s via %s",
                                app_name,
                                user_id,
                                path,
                            )
                        else:
                            logger.info(
                                "[Gatekeeper] Could not derive app/user while handling %s",
                                path,
                            )
                        new_body = json.dumps(payload).encode("utf-8")

                        async def receive():
                            return {"type": "http.request", "body": new_body, "more_body": False}

                        request = Request(request.scope, receive)
                except Exception as e:
                    logger.warning(f"[Gatekeeper] Could not inject auth state into {path}: {e}")

        return await call_next(request)
    finally:
        refresh_token_context.reset(refresh_token_reset)
        token_context.reset(token_reset)

# --- Routes ---

@adk_app.get("/", response_class=HTMLResponse)
async def login_root(request: Request):
    if request.cookies.get("alfred_token"):
        return RedirectResponse(url="/dev-ui/")
    return HTMLResponse(make_login_html())

@adk_app.get("/auth/login")
async def auth_login():
    """Redirect user to Google's OAuth2 consent screen."""
    if not CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_OAUTH_CLIENT_ID not configured.")

    state = secrets.token_urlsafe(16)
    params = urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",   # request refresh_token too
        "prompt": "consent select_account",  # force a fresh grant and account choice
        "state": state,
    })
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    logger.info(f"[Gatekeeper] Redirecting to Google OAuth2 consent screen")
    return RedirectResponse(url=google_auth_url)

@adk_app.get("/auth/callback")
async def auth_callback(request: Request, response: Response, code: str = None, error: str = None, state: str = None):
    """Exchange the authorization code for an access token and create a session."""
    if error:
        logger.warning(f"[Gatekeeper] OAuth2 error: {error}")
        return HTMLResponse(make_login_html(error_msg=f"Login failed: {error}"))

    if not code:
        return HTMLResponse(make_login_html(error_msg="No authorization code received."))

    if not CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GOOGLE_OAUTH_CLIENT_SECRET not configured.")

    # Exchange authorization code → access token
    try:
        token_response = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_data = token_response.json()
    except Exception as e:
        logger.error(f"[Gatekeeper] Token exchange failed: {e}")
        return HTMLResponse(make_login_html(error_msg="Failed to exchange authorization code."))

    if "error" in token_data:
        err = token_data.get("error_description", token_data["error"])
        logger.error(f"[Gatekeeper] Token exchange error: {err}")
        return HTMLResponse(make_login_html(error_msg=f"Authentication error: {err}"))

    access_token = token_data.get("access_token")
    if not access_token:
        return HTMLResponse(make_login_html(error_msg="No access token in response."))
    refresh_token = token_data.get("refresh_token")

    logger.info("[Gatekeeper] OAuth2 access token obtained successfully.")

    # Set the access token as the session cookie
    # httponly=True: JS cannot read it (XSS protection)
    # The token is used by DynamicHeaders to authenticate MCP calls
    redirect = RedirectResponse(url="/dev-ui/", status_code=302)
    redirect.set_cookie(
        key="alfred_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=ENVIRONMENT == "production",
        max_age=3600,  # 1 hour (access tokens typically expire in 1h)
    )
    if refresh_token:
        redirect.set_cookie(
            key="alfred_refresh_token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
            secure=ENVIRONMENT == "production",
            max_age=60 * 60 * 24 * 90,
        )
    else:
        logger.warning("[Gatekeeper] No refresh token returned from Google OAuth.")
    return redirect

@adk_app.get("/auth/logout")
@adk_app.post("/auth/logout")
async def logout():
    """Clear the session cookie and redirect to login."""
    redirect = RedirectResponse(url="/", status_code=302)
    redirect.delete_cookie("alfred_token")
    redirect.delete_cookie("alfred_refresh_token")
    return redirect

if __name__ == "__main__":
    logger.info(f"Starting Alfred Gatekeeper")
    logger.info(f"RedirectURI: {REDIRECT_URI}")
    logger.info(f"Serving agents from: {parent_agents_dir}")
    uvicorn.run(adk_app, host="0.0.0.0", port=PORT, log_level="info")
