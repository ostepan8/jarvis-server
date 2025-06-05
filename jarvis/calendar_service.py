from __future__ import annotations

import aiohttp
from datetime import date
from typing import Any, Dict, List, Optional


class CalendarService:
    """Service responsible for communicating with the calendar API."""

    def __init__(self, base_url: str = "http://localhost:8080") -> None:
        self.base_url = base_url

    async def _request(
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url) as response:
                    result = await response.json()
                    # Check for API errors
                    if result.get("status") == "error":
                        raise Exception(
                            f"API Error: {result.get('message', 'Unknown error')}"
                        )
                    return result
            if method == "POST":
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    if result.get("status") == "error":
                        raise Exception(
                            f"API Error: {result.get('message', 'Unknown error')}"
                        )
                    return result
            if method == "DELETE":
                async with session.delete(url) as response:
                    result = await response.json()
                    if result.get("status") == "error":
                        raise Exception(
                            f"API Error: {result.get('message', 'Unknown error')}"
                        )
                    return result
        return {"status": "error", "message": "Unsupported method"}

    async def get_events_by_date(self, date: str) -> Dict[str, Any]:
        """Get events for a specific date - now returns a dict matching AI expectations"""
        result = await self._request("GET", f"/events/day/{date}")
        events = result.get("data", [])

        # Format for better readability
        formatted_events = []
        for event in events:
            formatted_events.append(
                {
                    "id": event["id"],
                    "title": event["title"],
                    "time": event["time"],
                    "duration_minutes": event.get("duration", 0) // 60,
                    "description": event.get("description", ""),
                }
            )

        return {
            "date": date,
            "event_count": len(formatted_events),
            "events": formatted_events,
        }

    async def get_today_events(self) -> Dict[str, Any]:
        """Get today's events - returns dict instead of list"""
        today = date.today().strftime("%Y-%m-%d")
        return await self.get_events_by_date(today)

    async def add_event(
        self,
        title: str,
        date: str,
        time: str,
        duration_minutes: int = 60,
        description: str = "",
    ) -> Dict[str, Any]:
        """Add an event on a given date and time."""
        datetime_str = f"{date} {time}"
        data = {
            "title": title,
            "time": datetime_str,
            "duration": duration_minutes * 60,
            "description": description,
        }
        result = await self._request("POST", "/events", data)
        event = result.get("data", {})

        return {
            "success": True,
            "message": f"Event '{title}' added successfully",
            "event": {
                "id": event.get("id"),
                "title": event.get("title"),
                "time": event.get("time"),
                "duration_minutes": event.get("duration", 0) // 60,
            },
        }

    async def delete_event(self, event_id: str) -> Dict[str, Any]:
        """Delete an event and return success status"""
        try:
            await self._request("DELETE", f"/events/{event_id}")
            return {
                "success": True,
                "message": f"Event {event_id} deleted successfully",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def analyze_schedule(self, date_range: str = "today") -> Dict[str, Any]:
        """Analyze schedule and provide insights"""
        if date_range == "today":
            today_data = await self.get_today_events()
            events = today_data.get("events", [])
            total_time = sum(e.get("duration_minutes", 0) for e in events)

            return {
                "date_range": date_range,
                "total_events": len(events),
                "total_scheduled_minutes": total_time,
                "analysis": f"You have {len(events)} events today totaling {total_time} minutes",
            }
        return {"status": "error", "message": "Unsupported range"}
