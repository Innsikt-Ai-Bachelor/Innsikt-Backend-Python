from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from models.chat import StoredMessage


@dataclass
class ChatSession:
    scenario_id: Optional[int]
    title: Optional[str]
    messages: List[StoredMessage]


_sessions: Dict[str, ChatSession] = {}
_sessions_lock = threading.Lock()


def create_session(scenario_id: int | None = None, title: str | None = None) -> str:
    session_id = str(uuid4())
    with _sessions_lock:
        _sessions[session_id] = ChatSession(
            scenario_id=scenario_id,
            title=title,
            messages=[],
        )
    return session_id


def session_exists(session_id: str) -> bool:
    with _sessions_lock:
        return session_id in _sessions


def add_message(session_id: str, role: str, content: str) -> None:
    msg = StoredMessage(role=role, content=content)
    with _sessions_lock:
        if session_id not in _sessions:
            _sessions[session_id] = ChatSession(scenario_id=None, title=None, messages=[])
        _sessions[session_id].messages.append(msg)


def get_messages(session_id: str) -> List[StoredMessage]:
    with _sessions_lock:
        s = _sessions.get(session_id)
        return list(s.messages) if s else []


def get_session_meta(session_id: str) -> Tuple[int | None, str | None]:
    with _sessions_lock:
        s = _sessions.get(session_id)
        if not s:
            return None, None
        return s.scenario_id, s.title
