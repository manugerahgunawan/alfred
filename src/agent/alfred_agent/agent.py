import functools
import importlib
import logging
import os
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from datetime import timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

import google.cloud.logging
import requests
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.auth.auth_credential import (
    AuthCredential,
    AuthCredentialTypes,
    HttpAuth,
    HttpCredentials,
)
from fastapi.openapi.models import HTTPBearer
from google.adk.auth.credential_service.base_credential_service import (
    BaseCredentialService,
)
from google.adk.tools.mcp_tool.mcp_tool import MCPTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.tool_context import ToolContext
from google.cloud import firestore
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials as GoogleOAuthCredentials
from google.genai.types import FunctionDeclaration

from mcp_google_client import MCPGoogleClient

# --- Per-Request Authentication Context ---
# This ensures that each user has their own isolated session and token.
token_context: ContextVar[str] = ContextVar("token_context", default="")
refresh_token_context: ContextVar[str] = ContextVar(
    "refresh_token_context", default=""
)
SESSION_ACCESS_TOKEN_KEY = "ALFRED_ACCESS_TOKEN"
SESSION_REFRESH_TOKEN_KEY = "ALFRED_REFRESH_TOKEN"
SESSION_TOKEN_EXPIRES_AT_KEY = "ALFRED_TOKEN_EXPIRES_AT"
SESSION_TIMEZONE_KEY = "ALFRED_TIMEZONE"
SESSION_LOCALE_KEY = "ALFRED_LOCALE"
SESSION_TOKEN_STORE: dict[str, dict[str, Any]] = {}
DEFAULT_APP_NAME = os.getenv("ADK_APP_NAME", "alfred_agent")
DEFAULT_USER_ID = os.getenv("ADK_USER_ID", "user")
PRODUCTION_APP_ALIAS = os.getenv("ADK_RUNTIME_APP_NAME", "workspace")
AUTH_TOKEN_ROOT = "adk_auth_tokens"
GENERIC_CALENDAR_QUERY_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "calendar",
    "check",
    "events",
    "event",
    "for",
    "from",
    "in",
    "is",
    "my",
    "next",
    "of",
    "on",
    "please",
    "professional",
    "schedule",
    "schedules",
    "show",
    "the",
    "this",
    "time",
    "today",
    "tomorrow",
    "upcoming",
    "week",
    "what",
    "work",
    "workevents",
    "working",
    "your",
    "with",
    "1",
    "one",
    "2",
    "2nd",
    "3",
    "3rd",
    "7",
    "7th",
    "days",
    "day",
    "week",
}


def _token_store_key(app_name: str, user_id: str) -> str:
    return f"{app_name}:{user_id}"


def _debug_trace(message: str) -> None:
    print(message, flush=True)
    logging.warning(message)


def _normalize_mcp_schema_tree(schema: Any) -> Any:
    primitive_types = {
        "string",
        "number",
        "integer",
        "boolean",
        "object",
        "array",
        "null",
    }

    def _is_null_schema(node: Any) -> bool:
        return isinstance(node, dict) and str(node.get("type", "")).lower() == "null"

    def _normalize_type_value(value: Any) -> str:
        if isinstance(value, str):
            lowered = value.strip().lower()
            return lowered if lowered in primitive_types else "object"

        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    lowered = item.strip().lower()
                    if lowered in primitive_types and lowered != "null":
                        return lowered
            for item in value:
                if isinstance(item, str):
                    lowered = item.strip().lower()
                    if lowered in primitive_types:
                        return lowered
            return "object"

        if isinstance(value, dict):
            nested_type = value.get("type")
            if nested_type is not None:
                return _normalize_type_value(nested_type)
            if "properties" in value:
                return "object"
            if "items" in value:
                return "array"
            return "object"

        return "object"

    def _pick_branch(branch_value: Any) -> Any:
        branches = branch_value if isinstance(branch_value, list) else [branch_value]
        normalized_branches = [_normalize_mcp_schema_tree(item) for item in branches]
        for branch in normalized_branches:
            if not _is_null_schema(branch):
                return branch
        return normalized_branches[0] if normalized_branches else {}

    if isinstance(schema, list):
        return [_normalize_mcp_schema_tree(item) for item in schema]

    if isinstance(schema, dict):
        for branch_key in ("anyOf", "oneOf", "allOf"):
            if branch_key in schema:
                return _pick_branch(schema[branch_key])

        if "not" in schema:
            branch_value = schema["not"]
            if isinstance(branch_value, dict):
                return _normalize_mcp_schema_tree(branch_value)
            return {}

        normalized: dict[str, Any] = {}

        for key, value in schema.items():
            if key in {"anyOf", "oneOf", "allOf", "not"}:
                continue

            if key == "type":
                normalized[key] = _normalize_type_value(value)
                continue

            if key in {"properties", "items", "additionalProperties"}:
                if isinstance(value, dict):
                    normalized[key] = {
                        sub_key: _normalize_mcp_schema_tree(sub_value)
                        for sub_key, sub_value in value.items()
                    }
                elif isinstance(value, list):
                    normalized[key] = [_normalize_mcp_schema_tree(item) for item in value]
                else:
                    if key == "additionalProperties" and isinstance(value, bool):
                        normalized[key] = value
                continue

            if key == "required" and isinstance(value, list):
                normalized[key] = [str(item) for item in value if isinstance(item, str)]
                continue

            if key == "enum" and isinstance(value, list):
                normalized[key] = [
                    item
                    for item in value
                    if isinstance(item, (str, int, float, bool)) or item is None
                ]
                continue

            if isinstance(value, dict):
                normalized[key] = _normalize_mcp_schema_tree(value)
                continue

            if isinstance(value, list):
                normalized[key] = [_normalize_mcp_schema_tree(item) for item in value]
                continue

            normalized[key] = value

        if "type" not in normalized or not normalized["type"]:
            if "properties" in normalized or "required" in normalized:
                normalized["type"] = "object"
            elif "items" in normalized:
                normalized["type"] = "array"
            else:
                normalized["type"] = "object"

        return normalized

    if isinstance(schema, str):
        schema_type = schema.strip().lower()
        if schema_type in primitive_types:
            return schema_type
        return schema

    if isinstance(schema, (int, float, bool)):
        return schema

    return schema


