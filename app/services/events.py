from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re

from app.database import Database


SENSITIVE_KEYS = {"openai_api_key", "azure_storage_sas_token", "sas_token", "authorization", "api_key"}


def redact(value: Any) -> Any:
    """Recursively remove known credential fields before they reach persistence."""
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if key.lower() in SENSITIVE_KEYS else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", value)
        value = re.sub(r"([?&](?:sig|se|sp|sv)=)[^&\s]+", r"\1[REDACTED]", value, flags=re.IGNORECASE)
    return value


class EventLogger:
    def __init__(self, database: Database):
        self.database = database

    def log(self, event_type: str, message: str, severity: str = "info", **kwargs: Any) -> None:
        self.database.add_event(redact({
            "timestamp": datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S"),
            "event_type": event_type,
            "severity": severity,
            "message": message,
            **kwargs,
        }))
