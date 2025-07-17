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

    def __init__(self, logger: Optional[JarvisLogger] = None, db_path: str = LOG_DB_PATH) -> None:
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
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                "SELECT details FROM logs WHERE action LIKE 'Trigger matched%' ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()
            conn.close()
            phrases = []
            for (details,) in rows:
                if not details:
                    continue
                if "Command:" in details:
                    start = details.find("Command: '") + len("Command: '")
                    end = details.find("'", start)
                    if start > -1 and end > start:
                        phrase = details[start:end]
                        phrases.append(phrase)
            # deduplicate while preserving order
            seen = set()
            unique = []
            for p in phrases:
                if p not in seen:
                    seen.add(p)
                    unique.append(p)
            return unique
        except Exception as exc:
            if self.logger:
                self.logger.log("ERROR", "Trigger phrase suggestion failed", str(exc))
            return []
