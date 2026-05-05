"""
Authentication module for the web interface.
Handles user validation and session management.
"""

import logging
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Tuple
import hashlib
import secrets
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# In-memory session storage
sessions: Dict[str, Dict] = {}


class AuthManager:
    """Manages user authentication and session handling."""

    def __init__(self, config: Dict):
        """
        Initialize auth manager with configuration.

        Args:
            config: Configuration dictionary containing web.auth settings
        """
        self.config = config
        self.session_timeout = config.get("session_timeout_minutes", 60)
        self.users = config.get("users", {})

    def validate_credentials(self, username: str, password: str) -> bool:
        """
        Validate user credentials.

        Args:
            username: Username to validate
            password: Password to validate (plaintext)

        Returns:
            bool: True if credentials are valid
        """
        if username not in self.users:
            return False

        stored_hash = self.users[username]

        # Support both bcrypt hashes and plaintext for backwards compatibility
        if stored_hash.startswith("$2b$"):
            return pwd_context.verify(password, stored_hash)
        else:
            # Plaintext comparison (for testing/simple setups)
            return password == stored_hash

    def create_session(self, username: str) -> str:
        """
        Create a new session for a user.

        Args:
            username: Username to create session for

        Returns:
            str: Session token
        """
        session_token = secrets.token_urlsafe(32)
        sessions[session_token] = {
            "username": username,
            "created_at": datetime.now(UTC),
            "last_activity": datetime.now(UTC)
        }
        logger.info(f"Session created for user: {username}")
        return session_token

    def validate_session(self, token: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a session token.

        Args:
            token: Session token to validate

        Returns:
            Tuple of (is_valid, username) or (False, None) if invalid/expired
        """
        if token not in sessions:
            return False, None

        session = sessions[token]
        session_time_delta = datetime.now(UTC) - session["created_at"]

        if session_time_delta > timedelta(minutes=self.session_timeout):
            del sessions[token]
            return False, None

        # Update last activity
        session["last_activity"] = datetime.now(UTC)
        return True, session["username"]

    def destroy_session(self, token: str) -> bool:
        """
        Destroy a session.

        Args:
            token: Session token to destroy

        Returns:
            bool: True if session was destroyed
        """
        if token in sessions:
            del sessions[token]
            logger.info(f"Session destroyed: {token}")
            return True
        return False

    def cleanup_expired_sessions(self):
        """Remove expired sessions."""
        expired_tokens = []
        for token, session in sessions.items():
            session_time_delta = datetime.now(UTC) - session["created_at"]
            if session_time_delta > timedelta(minutes=self.session_timeout):
                expired_tokens.append(token)

        for token in expired_tokens:
            del sessions[token]

        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired sessions")

