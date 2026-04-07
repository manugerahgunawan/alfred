import os
import webbrowser
import httpx
import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# Load your existing .env values
load_dotenv()

# --- Configuration ---
CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "181562945855-npgr2d40ck14059q6lbcj4kdt1tj36pn.apps.googleusercontent.com")
CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "YOUR_SECRET_HERE")
REDIRECT_URI = "http://localhost:8080" # Add this to your Authorized Redirect URIs in GCP Console!
SCOPES = [
    # Identity scopes (REQUIRED for server to validate who you are)
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    # App scopes
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts"
]

class OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        if "code" in query:
            self.server.auth_code = query["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Success! You can close this tab and return to the terminal.")
        else:
            self.send_response(400)
            self.end_headers()

async def get_token():
    if CLIENT_SECRET == "YOUR_SECRET_HERE":
        print("Error: GOOGLE_OAUTH_CLIENT_SECRET is missing. Check your .env file.")
        return

    # 1. Start a local server to catch the redirect
    server = HTTPServer(("localhost", 8080), OAuthHandler)
    server.auth_code = None
    
    # 2. Build the Auth URL
    from urllib.parse import quote
    scope_str = quote(" ".join(SCOPES))
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"response_type=code&"
        f"scope={scope_str}&"
        f"access_type=offline&"
        f"prompt=consent"
    )

    print(f"\n1. Opening browser for authorization...")
    webbrowser.open(auth_url)
    
    # 3. Wait for the redirect
    print("\n2. Waiting for you to authorize in the browser...")
    while not server.auth_code:
        server.handle_request()
    
    print(f"\n3. Exchanging code for token...")
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": server.auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)
        if response.status_code != 200:
            print(f"Error: {response.status_code} {response.text}")
            return
        
        tokens = response.json()
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        
        print("\n--- DONE! ---")
        print(f"Access Token: {access_token[:20]}...")
        if refresh_token:
            print(f"Refresh Token: {refresh_token[:10]}...")
        
        # 4. Save to .env (Smartly finding root)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(os.path.dirname(script_dir))
        
        target_env = os.path.join(root_dir, ".env")
        if not os.path.exists(target_env):
            target_env = os.path.join(script_dir, ".env")

        # Read existing lines (strip trailing whitespace to normalize)
        lines = []
        if os.path.exists(target_env):
            with open(target_env, "r") as f:
                lines = f.readlines()
        
        # Filter out old GOOGLE_ACCESS_TOKEN lines
        lines = [line for line in lines if not line.startswith("GOOGLE_ACCESS_TOKEN=")]
        
        # Ensure the file ends with a newline before adding the new token
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + "\n"
        
        # Add new token
        lines.append(f"GOOGLE_ACCESS_TOKEN={access_token}\n")

        with open(target_env, "w", newline="\n") as f:
            f.writelines(lines)
        
        print(f"\nUpdated {target_env} with GOOGLE_ACCESS_TOKEN.")

if __name__ == "__main__":
    asyncio.run(get_token())