def _install_mcp_schema_normalizer() -> None:
    try:
        gemini_schema_util = importlib.import_module(
            "google.adk.tools._gemini_schema_util"
        )
        mcp_tool_module = importlib.import_module(
            "google.adk.tools.mcp_tool.mcp_tool"
        )
        original_to_gemini_schema = gemini_schema_util._to_gemini_schema

        def _patched_to_gemini_schema(openapi_schema: dict[str, Any]):
            normalized_schema = _normalize_mcp_schema_tree(openapi_schema)
            return original_to_gemini_schema(normalized_schema)

        gemini_schema_util._to_gemini_schema = _patched_to_gemini_schema
        mcp_tool_module._to_gemini_schema = _patched_to_gemini_schema
        _debug_trace("[Config] Installed MCP schema normalizer")
    except Exception as exc:
        logging.warning(f"[Config] Could not install MCP schema normalizer: {exc}")


def _install_mcp_native_json_schema_patch() -> None:
    try:
        mcp_tool_module = importlib.import_module(
            "google.adk.tools.mcp_tool.mcp_tool"
        )
        original_get_declaration = mcp_tool_module.McpTool._get_declaration

        def _patched_get_declaration(self) -> FunctionDeclaration:
            schema_dict = getattr(self._mcp_tool, "inputSchema", {}) or {}
            if isinstance(schema_dict, dict):
                _debug_trace(
                    f"[Config] Using native MCP JSON schema for tool={getattr(self, 'name', '<unknown>')}"
                )
                return FunctionDeclaration(
                    name=self.name,
                    description=self.description,
                    parameters_json_schema=schema_dict,
                )
            return original_get_declaration(self)

        mcp_tool_module.McpTool._get_declaration = _patched_get_declaration
        mcp_tool_module.MCPTool._get_declaration = _patched_get_declaration
        _debug_trace("[Config] Installed native MCP JSON schema patch")
    except Exception as exc:
        logging.warning(f"[Config] Could not install native MCP JSON schema patch: {exc}")


def _token_store_key_candidates(app_name: str = "", user_id: str = "") -> list[str]:
    candidates: list[str] = []
    for candidate_app in [
        app_name,
        DEFAULT_APP_NAME,
        PRODUCTION_APP_ALIAS,
    ]:
        candidate_app = str(candidate_app or "").strip()
        candidate_user = str(user_id or "").strip()
        if candidate_app and candidate_user:
            key = _token_store_key(candidate_app, candidate_user)
            if key not in candidates:
                candidates.append(key)
    return candidates


def _auth_token_doc_ref(app_name: str, user_id: str):
    db = get_db()
    if db is None:
        return None
    return (
        db.collection(AUTH_TOKEN_ROOT)
        .document(app_name)
        .collection("users")
        .document(user_id)
        .collection("tokens")
        .document("current")
    )


def _record_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    access_token = str(payload.get(SESSION_ACCESS_TOKEN_KEY, "")).strip()
    if not access_token:
        return {}
    record[SESSION_ACCESS_TOKEN_KEY] = access_token
    refresh_token = str(payload.get(SESSION_REFRESH_TOKEN_KEY, "")).strip()
    if refresh_token:
        record[SESSION_REFRESH_TOKEN_KEY] = refresh_token
    expires_at = _normalize_int(payload.get(SESSION_TOKEN_EXPIRES_AT_KEY))
    if expires_at is not None:
        record[SESSION_TOKEN_EXPIRES_AT_KEY] = expires_at
    timezone_name = str(payload.get(SESSION_TIMEZONE_KEY, "")).strip()
    if timezone_name:
        record[SESSION_TIMEZONE_KEY] = timezone_name
    locale_name = str(payload.get(SESSION_LOCALE_KEY, "")).strip()
    if locale_name:
        record[SESSION_LOCALE_KEY] = locale_name
    return record


