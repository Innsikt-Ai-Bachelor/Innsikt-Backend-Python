from __future__ import annotations

from typing import Dict, List
from uuid import uuid4
import threading

from models.chat import StoredMessage


# In-memory chat sessions.
# NOTE: This is intentionally simple for development and is process-local.
# You can later swap this to a DB-backed store without changing the API layer.
_sessions: Dict[str, List[StoredMessage]] = {}
_sessions_lock = threading.Lock()


def create_session() -> str:
    session_id = str(uuid4())
    with _sessions_lock:
        _sessions[session_id] = []
    return session_id


def session_exists(session_id: str) -> bool:
    with _sessions_lock:
        return session_id in _sessions


def add_message(session_id: str, role: str, content: str) -> None:
    msg = StoredMessage(role=role, content=content)
    with _sessions_lock:
        if session_id not in _sessions:
            _sessions[session_id] = []
        _sessions[session_id].append(msg)


def get_messages(session_id: str) -> List[StoredMessage]:
    with _sessions_lock:
        return _sessions.get(session_id, [])
