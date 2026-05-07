"""
Authentication module for the web interface.
Handles user validation and session management with thread-safe operations.
"""

import logging
from datetime import datetime, timedelta, UTC
import secrets
import threading
import bcrypt

logger = logging.getLogger(__name__)

# Password hashing configuration

# In-memory session storage with thread safety

_sessions_lock = threading.Lock()



def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed.encode("utf-8"),
    )

class AuthManager:
    """Manages user authentication and session handling."""

    def __init__(self, config: dict):
        """
        Initialize auth manager with configuration.

        Args:
            config: Configuration dictionary containing web.auth settings
        """
        self.config = config
        self.session_timeout = config.get("session_timeout_minutes", 60)
        self.users = {user: pw if pw.startswith("$2b$") else hash_password(pw) for user, pw in config.get("users", {}).items()}
        self.sessions: dict[str, dict[str, str|datetime]] = {}

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

        # Only support bcrypt hashes (no plaintext fallback for security)
        if not stored_hash.startswith("$2b$"):
            logger.error(f"Invalid password hash format for user: {username}")
            return False

        try:
            return verify_password(password, stored_hash)
        except Exception as e:
            logger.error(f"Password verification error for user {username}: {e}")
            return False

    def create_session(self, username: str) -> str:
        """
        Create a new session for a user (thread-safe).

        Args:
            username: Username to create session for

        Returns:
            str: Session token
        """
        session_token = secrets.token_urlsafe(32)

        with _sessions_lock:
            self.sessions[session_token] = {
                "username": username,
                "created_at": datetime.now(UTC),
                "last_activity": datetime.now(UTC)
            }

        logger.info(f"Session created for user: {username}")
        return session_token

    def validate_session(self, token: str) -> tuple[bool, str|None]:
        """
        Validate a session token (thread-safe).

        Args:
            token: Session token to validate

        Returns:
            Tuple of (is_valid, username) or (False, None) if invalid/expired
        """
        with _sessions_lock:
            session = self.sessions.get(token, None)
            if session is None:
                return False, None

            session_time_delta = datetime.now(UTC) - session["created_at"]

            if session_time_delta > timedelta(minutes=self.session_timeout):
                del self.sessions[token]
                return False, None

            # Update last activity
            session["last_activity"] = datetime.now(UTC)
            username = session["username"]

        return True, username

    def destroy_session(self, token: str) -> bool:
        """
        Destroy a session (thread-safe).

        Args:
            token: Session token to destroy

        Returns:
            bool: True if session was destroyed
        """
        with _sessions_lock:
            if token in self.sessions:
                del self.sessions[token]
                logger.info(f"Session destroyed: {token}")
                return True
        return False

    def cleanup_expired_sessions(self):
        """Remove expired sessions (thread-safe)."""
        expired_tokens = []

        with _sessions_lock:
            for token, session in self.sessions.items():
                session_time_delta = datetime.now(UTC) - session["created_at"]
                if session_time_delta > timedelta(minutes=self.session_timeout):
                    expired_tokens.append(token)

            for token in expired_tokens:
                del self.sessions[token]

        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired sessions")