def _refresh_token_record(
    app_name: str,
    user_id: str,
    session_id: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    access_token = str(record.get(SESSION_ACCESS_TOKEN_KEY, "")).strip()
    refresh_token = str(record.get(SESSION_REFRESH_TOKEN_KEY, "")).strip()
    if not refresh_token:
        return record

    client_id = str(os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")).strip()
    client_secret = str(os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")).strip()
    token_uri = os.getenv("GOOGLE_OAUTH_TOKEN_URI", "https://oauth2.googleapis.com/token")
    if not client_id or not client_secret:
        return record

    try:
        credentials = GoogleOAuthCredentials(
            token=access_token or None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=WORKSPACE_SCOPES,
        )
        credentials.refresh(GoogleAuthRequest())
        new_access_token = str(credentials.token or "").strip()
        if not new_access_token:
            return record

        refreshed_record = dict(record)
        refreshed_record[SESSION_ACCESS_TOKEN_KEY] = new_access_token
        refreshed_record[SESSION_REFRESH_TOKEN_KEY] = refresh_token
        if credentials.expiry is not None:
            refreshed_record[SESSION_TOKEN_EXPIRES_AT_KEY] = int(credentials.expiry.timestamp())
        if record.get(SESSION_TIMEZONE_KEY):
            refreshed_record[SESSION_TIMEZONE_KEY] = str(record.get(SESSION_TIMEZONE_KEY, "")).strip()
        if record.get(SESSION_LOCALE_KEY):
            refreshed_record[SESSION_LOCALE_KEY] = str(record.get(SESSION_LOCALE_KEY, "")).strip()

        if app_name and user_id:
            store_key = _token_store_key(app_name, user_id)
            SESSION_TOKEN_STORE[store_key] = dict(refreshed_record)
            if session_id:
                SESSION_TOKEN_STORE[session_id] = dict(refreshed_record)
            _persist_token_record(app_name, user_id, refreshed_record)
            for alias_key in _token_store_key_candidates(app_name, user_id):
                alias_app, alias_user = alias_key.split(":", 1)
                SESSION_TOKEN_STORE[alias_key] = dict(refreshed_record)
                _persist_token_record(alias_app, alias_user, refreshed_record)

        _debug_trace(
            f"[Auth] Refreshed access token app={app_name or '<missing>'} user={user_id or '<missing>'} session={session_id or '<missing>'} expires_at={refreshed_record.get(SESSION_TOKEN_EXPIRES_AT_KEY, '<missing>')}"
        )
        return refreshed_record
    except Exception as exc:
        _debug_trace(
            f"[Auth] Failed to refresh access token app={app_name or '<missing>'} user={user_id or '<missing>'} session={session_id or '<missing>'} err={exc}"
        )
        return record


def _persist_token_record(app_name: str, user_id: str, payload: dict[str, Any]) -> None:
    if not app_name or not user_id or not payload:
        return
    doc_ref = _auth_token_doc_ref(app_name, user_id)
    if doc_ref is None:
        return
    try:
        doc_ref.set({"payload": payload, "updated_at": time.time()})
        _debug_trace(f"[Auth] Persisted token record to Firestore app={app_name} user={user_id}")
    except Exception as exc:
        _debug_trace(
            f"[Auth] Failed to persist token record to Firestore app={app_name} user={user_id} err={exc}"
        )


def _load_persisted_token_record(app_name: str, user_id: str) -> dict[str, Any]:
    if not app_name or not user_id:
        return {}
    doc_ref = _auth_token_doc_ref(app_name, user_id)
    if doc_ref is None:
        return {}
    try:
        doc = doc_ref.get()
        if not doc.exists:
            return {}
        data = doc.to_dict() or {}
        payload = data.get("payload") or {}
        if not isinstance(payload, dict):
            return {}
        record = _record_from_payload(payload)
        if record:
            _debug_trace(
                f"[Auth] Loaded persisted token record app={app_name} user={user_id} keys={list(record.keys())}"
            )
        return record
    except Exception as exc:
        _debug_trace(
            f"[Auth] Failed to load persisted token record app={app_name} user={user_id} err={exc}"
        )
        return {}


load_dotenv()

# --- Lazy GCP Client Initialization ---
# These MUST be lazy to prevent blocking the server startup during import.
# Cloud Run health checks fail when module-level network calls hang.
_db = None
_cloud_logging_initialized = False


def get_db():
    """Returns a Firestore client, initializing lazily on first use."""
    global _db
    if _db is None:
        try:
            _db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "alfred-492407"))
        except Exception as e:
            logging.warning(f"[Firestore] Could not initialize client: {e}")
    return _db


def setup_cloud_logging():
    """Configures Cloud Logging lazily on first use."""
    global _cloud_logging_initialized
    if not _cloud_logging_initialized:
        try:
            client = google.cloud.logging.Client()
            client.setup_logging()
            _cloud_logging_initialized = True
        except Exception as e:
            logging.warning(f"[Logging] Could not initialize Cloud Logging: {e}")


# Get today's date for temporal context (timezone-aware)
_agent_tz = ZoneInfo(os.getenv("TIMEZONE", "Asia/Bangkok"))
now = datetime.now(_agent_tz)
today_str = now.strftime("%A, %B %d, %Y")
today_iso = now.strftime("%Y-%m-%d")
raw_tz = now.strftime("%z")
tz_str = f"{raw_tz[:3]}:{raw_tz[3:]}"  # Convert +0700 to +07:00

model_name = os.getenv("MODEL")
MCP_URL = os.getenv("MCP_URL", "").strip('"\'')
ACCESS_TOKEN = os.getenv("GOOGLE_ACCESS_TOKEN", "").strip('"\'')

WORKSPACE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/contacts",
]

logging.info(f"[Config] MCP_URL: {MCP_URL}")
if ACCESS_TOKEN:
    logging.info(f"[Config] Local GOOGLE_ACCESS_TOKEN found (len: {len(ACCESS_TOKEN)})")


