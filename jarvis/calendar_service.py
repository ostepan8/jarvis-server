from __future__ import annotations

import aiohttp
from datetime import date
from typing import Any, Dict, List, Optional


class CalendarService:
    """Service responsible for communicating with the calendar API."""

    def __init__(self, base_url: str = "http://localhost:8080") -> None:
        self.base_url = base_url

    async def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url) as response:
                    return await response.json()
            if method == "POST":
                async with session.post(url, json=data) as response:
                    return await response.json()
            if method == "DELETE":
                async with session.delete(url) as response:
                    return await response.json()
        return {"status": "error", "message": "Unsupported method"}

    async def get_events_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        result = await self._request("GET", f"/events/day/{date_str}")
        return result.get("data", [])

    async def get_today_events(self) -> List[Dict[str, Any]]:
        today = date.today().strftime("%Y-%m-%d")
        return await self.get_events_by_date(today)

    async def add_event(self, title: str, date: str, time: str, duration_minutes: int = 60, description: str = "") -> Dict[str, Any]:
        """Add an event on a given date and time."""
        datetime_str = f"{date} {time}"
        data = {
            "title": title,
            "time": datetime_str,
            "duration": duration_minutes * 60,
            "description": description,
        }
        return await self._request("POST", "/events", data)

    async def delete_event(self, event_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/events/{event_id}")

    async def analyze_schedule(self, date_range: str = "today") -> Dict[str, Any]:
        if date_range == "today":
            events = await self.get_today_events()
            total_time = sum(e.get("duration", 0) // 60 for e in events)
            return {
                "date_range": date_range,
                "total_events": len(events),
                "total_scheduled_minutes": total_time,
                "analysis": f"You have {len(events)} events today totaling {total_time} minutes",
            }
        return {"status": "error", "message": "Unsupported range"}
