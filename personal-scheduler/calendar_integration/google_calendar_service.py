from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from gcsa.google_calendar import GoogleCalendar
from gcsa.event import Event as GEvent

from .calendar_service import CalendarService, Event


class GoogleCalendarService(CalendarService):
    """Google Calendar implementation using google-calendar-simple-api."""

    def __init__(self, credentials_file: str = "calendar_integration/credentials.json", calendar_id: str = "primary"):
        self.calendar = GoogleCalendar(
            default_calendar=calendar_id,
            credentials_path=credentials_file,
            token_path="calendar_integration/token.pickle",
        )

    def _to_gevent(self, event: Event) -> GEvent:
        start = self._parse_datetime(event.start)
        end = self._parse_datetime(event.end)
        return GEvent(
            summary=event.summary,
            start=start,
            end=end,
            description=event.description or None,
            timezone=event.timezone,
            event_id=event.id,
            recurrence=event.recurrence,
        )

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        # Support RFC3339 with trailing 'Z'
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)

    def add_event(self, event: Event) -> str:
        gevent = self._to_gevent(event)
        created = self.calendar.add_event(gevent)
        return created.event_id

    def update_event(self, event: Event) -> str:
        gevent = self._to_gevent(event)
        updated = self.calendar.update_event(gevent)
        return updated.event_id

    def delete_event(self, event_id: str) -> None:
        self.calendar.delete_event(event_id)

