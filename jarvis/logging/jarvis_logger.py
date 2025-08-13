import logging
import sqlite3
from datetime import datetime
from typing import Any, Optional
import json
import threading
from contextlib import contextmanager

# Default SQLite database for logs.  Defined here to avoid importing
# ``jarvis.core`` at module import time, which previously caused a
# circular import when ``JarvisLogger`` was imported by modules that
# themselves were loaded during ``jarvis.core`` initialization.
# The central constant still lives in ``jarvis.core.constants`` but we
# lazily import it in ``JarvisLogger.__init__`` if needed.
DEFAULT_LOG_DB_PATH = "jarvis_logs.db"


class JarvisLogger:
    """Thread-safe logger that writes to stdout and a SQLite database."""

    def __init__(
        self, db_path: str | None = None, log_level: int = logging.INFO
    ) -> None:
        """Create a new logger.

        Parameters
        ----------
        db_path:
            Path to the SQLite database used for log storage.  If ``None``,
            the value from ``jarvis.core.constants.LOG_DB_PATH`` is used when
            available, otherwise ``DEFAULT_LOG_DB_PATH`` is applied.  The lazy
            import prevents circular imports during package initialization.
        log_level:
            Standard library logging level for console output.
        """

        if db_path is None:
            try:  # Import lazily to avoid triggering jarvis.core import
                from ..core.constants import LOG_DB_PATH  # type: ignore

                db_path = LOG_DB_PATH
            except Exception:
                db_path = DEFAULT_LOG_DB_PATH

        self.db_path = db_path
        self.log_level = log_level
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._local = threading.local()  # Thread-local storage for connections

        # Initialize the database schema
        self._ensure_table()

        # Set up console logging
        self.logger = logging.getLogger("jarvis")
        if not self.logger.handlers:
            self.logger.setLevel(log_level)
            handler = logging.StreamHandler()
            formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            # Create a new connection for this thread
            # Use check_same_thread=False to allow cross-thread usage
            # But we'll still use locks to ensure thread safety
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=10.0,  # 10 second timeout for database locks
            )
            # Enable WAL mode for better concurrent access
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA synchronous=NORMAL")

        return self._local.connection

    @contextmanager
    def _db_context(self):
        """Context manager for thread-safe database operations."""
        with self._lock:
            conn = self._get_connection()
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()

    def _ensure_table(self) -> None:
        """Ensure the logs table exists."""
        with self._db_context() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    level TEXT,
                    action TEXT,
                    details TEXT
                )
                """
            )

    def log(self, level: str, action: str, details: Optional[Any] = None) -> None:
        """Thread-safe log method that writes to stdout and SQLite database."""
        try:
            level_name = level.upper()

            # Format details
            if details is not None and not isinstance(details, str):
                try:
                    details_str = json.dumps(details)
                except Exception:
                    details_str = str(details)
            else:
                details_str = details or ""

            # Log to console (thread-safe by default)
            message = f"{action}: {details_str}" if details_str else action
            self.logger.log(getattr(logging, level_name, logging.INFO), message)

            # Log to database (made thread-safe with our context manager)
            timestamp = datetime.now().isoformat()

            with self._db_context() as conn:
                conn.execute(
                    "INSERT INTO logs (timestamp, level, action, details) VALUES (?, ?, ?, ?)",
                    (timestamp, level_name, action, details_str),
                )

        except Exception as e:
            # Fallback: if database logging fails, at least log to console
            try:
                self.logger.error(f"Logger error: {e} - Original message: {action}")
            except Exception:
                # Last resort: print to stderr
                import sys

                print(f"LOGGER FAILURE: {e} - {action}", file=sys.stderr)

    def close(self) -> None:
        """Close database connections for the current thread."""
        with self._lock:
            if hasattr(self._local, "connection") and self._local.connection:
                try:
                    self._local.connection.close()
                except Exception:
                    pass  # Best effort cleanup
                finally:
                    self._local.connection = None

    def close_all_connections(self) -> None:
        """Close all database connections (call this on shutdown)."""
        with self._lock:
            # This is a best-effort cleanup
            # Individual threads should call close() themselves
            if hasattr(self._local, "connection") and self._local.connection:
                try:
                    self._local.connection.close()
                    self._local.connection = None
                except Exception:
                    pass

    def __enter__(self) -> "JarvisLogger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self):
        """Cleanup on garbage collection."""
        try:
            self.close()
        except Exception:
            pass  # Best effort cleanup
