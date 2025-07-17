from __future__ import annotations

import asyncio
import sqlite3
from typing import List, Optional, Set

from .base import NightAgent
from ..loggers.jarvis_logger import JarvisLogger
from ..constants import LOG_DB_PATH
from ..agents.message import Message


class TriggerPhraseSuggesterAgent(NightAgent):
    """Suggest new protocol trigger phrases from logs."""

    def __init__(
        self, logger: Optional[JarvisLogger] = None, db_path: str = LOG_DB_PATH
    ) -> None:
        super().__init__("TriggerPhraseSuggester", logger)
        self.db_path = db_path

    @property
    def description(self) -> str:
        return "Analyzes logs to suggest new protocol trigger phrases"

    @property
    def capabilities(self) -> Set[str]:
        return {"suggest_trigger_phrases"}

    async def _handle_capability_request(self, message: Message) -> None:
        if message.content.get("capability") != "suggest_trigger_phrases":
            return
        phrases = await self._suggest_trigger_phrases()
        await self.send_capability_response(
            to_agent=message.from_agent,
            result={"phrases": phrases},
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def _handle_capability_response(self, message: Message) -> None:
        return None

    async def start_background_tasks(self) -> None:
        self._create_background_task(self._periodic_scan())

    async def _periodic_scan(self) -> None:
        while True:
            await self._suggest_trigger_phrases()
            await asyncio.sleep(3600)

    async def _suggest_trigger_phrases(self) -> List[str]:
        print(f"DEBUG: Starting trigger phrase suggestion from {self.db_path}")
        try:
            conn = sqlite3.connect(self.db_path)
            print("DEBUG: Connected to database")

            query = "SELECT details FROM logs WHERE action LIKE 'Trigger matched%' ORDER BY timestamp DESC LIMIT 100"
            print(f"DEBUG: Executing query: {query}")
            rows = conn.execute(query).fetchall()
            print(f"DEBUG: Retrieved {len(rows)} rows from database")

            conn.close()
            print("DEBUG: Database connection closed")

            phrases = []
            print("DEBUG: Processing rows to extract phrases")
            for i, (details,) in enumerate(rows):
                print(f"DEBUG: Processing row {i}, details: {details[:50]}...")
                if not details:
                    print(f"DEBUG: Row {i} has empty details, skipping")
                    continue
                if "Command:" in details:
                    print(f"DEBUG: Found 'Command:' in row {i}")
                    start = details.find("Command: '") + len("Command: '")
                    end = details.find("'", start)
                    print(f"DEBUG: Start position: {start}, End position: {end}")
                    if start > -1 and end > start:
                        phrase = details[start:end]
                        print(f"DEBUG: Extracted phrase: '{phrase}'")
                        phrases.append(phrase)
                    else:
                        print(f"DEBUG: Invalid positions, couldn't extract phrase")

            print(f"DEBUG: Extracted {len(phrases)} phrases total")
            # deduplicate while preserving order
            print("DEBUG: Deduplicating phrases")
            seen = set()
            unique = []
            for p in phrases:
                if p not in seen:
                    seen.add(p)
                    unique.append(p)

            print(f"DEBUG: Returning {len(unique)} unique phrases")
            return unique
        except Exception as exc:
            print(f"DEBUG: Exception occurred: {type(exc).__name__}: {str(exc)}")
            if self.logger:
                self.logger.log("ERROR", "Trigger phrase suggestion failed", str(exc))
            return []