@functools.lru_cache(maxsize=128)
def get_user_email(token: str) -> str:
    """Fetches the user's email from Google to use as a unique ID."""
    if not token:
        token = token_context.get()
        if not token:
            token = os.getenv("GOOGLE_ACCESS_TOKEN", "")

    if not token:
        return "anonymous_household"

    try:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if response.status_code == 200:
            return response.json().get("email", "anonymous_household")
    except Exception as e:
        logging.warning(f"[Identity] Failed to fetch user info: {e}")
    return "anonymous_household"


def _normalize_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _should_apply_calendar_query(person: str) -> bool:
    text = " ".join(str(person or "").lower().split())
    if not text:
        return False

    tokens = [token for token in text.replace("-", " ").split() if token]
    if not tokens:
        return False

    return any(
        token not in GENERIC_CALENDAR_QUERY_WORDS and not token.isdigit()
        for token in tokens
    )


def _extract_calendar_items(payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            summary = str(value.get("summary") or value.get("title") or "").strip()
            start = value.get("start")
            end = value.get("end")
            description = str(value.get("description") or "").strip()
            if summary and (start is not None or end is not None):
                items.append(value)
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(payload)
    return items


def _calendar_event_label(event: dict[str, Any]) -> str:
    title = str(event.get("summary") or event.get("title") or "Untitled event").strip()
    description = str(event.get("description") or "").strip()

    start_value = event.get("start")
    end_value = event.get("end")

    def _extract_time(value: Any) -> str:
        if isinstance(value, dict):
            return str(
                value.get("dateTime")
                or value.get("date")
                or value.get("time")
                or ""
            ).strip()
        return str(value or "").strip()

    start_text = _extract_time(start_value)
    end_text = _extract_time(end_value)

    time_text = ""
    if start_text and end_text:
        time_text = f"{start_text} to {end_text}"
    elif start_text:
        time_text = start_text

    label = title
    if time_text:
        label = f"{label} ({time_text})"
    if description:
        label = f'{label} - {description}'
    return label


def _get_token_record(
    app_name: str = "",
    user_id: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    record: dict[str, Any] = {}
    tried_keys: list[str] = []
    if app_name and user_id:
        key = _token_store_key(app_name, user_id)
        tried_keys.append(key)
        record = SESSION_TOKEN_STORE.get(key, {})
    if not record:
        for key in _token_store_key_candidates(app_name, user_id):
            if key in tried_keys:
                continue
            tried_keys.append(key)
            record = SESSION_TOKEN_STORE.get(key, {})
            if record:
                break
    if not record and session_id:
        record = SESSION_TOKEN_STORE.get(session_id, {})
    if not record:
        for key in _token_store_key_candidates(app_name, user_id):
            try:
                persisted = _load_persisted_token_record(*key.split(":", 1))
            except Exception:
                persisted = {}
            if persisted:
                record = persisted
                SESSION_TOKEN_STORE[key] = dict(persisted)
                _debug_trace(f"[Auth] Hydrated token record from Firestore key={key}")
                break
    if not record:
        record = SESSION_TOKEN_STORE.get(
            _token_store_key(DEFAULT_APP_NAME, DEFAULT_USER_ID), {}
        )
    if record:
        _debug_trace(
            f"[Auth] Token record lookup app={app_name or '<missing>'} user={user_id or '<missing>'} session={session_id or '<missing>'} tried={tried_keys} hit={bool(record)}"
        )
    else:
        _debug_trace(
            f"[Auth] Token record lookup app={app_name or '<missing>'} user={user_id or '<missing>'} session={session_id or '<missing>'} tried={tried_keys} hit=False"
        )
    return record


def _token_record_from_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}

    access_token = str(state.get(SESSION_ACCESS_TOKEN_KEY, "")).strip()
    if not access_token:
        return {}

    record: dict[str, Any] = {
        SESSION_ACCESS_TOKEN_KEY: access_token,
        SESSION_REFRESH_TOKEN_KEY: str(state.get(SESSION_REFRESH_TOKEN_KEY, "")).strip(),
    }

    expires_at = _normalize_int(state.get(SESSION_TOKEN_EXPIRES_AT_KEY))
    if expires_at is not None:
        record[SESSION_TOKEN_EXPIRES_AT_KEY] = expires_at

    timezone_name = str(state.get(SESSION_TIMEZONE_KEY, "")).strip()
    if timezone_name:
        record[SESSION_TIMEZONE_KEY] = timezone_name

    locale_name = str(state.get(SESSION_LOCALE_KEY, "")).strip()
    if locale_name:
        record[SESSION_LOCALE_KEY] = locale_name

    return record


def _resolve_timezone_name(tool_context: ToolContext) -> str:
    invocation_context = getattr(tool_context, "_invocation_context", None)
    session = getattr(invocation_context, "session", None) if invocation_context else None
    if session is not None:
        session_state = getattr(session, "state", {}) or {}
        timezone_name = str(session_state.get(SESSION_TIMEZONE_KEY, "")).strip()
        if timezone_name:
            return timezone_name

    try:
        state_timezone = str(tool_context.state.get(SESSION_TIMEZONE_KEY, "")).strip()
        if state_timezone:
            return state_timezone
    except Exception:
        pass

    return os.getenv("TIMEZONE", "Asia/Bangkok")


def _resolve_access_token(tool_context: ToolContext) -> str:
    invocation_context = getattr(tool_context, "_invocation_context", None)
    session = getattr(invocation_context, "session", None) if invocation_context else None
    session_id = getattr(session, "id", "") if session is not None else ""
    app_name = getattr(invocation_context, "app_name", "") if invocation_context else ""
    user_id = getattr(invocation_context, "user_id", "") if invocation_context else ""

    record = _get_token_record(app_name, user_id, session_id)
    if record:
        record = _refresh_token_record(app_name, user_id, session_id, record)
    access_token = str(record.get(SESSION_ACCESS_TOKEN_KEY, "")).strip()
    if access_token:
        return access_token

    try:
        state_token = str(tool_context.state.get(SESSION_ACCESS_TOKEN_KEY, "")).strip()
        if state_token:
            return state_token
    except Exception:
        pass

    state_token = token_context.get().strip()
    if state_token:
        return state_token

    return ACCESS_TOKEN


def _build_bearer_credential(
    access_token: str,
    refresh_token: str = "",
    expires_at: Optional[int] = None,
) -> AuthCredential:
    return AuthCredential(
        auth_type=AuthCredentialTypes.HTTP,
        http=HttpAuth(
            scheme="bearer",
            credentials=HttpCredentials(token=access_token or None),
        ),
    )


_install_mcp_schema_normalizer()
_install_mcp_native_json_schema_patch()


class SessionAwareCredentialService(BaseCredentialService):
    """Credential service that resolves Google credentials from Alfred sessions."""

    async def load_credential(self, auth_config, callback_context):
        invocation_context = getattr(callback_context, "_invocation_context", None)
        app_name = getattr(invocation_context, "app_name", "") if invocation_context else ""
        user_id = getattr(invocation_context, "user_id", "") if invocation_context else ""
        session = getattr(invocation_context, "session", None) if invocation_context else None
        session_id = getattr(session, "id", "") if session is not None else ""
        session_state = getattr(session, "state", {}) if session is not None else {}

        record = _get_token_record(app_name, user_id, session_id)
        if not record:
            record = _token_record_from_state(session_state)
        if not record:
            return None
        record = _refresh_token_record(app_name, user_id, session_id, record)

        access_token = str(record.get(SESSION_ACCESS_TOKEN_KEY, "")).strip()
        if not access_token:
            return None

        refresh_token = str(record.get(SESSION_REFRESH_TOKEN_KEY, "")).strip()
        expires_at = _normalize_int(record.get(SESSION_TOKEN_EXPIRES_AT_KEY))

        logging.info(
            "[CredentialService] Loaded token for app=%s user=%s session=%s",
            app_name or "<missing>",
            user_id or "<missing>",
            session_id or "<missing>",
        )
        return _build_bearer_credential(access_token, refresh_token, expires_at)

    async def save_credential(self, auth_config, callback_context) -> None:
        invocation_context = getattr(callback_context, "_invocation_context", None)
        app_name = getattr(invocation_context, "app_name", "") if invocation_context else ""
        user_id = getattr(invocation_context, "user_id", "") if invocation_context else ""
        session = getattr(invocation_context, "session", None) if invocation_context else None
        session_id = getattr(session, "id", "") if session is not None else ""

        credential = getattr(auth_config, "exchanged_auth_credential", None)
        if not credential:
            return

        access_token = ""
        refresh_token = ""
        expires_at = None
        if credential.http and credential.http.credentials.token:
            access_token = str(credential.http.credentials.token or "").strip()
        elif credential.oauth2 and credential.oauth2.access_token:
            access_token = str(credential.oauth2.access_token or "").strip()
            refresh_token = str(credential.oauth2.refresh_token or "").strip()
            expires_at = _normalize_int(credential.oauth2.expires_at)
        if not access_token:
            return

        if credential.oauth2:
            refresh_token = str(credential.oauth2.refresh_token or "").strip()
            expires_at = _normalize_int(credential.oauth2.expires_at)
        store_session_tokens(
            app_name=app_name,
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            session_id=session_id,
            expires_at=expires_at,
        )
        logging.info(
            "[CredentialService] Saved refreshed token for app=%s user=%s session=%s",
            app_name or "<missing>",
            user_id or "<missing>",
            session_id or "<missing>",
        )


class SessionAwareMcpToolset(McpToolset):
    """McpToolset variant that uses the current session token during discovery."""

    def _resolve_headers_from_context(self, readonly_context: Any) -> Optional[dict[str, str]]:
        invocation_context = getattr(readonly_context, "_invocation_context", None)
        session = getattr(invocation_context, "session", None) if invocation_context else None
        session_id = getattr(session, "id", "") if session is not None else ""
        app_name = getattr(invocation_context, "app_name", "") if invocation_context else ""
        user_id = getattr(invocation_context, "user_id", "") if invocation_context else ""
        session_state = getattr(session, "state", {}) if session is not None else {}
        record: dict[str, Any] = {}
        if app_name and user_id:
            record = _get_token_record(app_name, user_id, session_id)
        if not record:
            record = _token_record_from_state(session_state)

        access_token = str(record.get(SESSION_ACCESS_TOKEN_KEY, "")).strip()
        record_source = "store" if record else "none"
        if not access_token:
            access_token = token_context.get().strip()
            if access_token:
                record_source = "token_context"
        if not access_token:
            access_token = ACCESS_TOKEN
            if access_token:
                record_source = "env"
        if not access_token:
            _debug_trace(
                f"[MCP] No access token available for discovery app={app_name or '<missing>'} user={user_id or '<missing>'} session={session_id or '<missing>'}"
            )
            return None

        _debug_trace(
            "[MCP] Resolving discovery headers for "
            f"app={app_name or '<missing>'} user={user_id or '<missing>'} session={session_id or '<missing>'} "
            f"(source={record_source} token_len={len(access_token)} "
            f"state_token={bool(str((session_state or {}).get(SESSION_ACCESS_TOKEN_KEY, '')).strip())} "
            f"store_hit={bool(record)})"
        )
        return {"Authorization": f"Bearer {access_token}"}

    async def get_tools(self, readonly_context=None):
        headers = self._resolve_headers_from_context(readonly_context)
        auth_header_len = len(headers.get("Authorization", "")) if headers else 0
        _debug_trace(
            "[MCP] Starting discovery "
            f"url={MCP_URL} headers_present={bool(headers)} "
            f"auth_scheme={getattr(getattr(self, '_auth_scheme', None), 'scheme', '<missing>')} "
            f"auth_header_len={auth_header_len}"
        )
        try:
            _debug_trace(
                "[MCP] About to create MCP session "
                f"url={MCP_URL} headers_present={bool(headers)} auth_header_len={auth_header_len}"
            )
            session = await self._mcp_session_manager.create_session(headers=headers)
            _debug_trace(
                "[MCP] Session created for discovery "
                f"manager={type(self._mcp_session_manager).__name__} "
                f"session_id={getattr(session, '_session_id', '<unknown>')}"
            )
            tools_response = await session.list_tools()
        except Exception:
            logging.exception(
                "[MCP] Discovery failed url=%s headers_present=%s headers_len=%s",
                MCP_URL,
                bool(headers),
                len(headers.get("Authorization", "")) if headers else 0,
            )
            raise
        tools = []
        for tool in tools_response.tools:
            mcp_tool = MCPTool(
                mcp_tool=tool,
                mcp_session_manager=self._mcp_session_manager,
                auth_scheme=self._auth_scheme,
                auth_credential=None,
            )

            if self._is_tool_selected(mcp_tool, readonly_context):
                tools.append(mcp_tool)
        return tools

    async def _run_async_impl(self, args, tool_context, credential):
        headers = await self._get_headers(tool_context, credential)
        auth_header_len = len(headers.get("Authorization", "")) if headers else 0
        _debug_trace(
            "[MCP] Executing tool "
            f"name={getattr(self, 'name', '<unknown>')} "
            f"url={MCP_URL} headers_present={bool(headers)} auth_header_len={auth_header_len}"
        )
        return await super()._run_async_impl(
            args=args,
            tool_context=tool_context,
            credential=credential,
        )


def _build_workspace_toolset() -> Optional[SessionAwareMcpToolset]:
    if not MCP_URL:
        logging.warning("[Config] MCP_URL is not configured.")
        return None

    auth_scheme = HTTPBearer()

    return SessionAwareMcpToolset(
        connection_params=StreamableHTTPConnectionParams(url=MCP_URL),
        tool_filter=lambda tool, _: "modify_gmail_message_labels" not in tool.name,
        auth_scheme=auth_scheme,
        auth_credential=None,
    )


workspace_toolset = _build_workspace_toolset()
WORKSPACE_TOOLS = [workspace_toolset] if workspace_toolset is not None else []


def store_session_tokens(
    app_name: str,
    user_id: str,
    access_token: str,
    refresh_token: str = "",
    session_id: str = "",
    expires_at: Optional[int] = None,
    timezone_name: str = "",
    locale_name: str = "",
) -> None:
    if not app_name or not user_id or not access_token:
        return

    store_key = _token_store_key(app_name, user_id)
    existing = SESSION_TOKEN_STORE.get(store_key, {})
    resolved_refresh_token = refresh_token or str(
        existing.get(SESSION_REFRESH_TOKEN_KEY, "")
    ).strip()
    resolved_expires_at = expires_at
    if resolved_expires_at is None:
        resolved_expires_at = _normalize_int(
            existing.get(SESSION_TOKEN_EXPIRES_AT_KEY)
        )

    payload: dict[str, Any] = {
        SESSION_ACCESS_TOKEN_KEY: access_token,
        SESSION_REFRESH_TOKEN_KEY: resolved_refresh_token,
    }
    if resolved_expires_at is not None:
        payload[SESSION_TOKEN_EXPIRES_AT_KEY] = resolved_expires_at
    if timezone_name:
        payload[SESSION_TIMEZONE_KEY] = timezone_name
    if locale_name:
        payload[SESSION_LOCALE_KEY] = locale_name

    _debug_trace(
        "[Auth] Storing session tokens "
        f"app={app_name or '<missing>'} user={user_id or '<missing>'} session={session_id or '<missing>'} "
        f"access_len={len(access_token)} refresh_present={bool(resolved_refresh_token)} "
        f"expires_at={resolved_expires_at if resolved_expires_at is not None else '<missing>'} "
        f"timezone={timezone_name or '<missing>'} locale={locale_name or '<missing>'}"
    )
    SESSION_TOKEN_STORE[store_key] = payload
    _persist_token_record(app_name, user_id, payload)
    if session_id:
        SESSION_TOKEN_STORE[session_id] = dict(payload)
        _debug_trace(
            f"[Auth] Mirrored session token store by session_id={session_id} store_key={store_key}"
        )

    alias_keys = [key for key in _token_store_key_candidates(app_name, user_id) if key != store_key]
    for alias_key in alias_keys:
        SESSION_TOKEN_STORE[alias_key] = dict(payload)
        alias_app, alias_user = alias_key.split(":", 1)
        _persist_token_record(alias_app, alias_user, payload)
        _debug_trace(f"[Auth] Mirrored session token store by alias_key={alias_key} primary_key={store_key}")


async def calendar_activity_summary(
    tool_context: ToolContext,
    person: str = "",
    days_ahead: int = 7,
) -> dict:
    """Summarize calendar activity over the next N days."""
    setup_cloud_logging()
    if not MCP_URL:
        return {"status": "error", "message": "MCP_URL is not configured."}

    token = _resolve_access_token(tool_context)
    if not token:
        return {"status": "error", "message": "No Google access token is available."}

    timezone_name = _resolve_timezone_name(tool_context)
    try:
        tzinfo = ZoneInfo(timezone_name)
    except Exception:
        tzinfo = ZoneInfo(os.getenv("TIMEZONE", "Asia/Bangkok"))
        timezone_name = getattr(tzinfo, "key", timezone_name)

    now = datetime.now(tzinfo)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=max(days_ahead, 1))).isoformat()

    arguments: dict[str, Any] = {
        "time_min": time_min,
        "time_max": time_max,
        "detailed": True,
    }
    if _should_apply_calendar_query(person):
        arguments["query"] = person.strip()

    client = MCPGoogleClient(MCP_URL, token)
    try:
        result = await client.call_tool("get_events", arguments)
        items = _extract_calendar_items(result)
        event_lines = [_calendar_event_label(item) for item in items]
        if event_lines:
            if person.strip():
                summary_text = (
                    f"I found {len(event_lines)} calendar event(s) matching '{person.strip()}' "
                    f"in the next {days_ahead} day(s): "
                    + "; ".join(event_lines)
                )
            else:
                summary_text = (
                    f"I found {len(event_lines)} calendar event(s) in the next {days_ahead} day(s): "
                    + "; ".join(event_lines)
                )
        else:
            if person.strip():
                summary_text = (
                    f"I found no calendar events matching '{person.strip()}' in the next {days_ahead} day(s)."
                )
            else:
                summary_text = f"I found no calendar events in the next {days_ahead} day(s)."
        return {
            "status": "ok",
            "query": person.strip(),
            "timezone": timezone_name,
            "time_min": time_min,
            "time_max": time_max,
            "count": len(items),
            "summary": summary_text,
            "result": result,
        }
    except Exception as e:
        logging.exception("[MCP] Failed to summarize calendar activity")
        return {
            "status": "error",
            "message": str(e),
            "query": person,
        }
    finally:
        await client.close()


