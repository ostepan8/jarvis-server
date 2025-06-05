import logging
import sqlite3
from datetime import datetime
from typing import Optional, Any
import json


class JarvisLogger:
    """Simple logger that writes to stdout and a SQLite database."""

    def __init__(self, db_path: str = "jarvis_logs.db", log_level: int = logging.INFO) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self._ensure_table()

        self.logger = logging.getLogger("jarvis")
        if not self.logger.handlers:
            self.logger.setLevel(log_level)
            handler = logging.StreamHandler()
            formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _ensure_table(self) -> None:
        with self.conn:
            self.conn.execute(
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
        """Log a message to stdout and the SQLite database."""
        level_name = level.upper()
        if details is not None and not isinstance(details, str):
            try:
                details_str = json.dumps(details)
            except Exception:
                details_str = str(details)
        else:
            details_str = details or ""

        message = f"{action}: {details_str}" if details_str else action
        self.logger.log(getattr(logging, level_name, logging.INFO), message)

        timestamp = datetime.utcnow().isoformat()
        with self.conn:
            self.conn.execute(
                "INSERT INTO logs (timestamp, level, action, details) VALUES (?, ?, ?, ?)",
                (timestamp, level_name, action, details_str),
            )
