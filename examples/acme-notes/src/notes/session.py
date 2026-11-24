"""Session store for Acme Notes.

Implements identity/session: SESS-01 (creation), SESS-02 (idle validity),
SESS-03 (absolute lifetime). See specmaker/specs/identity/session/spec.md.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

from .clock import Clock, utc_now

IDLE_TIMEOUT = timedelta(minutes=30)      # SESS-02, LLD section 5
ABSOLUTE_LIFETIME = timedelta(hours=12)   # SESS-03, LLD section 5


class SessionExpired(Exception):
    """Raised when a token is no longer valid. `reason` is the API error code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class Session:
    user_id: str
    created_at: datetime
    last_seen: datetime


class SessionStore:
    def __init__(self, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._sessions: Dict[str, Session] = {}

    def create(self, user_id: str) -> str:
        """SESS-01: a successful sign-in returns a new opaque token."""
        token = secrets.token_urlsafe(32)
        now = self._clock()
        self._sessions[token] = Session(user_id, created_at=now, last_seen=now)
        return token

    def validate(self, token: str) -> str:
        """Return the user id for a valid token and refresh its idle timer."""
        session: Optional[Session] = self._sessions.get(token)
        if session is None:
            raise SessionExpired("session_invalid")
        now = self._clock()
        if now - session.created_at >= ABSOLUTE_LIFETIME:
            del self._sessions[token]
            raise SessionExpired("session_lifetime_exceeded")
        if now - session.last_seen >= IDLE_TIMEOUT:
            del self._sessions[token]
            raise SessionExpired("session_expired")
        session.last_seen = now
        return session.user_id

    def sign_out(self, token: str) -> None:
        self._sessions.pop(token, None)
