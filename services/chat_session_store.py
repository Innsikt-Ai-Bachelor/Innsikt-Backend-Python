from __future__ import annotations

from typing import Dict, List
from uuid import uuid4

from models.chat import StoredMessage


# In-memory chat sessions.
# NOTE: This is intentionally simple for development.
# You can later swap this to a DB-backed store without changing the API layer.
_sessions: Dict[str, List[StoredMessage]] = {}


def create_session() -> str:
    session_id = str(uuid4())
    _sessions[session_id] = []
    return session_id


def session_exists(session_id: str) -> bool:
    return session_id in _sessions


def add_message(session_id: str, role: str, content: str) -> None:
    if session_id not in _sessions:
        _sessions[session_id] = []
    _sessions[session_id].append(StoredMessage(role=role, content=content))


def get_messages(session_id: str) -> List[StoredMessage]:
    return _sessions.get(session_id, [])
