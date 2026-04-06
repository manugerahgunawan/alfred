# Google Workspace MCP Server Deployment Guide

> [!NOTE]
> This service is currently **deployed and running correctly**. This documentation is for reference only or for future infrastructure updates. New team members should refer to the [ADK Agent Guide](./adk_agent_guide.md) for integration.

## Building the Image

To build and push the MCP server image to Google Artifact Registry:

```bash
gcloud builds submit --tag asia-southeast2-docker.pkg.dev/alfred-492407/mcp-repo/workspace-mcp:v1
```

## Cloud Run Deployment

Use the following command to deploy or update the service. Replace secret names if they differ in your GCP project.

```bash
gcloud run deploy workspace-mcp \
  --image asia-southeast2-docker.pkg.dev/alfred-492407/mcp-repo/workspace-mcp:v1 \
  --region asia-southeast2 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --service-account mcp-runner@alfred-492407.iam.gserviceaccount.com \
  --set-env-vars MCP_ENABLE_OAUTH21=true,EXTERNAL_OAUTH21_PROVIDER=true,OAUTHLIB_INSECURE_TRANSPORT=1,WORKSPACE_EXTERNAL_URL=https://workspace-mcp-181562945855.asia-southeast2.run.app \
  --set-secrets="GOOGLE_OAUTH_CLIENT_ID=GOOGLE_OAUTH_CLIENT_ID:latest,GOOGLE_OAUTH_CLIENT_SECRET=GOOGLE_OAUTH_CLIENT_SECRET:latest,GOOGLE_OAUTH_REDIRECT_URI=GOOGLE_OAUTH_REDIRECT_URI:latest"
```

## Server Configuration

### Dockerfile

The server uses a lightweight Python 3.12 image. It must install `git` to pull the `workspace-mcp` package directly from GitHub.

```dockerfile
# Use a lightweight Python image
FROM python:3.12-slim

WORKDIR /app

# Install git so pip can clone the GitHub repository
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Start the server using Streamable HTTP transport
# We use 'sh -c' so Cloud Run's $PORT environment variable still gets processed!
CMD ["sh", "-c", "workspace-mcp --transport streamable-http --tools contacts gmail calendar"]
```

### requirements.txt

The server relies on the `google_workspace_mcp` package and its dependencies.

```text
# General dependencies
python-dotenv
mcp

# Google Workspace MCP via GitHub
workspace-mcp @ git+https://github.com/taylorwilsdon/google_workspace_mcp.git
```
