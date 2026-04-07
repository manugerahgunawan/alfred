
 To Deploy the MCP Server 
 gcloud run deploy workspace-mcp   --image asia-southeast2-docker.pkg.dev/alfred-492407/mcp-repo/workspace-mcp:v1   --region asia-southeast2   --platform managed   --allow-unauthenticated   --port 8080   --service-account mcp-runner@alfred-492407.iam.gserviceaccount.com   --set-env-vars MCP_ENABLE_OAUTH21=true,EXTERNAL_OAUTH21_PROVIDER=true,OAUTHLIB_INSECURE_TRANSPORT=1,WORKSPACE_EXTERNAL_URL=https://workspace-mcp-181562945855.asia-southeast2.run.app   --set-secrets="GOOGLE_OAUTH_CLIENT_ID=GOOGLE_OAUTH_CLIENT_ID:latest,GOOGLE_OAUTH_CLIENT_SECRET=GOOGLE_OAUTH_CLIENT_SECRET:latest,GOOGLE_OAUTH_REDIRECT_URI=GOOGLE_OAUTH_REDIRECT_URI:latest"


============Dockerfile============
 # Use a lightweight Python image
FROM python:3.12-slim

WORKDIR /app

# 1. NEW: Install git so pip can clone the GitHub repository
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# 2. NEW: JSON array format to fix the warning. 
# We use 'sh -c' so Cloud Run's $PORT environment variable still gets processed!
CMD ["sh", "-c", "workspace-mcp --transport streamable-http --tools contacts gmail calendar"]

=========Requirements============  
# Other dependencies
python-dotenv
mcp

# Google Workspace MCP via GitHub
workspace-mcp @ git+https://github.com/taylorwilsdon/google_workspace_mcp.git