# --- Initialize State ---
# Pre-populating to prevent 'Context variable not found' errors
initial_state = {
    "CURRENT_INTENT": "None",
    SESSION_TIMEZONE_KEY: os.getenv("TIMEZONE", "Asia/Bangkok"),
}


# --- Alfred's Specialized Tools ---

def assess_household_conflicts(tool_context: ToolContext, intent: str) -> dict:
    """Analyzes for overlaps between work (Calendar) and household (Firestore) domains."""
    setup_cloud_logging()
    logging.info(f"[Alfred Core] Analyzing intent: {intent}")

    analysis_results = []
    email = get_user_email(token_context.get())
    db = get_db()

    # 1. Read per-user household rules from Firestore
    try:
        if db is None:
            return {"status": "Error", "findings": ["Firestore unavailable."], "advice": ""}
        user_ref = db.collection("users").document(email).collection("household").document("profile")
        household = user_ref.get()
        if household.exists:
            data = household.to_dict()
            rules = data.get("rules", [])
            analysis_results.append(f"Loaded {len(rules)} family rules for {email}.")

            # Simple keyword-based conflict check
            for rule in rules:
                if rule["name"].lower() in intent.lower():
                    analysis_results.append(
                        f"ALERT: Intent matches mandatory rule '{rule['name']}' at {rule['time']}."
                    )
        else:
            analysis_results.append(
                f"No profile found for {email}. Using default butler discretion."
            )
    except Exception as e:
        logging.warning(f"[Firestore] Could not load user household: {e}")
        analysis_results.append("Error accessing Household rules.")

    return {
        "status": "Conflict analysis complete.",
        "findings": analysis_results,
        "advice": "Please cross-reference with the workspace tools to ensure no professional overlaps.",
    }


