"""Custom service registration for ADK.

This file is auto-loaded by ADK's load_services_module() at startup.
It registers the 'firestore://' URI scheme so that
  --session_service_uri firestore://<project-id>
works with `adk web`, `adk api_server`, and Cloud Run deployments.
"""

from urllib.parse import urlparse

from google.adk.cli.service_registry import get_service_registry


def _create_firestore_session_service(uri: str, **kwargs):
    """Factory that creates a FirestoreSessionService from a firestore:// URI."""
    from firestore_session_service import FirestoreSessionService

    parsed = urlparse(uri)
    project = parsed.hostname  # firestore://project-id  → project-id
    return FirestoreSessionService(project=project)


registry = get_service_registry()
registry.register_session_service("firestore", _create_firestore_session_service)
