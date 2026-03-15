"""Create, resume, and list sessions."""

from __future__ import annotations

import uuid

from sam.agent.history import ConversationHistory
from sam.config import Settings
from sam.session.storage import load_session, save_session


class SessionManager:
    """Manages agent sessions with persistence."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_session(self) -> tuple[str, ConversationHistory]:
        """Create a new session with a unique ID."""
        session_id = str(uuid.uuid4())[:8]
        history = ConversationHistory(context_window=self.settings.context_window)
        return session_id, history

    def resume_session(self, session_id: str) -> tuple[str, ConversationHistory] | None:
        """Resume an existing session."""
        data = load_session(session_id)
        if data is None:
            return None

        messages = data.get("messages", [])
        history = ConversationHistory.from_serializable(
            messages,
            context_window=self.settings.context_window,
        )
        return session_id, history

    def save(self, session_id: str, history: ConversationHistory) -> None:
        """Save the current session state."""
        save_session(
            session_id=session_id,
            messages=history.to_serializable(),
            model=self.settings.model,
            working_dir=str(self.settings.working_dir),
        )

    def get_or_create(self) -> tuple[str, ConversationHistory]:
        """Resume a session if session_id is set, otherwise create new."""
        if self.settings.session_id:
            result = self.resume_session(self.settings.session_id)
            if result:
                return result

        return self.create_session()
