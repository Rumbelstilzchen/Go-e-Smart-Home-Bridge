"""
Override Manager for temporary charging logic modifications.
Handles time-based overrides for vehicle charging with battery prioritization disabled.
"""

import logging
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict
import json
import os

logger = logging.getLogger(__name__)


class OverrideManager:
    """Manages temporary overrides of the charging logic."""

    def __init__(self, config: Dict):
        """
        Initialize override manager.

        Args:
            config: Configuration dictionary
            state_file: File to persist override state
        """
        self.config = config
        self.override: Optional[Dict] = None
        self.load_state()

    def set_override(self, end_time: datetime, start_time: Optional[datetime] = None) -> bool:
        """
        Set a new override period.

        Args:
            end_time: End time for the override (datetime object)
            start_time: Optional start time (defaults to now)

        Returns:
            bool: True if override was set successfully
        """
        if start_time is None:
            start_time = datetime.now(UTC)

        if end_time <= start_time:
            logger.warning("Override end time must be after start time")
            return False

        self.override = {
            "start_time": start_time,
            "end_time": end_time,
            "created_at": datetime.now(UTC),
            "active": True
        }

        self.save_state()
        logger.info(f"Override set: {start_time} -> {end_time}")
        return True

    def is_override_active(self) -> bool:
        """
        Check if an override is currently active.

        Returns:
            bool: True if override is active and not expired
        """
        if self.override is None or not self.override.get("active", False):
            return False

        try:
            end_time = self.override["end_time"]
            if datetime.now(UTC) >= end_time:
                self.clear_override()
                return False
            return True
        except (ValueError, KeyError):
            logger.error("Invalid override state")
            self.clear_override()
            return False

    def get_remaining_time(self) -> Optional[timedelta]:
        """
        Get remaining time for active override.

        Returns:
            timedelta: Remaining time, or None if no active override
        """
        if not self.is_override_active():
            return None

        try:
            end_time = self.override["end_time"]
            remaining = end_time - datetime.now(UTC)
            return remaining if remaining.total_seconds() > 0 else None
        except (ValueError, KeyError):
            return None

    def get_override_info(self) -> Optional[Dict]:
        """
        Get current override information.

        Returns:
            dict: Override info or None if no active override
        """
        if not self.is_override_active():
            return None

        try:
            start_time = self.override["start_time"]
            end_time = self.override["end_time"]
            remaining = self.get_remaining_time()

            return {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "remaining_seconds": int(remaining.total_seconds()) if remaining else 0,
                "is_active": True
            }
        except (ValueError, KeyError):
            return None

    def clear_override(self) -> bool:
        """
        Clear current override.

        Returns:
            bool: True if override was cleared
        """
        if self.override is not None:
            self.override = None
            self.save_state()
            logger.info('Home-Akku has prio again - set by web_server')
            return True
        return False

    def save_state(self):
        """Persist override state to file."""
        self.config['override'] = self.override

    def load_state(self):
        """Load override state from file."""
        self.override = self.config.get('override',None)

