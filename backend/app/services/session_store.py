"""Simple in-memory session storage for local development."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import uuid4

from ..models import ChatMessage, DashboardData


@dataclass
class SessionState:
    dashboard: DashboardData
    history: List[ChatMessage] = field(default_factory=list)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}

    def create(self, dashboard: DashboardData, history: List[ChatMessage]) -> str:
        session_id = uuid4().hex
        self._sessions[session_id] = SessionState(
            dashboard=deepcopy(dashboard),
            history=deepcopy(history),
        )
        return session_id

    def get(self, session_id: str) -> Optional[SessionState]:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return SessionState(
            dashboard=deepcopy(state.dashboard),
            history=deepcopy(state.history),
        )

    def save(self, session_id: str, dashboard: DashboardData, history: List[ChatMessage]) -> None:
        self._sessions[session_id] = SessionState(
            dashboard=deepcopy(dashboard),
            history=deepcopy(history),
        )