def update_household_ledger(
    tool_context: ToolContext,
    action: str,
    item: str | None = None,
) -> dict:
    """Manages the persistent Household Ledger (Shopping List, Chores, Audit Trail)."""
    setup_cloud_logging()
    email = get_user_email(token_context.get())
    logging.info(f"[Ledger] Performing: {action} on {item} for Master: {email}")
    db = get_db()

    try:
        if db is None:
            return {"status": "Ledger unavailable: Firestore not connected."}
        user_ref = db.collection("users").document(email).collection("household").document("profile")

        if "add" in action.lower() and "list" in action.lower() and item:
            user_ref.set(
                {
                    "shopping_list": firestore.ArrayUnion([item]),
                    "last_updated": datetime.now(timezone.utc),
                },
                merge=True,
            )
            return {"status": f"Added '{item}' to the Household Shopping List for {email}."}

        # Audit trail per user
        db.collection("users").document(email).collection("audit").add(
            {
                "action": action,
                "item": item,
                "agent": tool_context.agent_name if hasattr(tool_context, "agent_name") else "unknown",
                "timestamp": datetime.now(timezone.utc),
            }
        )
        return {"status": f"Action logged to {email}'s Audit Trail."}
    except Exception as e:
        logging.error(f"[Ledger Error] {e}")
        return {"status": f"Ledger error: {str(e)}"}


