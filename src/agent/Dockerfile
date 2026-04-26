FROM python:3.11-slim
WORKDIR /app

# Create a non-root user
RUN adduser --disabled-password --gecos "" myuser
USER myuser
ENV PATH="/home/myuser/.local/bin:$PATH"

# GCP / Vertex AI env vars
ENV GOOGLE_GENAI_USE_VERTEXAI=1

# Install ADK + agent deps
COPY --chown=myuser:myuser alfred_agent/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir google-adk==1.27.2 \
	&& pip install --no-cache-dir -r /tmp/requirements.txt

# Copy services.py and firestore_session_service.py to the agents root
COPY --chown=myuser:myuser services.py /app/agents/services.py
COPY --chown=myuser:myuser firestore_session_service.py /app/agents/firestore_session_service.py

# Copy the agent package
COPY --chown=myuser:myuser alfred_agent/ /app/agents/alfred_agent/

EXPOSE 8080

# Run ADK web server with Firestore session persistence
# Cloud Run injects PORT env var (default 8000); we must listen on it
# CORS_ALLOW_ORIGINS should be set to your frontend URL, e.g.
# https://alfred-frontend-xxxxx-uc.a.run.app
CMD adk web \
	--port=${PORT:-8080} \
	--host=0.0.0.0 \
	--allow_origins=${CORS_ALLOW_ORIGINS:-http://localhost:3000} \
	--session_service_uri=firestore://${GOOGLE_CLOUD_PROJECT:-alfred-492407} \
	"/app/agents"
