from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Deque, List, Sequence


@dataclass(frozen=True)
class LogEntry:
    """Immutable value object that represents a single captured log record."""

    timestamp: datetime
    level: str
    logger_name: str
    message: str


class LogStore:
    """Thread-safe, bounded queue that keeps the most recent log entries."""

    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: Deque[LogEntry] = deque(maxlen=max_entries)
        self._lock = RLock()

    def append(self, entry: LogEntry) -> None:
        """Push a new entry onto the queue, dropping the oldest if full."""
        with self._lock:
            self._entries.append(entry)

    def latest(self, limit: int) -> List[LogEntry]:
        """Return up to `limit` newest entries, newest-first."""
        with self._lock:
            if not self._entries:
                return []
            clamped_limit = max(1, min(limit, len(self._entries)))
            return list(self._entries)[-clamped_limit:][::-1]


class InMemoryLogHandler(logging.Handler):
    """Logging handler that mirrors every record into the shared store."""

    def __init__(self, store: LogStore) -> None:
        super().__init__()
        self._store = store

    def emit(self, record: logging.LogRecord) -> None:
        try:
            timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone()
            entry = LogEntry(
                timestamp=timestamp,
                level=record.levelname,
                logger_name=record.name,
                message=record.getMessage(),
            )
            self._store.append(entry)
        except Exception:
            # Fall back to stdlib error handling so logging keeps working.
            self.handleError(record)


log_store = LogStore(max_entries=1000)
_handler: InMemoryLogHandler | None = None
_configured_loggers: Sequence[str] = (
    "app",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "uvicorn.asgi",
)


def install_log_buffer_handler() -> None:
    """Attach the in-memory handler to the relevant loggers once."""

    global _handler
    if _handler is not None:
        return

    handler = InMemoryLogHandler(log_store)
    handler.setLevel(logging.INFO)

    for logger_name in _configured_loggers:
        logger = logging.getLogger(logger_name)
        logger.addHandler(handler)
        if logger.level > logging.INFO or logger.level == 0:
            logger.setLevel(logging.INFO)

    _handler = handler


def get_recent_logs(limit: int = 200) -> List[LogEntry]:
    """Helper used by the admin page to fetch the latest log entries."""

    return log_store.latest(limit)