# --- Agent Definitions ---

# 1. The Work Agent (Professional Obligations)
# Has full Google Workspace access (Calendar, Contacts, Gmail, etc.) via MCP.
work_agent = Agent(
    name="work_agent",
    model=model_name,
    description="Manages meetings, emails, contacts, and professional documents.",
    instruction=f"""
    You are Alfred's professional attache. Your focus is Master Wayne's professional life.
    TODAY'S DATE is {today_str}. TIMEZONE is {tz_str}.
    Prefer the timezone in session state under `{SESSION_TIMEZONE_KEY}` when present.

    - Use the Google Workspace MCP tools for Calendar, Contacts, and Email CRUD.
    - For calendar summaries, use `calendar_activity_summary` instead of inventing date math or code.
    - Example: for "Robin next 1 week", call `calendar_activity_summary(person="Robin", days_ahead=7)`.
    - Example: for "What are the work events in the next 1 week?", call `calendar_activity_summary(days_ahead=7)`.
    - Never write Python, import modules, or invent helper code in your response.
    - When needed, inspect the available Workspace tools first and then call the correct tool by name.
    - Strictly only return events that are professional (keywords: meeting, presentation, call, board, conference, client, project, interview, deadline).
    - SPECIAL PROJECTS: Mentions of Gotham, Batman, or high-stakes 'midnight' meetings are to be treated as top-secret high-priority work.
    - MIDNIGHT LOGIC: If the Master asks for 'midnight' and it is currently late in the day (after 6 PM), assume he means the midnight that starts TOMORROW.
    - MANUALLY CALCULATE the date range for any relative terms.
    - IGNORE: Birthdays, Zumba, and simple family errands.
    """,
    tools=[calendar_activity_summary, *WORKSPACE_TOOLS],
    output_key="work_context",
)


