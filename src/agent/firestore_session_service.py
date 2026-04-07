"""Firestore-backed SessionService for Google ADK.

Stores sessions and events in Firestore so chat history persists across
Cloud Run container restarts and users can resume conversations.

Firestore structure:
  adk_sessions/
    {app_name}/
      users/
        {user_id}/
          sessions/
            {session_id}/          <-- session doc (state, last_update_time)
              events/
                {event_id}/        <-- event docs (serialized Event JSON)
"""

import json
import logging
import time
import uuid
from typing import Any, Optional

from google.adk.events.event import Event
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)
from google.adk.sessions.session import Session
from google.cloud import firestore

logger = logging.getLogger(__name__)

_ROOT = "adk_sessions"


class FirestoreSessionService(BaseSessionService):
    """Persists ADK sessions and events in Google Cloud Firestore."""

    def __init__(self, project: Optional[str] = None):
        self._db = firestore.Client(project=project) if project else firestore.Client()

    # ---- helpers ---------------------------------------------------------- #

    def _session_ref(self, app_name: str, user_id: str, session_id: str):
        return (
            self._db.collection(_ROOT)
            .document(app_name)
            .collection("users")
            .document(user_id)
            .collection("sessions")
            .document(session_id)
        )

    def _events_col(self, app_name: str, user_id: str, session_id: str):
        return self._session_ref(app_name, user_id, session_id).collection("events")

    @staticmethod
    def _serialize_event(event: Event) -> dict:
        return json.loads(event.model_dump_json())

    @staticmethod
    def _deserialize_event(data: dict) -> Event:
        return Event.model_validate(data)

    # ---- abstract method implementations --------------------------------- #

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        sid = session_id or str(uuid.uuid4())
        now = time.time()

        session = Session(
            id=sid,
            app_name=app_name,
            user_id=user_id,
            state=state or {},
            events=[],
            last_update_time=now,
        )

        self._session_ref(app_name, user_id, sid).set(
            {
                "state": json.dumps(session.state),
                "last_update_time": now,
                "app_name": app_name,
                "user_id": user_id,
            }
        )
        logger.info("[Firestore] Session created: %s/%s/%s", app_name, user_id, sid)
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        doc = self._session_ref(app_name, user_id, session_id).get()
        if not doc.exists:
            return None

        data = doc.to_dict()
        state = json.loads(data.get("state", "{}"))
        last_update = data.get("last_update_time", 0.0)

        # Load events, ordered by timestamp
        query = (
            self._events_col(app_name, user_id, session_id)
            .order_by("timestamp")
        )

        # Apply filters from config
        if config and config.after_timestamp is not None:
            query = query.where("timestamp", ">", config.after_timestamp)

        event_docs = query.stream()
        events = []
        for edoc in event_docs:
            try:
                events.append(self._deserialize_event(edoc.to_dict().get("data", {})))
            except Exception as e:
                logger.warning("[Firestore] Skipping malformed event %s: %s", edoc.id, e)

        # Apply num_recent_events limit
        if config and config.num_recent_events is not None:
            events = events[-config.num_recent_events:]

        return Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            state=state,
            events=events,
            last_update_time=last_update,
        )

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: Optional[str] = None,
    ) -> ListSessionsResponse:
        sessions: list[Session] = []

        if user_id:
            col = (
                self._db.collection(_ROOT)
                .document(app_name)
                .collection("users")
                .document(user_id)
                .collection("sessions")
            )
            for doc in col.stream():
                d = doc.to_dict()
                sessions.append(
                    Session(
                        id=doc.id,
                        app_name=app_name,
                        user_id=user_id,
                        state=json.loads(d.get("state", "{}")),
                        events=[],  # Don't load events for list
                        last_update_time=d.get("last_update_time", 0.0),
                    )
                )
        else:
            # List all users' sessions for this app
            users_col = (
                self._db.collection(_ROOT)
                .document(app_name)
                .collection("users")
            )
            for user_doc in users_col.stream():
                uid = user_doc.id
                sess_col = users_col.document(uid).collection("sessions")
                for sdoc in sess_col.stream():
                    d = sdoc.to_dict()
                    sessions.append(
                        Session(
                            id=sdoc.id,
                            app_name=app_name,
                            user_id=uid,
                            state=json.loads(d.get("state", "{}")),
                            events=[],
                            last_update_time=d.get("last_update_time", 0.0),
                        )
                    )

        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        # Delete all events first
        events_col = self._events_col(app_name, user_id, session_id)
        for edoc in events_col.stream():
            edoc.reference.delete()

        # Delete session doc
        self._session_ref(app_name, user_id, session_id).delete()
        logger.info("[Firestore] Session deleted: %s/%s/%s", app_name, user_id, session_id)

    async def append_event(self, session: Session, event: Event) -> Event:
        # Let the base class handle in-memory state updates
        event = await super().append_event(session, event)

        # Persist event to Firestore
        event_id = event.id or str(uuid.uuid4())
        now = time.time()

        self._events_col(session.app_name, session.user_id, session.id).document(
            event_id
        ).set(
            {
                "data": self._serialize_event(event),
                "timestamp": event.timestamp if event.timestamp else now,
            }
        )

        # Update session state + timestamp
        self._session_ref(session.app_name, session.user_id, session.id).update(
            {
                "state": json.dumps(session.state, default=str),
                "last_update_time": now,
            }
        )

        return event