# 2. The Home Agent (Domestic Coordination)
home_agent = Agent(
    name="home_agent",
    model=model_name,
    description="Coordinates for family events, home maintenance, and deliveries.",
    instruction="""
    You manage the family domain and home coordination.
    - Read the conversation context for any home/family event
       (keywords: dinner, lunch, breakfast, family, school, doctor, birthday, anniversary, vacation, appointment, pickup).
    - Track grocery lists, errands, and family appointments.
    - When a household or family need is mentioned, use the workspace tools for Calendar, Contacts, and Email as needed.
    - Call `add_event` to register the event. send_gmail_message to notify the event to the family members if it's found in search_contacts
    - Call `list_events` and include the home schedule in your output_key summary
    - If the current task is purely professional (work meetings, emails), simply observe and provide context if asked.
    - Maintain the Alfred persona: helpful, efficient, and deeply loyal to the household's well-being.
    """,
    tools=[update_household_ledger, *WORKSPACE_TOOLS],
    output_key="home_context",
)


output_formatter = Agent(
    name="output_formatter",
    model=model_name,
    description="Final response formatter for Alfred's voice.",
    instruction=f"""
    You are Alfred Pennyworth (Batman's butler).
    TODAY'S DATE: {today_str}

    Your task is to take the specialist result and provide a single, unified summary for the Master.

    - Be dry, witty, and impeccable.
    - If a conflict between work and home was detected, explain which event took precedence and why.
    - If there was no conflict, simply provide a polished summary of the requested information.
    - Mention any actions taken, such as emails sent or entries made.
    - Preserve important names, dates, times, and counts exactly.
    - Do not add new facts.
    - Do not mention internal tools, callbacks, or agents.
    - Maintain the persona. No bullet-point walls.
    """,
)


work_flow = SequentialAgent(
    name="work_flow",
    description="Runs the work specialist and then the output formatter.",
    sub_agents=[work_agent, output_formatter],
)

home_output_formatter = output_formatter.clone(update={"name": "home_output_formatter"})

home_flow = SequentialAgent(
    name="home_flow",
    description="Runs the home specialist and then the output formatter.",
    sub_agents=[home_agent, home_output_formatter],
)


# --- The Orchestration Layer ---

alfred_root = Agent(
    name="alfred_core",
    model=model_name,
    description="Alfred Pennyworth - Household Orchestrator",
    instruction=f"""
    You are Alfred Pennyworth, butler to the Wayne family.
    TODAY'S DATE: {today_str} | TIMEZONE: {tz_str}
    Prefer the timezone in session state under `{SESSION_TIMEZONE_KEY}` when present.

    Your primary duty is to ensure Master can fulfill his professional duties,
    including all Google Workspace work, while not neglecting his family responsibilities.

    ROUTING RULES:
    1. If the request is primarily professional, delegate only to work_agent.
    2. If the request is primarily household/domestic, delegate only to home_agent.
    3. If the request genuinely spans both domains, delegate to the specialist that owns the dominant part first, then only involve the other if necessary.
    4. Do not invoke both specialists for a single-domain request.
    5. Do not answer the user directly; delegate to the correct workflow and let the formatter deliver the final reply.

    "Be present at work. Be present at home. I shall handle the rest."
    """,
    tools=[assess_household_conflicts],
    sub_agents=[work_flow, home_flow],
)

root_agent = alfred_root
