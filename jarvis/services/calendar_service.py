from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from ..logger import JarvisLogger


class CalendarService:
    """Service responsible for communicating with the calendar API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        logger: JarvisLogger | None = None,
    ) -> None:
        self.base_url = base_url
        self.logger = logger or JarvisLogger()

    def current_date(self) -> str:
        """Return the current date as YYYY-MM-DD."""
        return date.today().strftime("%Y-%m-%d")

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Internal helper to perform an HTTP request to the calendar API."""
        url = f"{self.base_url}{endpoint}"
        self.logger.log(
            "INFO",
            "API request",
            f"{method} {url} params={params} json={json}",
        )
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, params=params, json=json)
        result = response.json()
        if result.get("status") == "error":
            raise Exception(result.get("message", "Unknown error"))
        self.logger.log("INFO", "API response", str(result))
        return result

    async def get_events_by_date(self, date: str) -> Dict[str, Any]:
        """Get events for a specific date - now returns a dict matching AI expectations"""
        result = await self._request("GET", f"/events/day/{date}")
        self.logger.log("INFO", "Fetched events", str(result))
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
        today = self.current_date()
        return await self.get_events_by_date(today)

    async def add_event(
        self,
        title: str,
        date: str,
        time: str,
        duration_minutes: int = 60,
        description: str = "",
        category: str = "",
    ) -> Dict[str, Any]:
        """Add an event on a given date and time."""
        datetime_str = f"{date} {time}"
        data = {
            "title": title,
            "time": datetime_str,
            "duration": duration_minutes * 60,
            "description": description,
            "category": category,
        }
        result = await self._request("POST", "/events", json=data)
        event = result.get("data", {})
        self.logger.log("INFO", "Added event", str(event))

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

    async def delete_event(self, event_id: str, soft: bool = False) -> Dict[str, Any]:
        """Delete an event and return success status."""
        try:
            params = {"soft": "true"} if soft else None
            await self._request("DELETE", f"/events/{event_id}", params=params)
            self.logger.log("INFO", "Deleted event", event_id)
            return {
                "success": True,
                "message": f"Event {event_id} deleted successfully",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_schedule_summary(self, date_range: str = "today") -> Dict[str, Any]:
        """Return a summary of the schedule for the given range."""
        if date_range == "today":
            today_data = await self.get_today_events()
            events = today_data.get("events", [])
            total_time = sum(e.get("duration_minutes", 0) for e in events)

            result = {
                "date_range": date_range,
                "total_events": len(events),
                "total_scheduled_minutes": total_time,
                "analysis": f"You have {len(events)} events today totaling {total_time} minutes",
                "events": events,
            }
            self.logger.log("INFO", "Schedule summary", str(result))
            return result
        return {"status": "error", "message": "Unsupported range"}

    # ------------------------------------------------------------------
    # Additional API wrappers for new C++ routes
    # ------------------------------------------------------------------

    async def get_all_events(self) -> List[Dict[str, Any]]:
        result = await self._request("GET", "/events")
        return result.get("data", [])

    async def get_next_event(self) -> Optional[Dict[str, Any]]:
        result = await self._request("GET", "/events/next")
        return result.get("data")

    async def get_tomorrow_events(self) -> Dict[str, Any]:
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        return await self.get_events_by_date(tomorrow)

    async def get_week_events(self, start_date: str) -> List[Dict[str, Any]]:
        result = await self._request("GET", f"/events/week/{start_date}")
        return result.get("data", [])

    async def get_month_events(self, month: str) -> List[Dict[str, Any]]:
        result = await self._request("GET", f"/events/month/{month}")
        return result.get("data", [])

    async def search_events(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        params = {"q": query}
        if max_results is not None:
            params["max"] = max_results
        result = await self._request("GET", "/events/search", params=params)
        return result.get("data", [])

    async def get_events_in_range(self, start: str, end: str) -> List[Dict[str, Any]]:
        result = await self._request("GET", f"/events/range/{start}/{end}")
        return result.get("data", [])

    async def get_events_by_duration(
        self, min_minutes: int = 0, max_minutes: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"min": min_minutes}
        if max_minutes is not None:
            params["max"] = max_minutes
        result = await self._request("GET", "/events/duration", params=params)
        return result.get("data", [])

    async def get_categories(self) -> List[str]:
        result = await self._request("GET", "/categories")
        return result.get("data", [])

    async def get_events_by_category(self, category: str) -> List[Dict[str, Any]]:
        result = await self._request("GET", f"/events/category/{category}")
        return result.get("data", [])

    async def check_conflicts(self, time: str, duration_minutes: int = 60) -> Dict[str, Any]:
        params = {"time": time, "duration": duration_minutes}
        return await self._request("GET", "/events/conflicts", params=params)

    async def validate_event_time(
        self, time: str, duration_minutes: int = 60, title: str = "Test Event"
    ) -> Dict[str, Any]:
        payload = {"time": time, "duration": duration_minutes, "title": title}
        return await self._request("POST", "/events/validate", json=payload)

    async def find_free_slots(
        self,
        date_str: str,
        start_hour: int = 9,
        end_hour: int = 17,
        min_duration: int = 30,
    ) -> List[Dict[str, Any]]:
        params = {"start": start_hour, "end": end_hour, "duration": min_duration}
        result = await self._request("GET", f"/free-slots/{date_str}", params=params)
        return result.get("data", [])

    async def find_next_available_slot(
        self, duration_minutes: int = 60, after: Optional[str] = None
    ) -> Dict[str, Any]:
        params = {"duration": duration_minutes}
        if after:
            params["after"] = after
        result = await self._request("GET", "/free-slots/next", params=params)
        return result.get("data", {})

    async def update_event(
        self,
        event_id: str,
        title: str,
        time: str,
        duration_minutes: int,
        description: str = "",
        category: str = "",
    ) -> Dict[str, Any]:
        payload = {
            "title": title,
            "time": time,
            "duration": duration_minutes * 60,
            "description": description,
            "category": category,
        }
        result = await self._request("PUT", f"/events/{event_id}", json=payload)
        return result.get("data", {})

    async def update_event_fields(self, event_id: str, **fields: Any) -> Dict[str, Any]:
        if "duration" in fields:
            fields["duration"] = fields["duration"] * 60
        result = await self._request("PATCH", f"/events/{event_id}", json=fields)
        return result.get("data", {})

    async def reschedule_event(
        self, event_id: str, new_time: str, duration_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        payload = {"time": new_time}
        if duration_minutes is not None:
            payload["duration"] = duration_minutes * 60
        result = await self._request("PATCH", f"/events/{event_id}", json=payload)
        return result.get("data", {})

    async def get_recurring_events(self) -> List[Dict[str, Any]]:
        result = await self._request("GET", "/recurring")
        return result.get("data", [])

    async def add_recurring_event(
        self,
        title: str,
        start: str,
        duration_minutes: int,
        pattern: Dict[str, Any],
        description: str = "",
        category: str = "",
    ) -> Dict[str, Any]:
        payload = {
            "title": title,
            "start": start,
            "duration": duration_minutes * 60,
            "pattern": pattern,
            "description": description,
            "category": category,
        }
        result = await self._request("POST", "/recurring", json=payload)
        return result.get("data", {})

    async def update_recurring_event(
        self,
        event_id: str,
        title: str,
        start: str,
        duration_minutes: int,
        pattern: Dict[str, Any],
        description: str = "",
        category: str = "",
    ) -> Dict[str, Any]:
        payload = {
            "title": title,
            "start": start,
            "duration": duration_minutes * 60,
            "pattern": pattern,
            "description": description,
            "category": category,
        }
        result = await self._request("PUT", f"/recurring/{event_id}", json=payload)
        return result.get("data", {})

    async def delete_recurring_event(self, event_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/recurring/{event_id}")

    async def delete_all_events(self) -> Dict[str, Any]:
        return await self._request("DELETE", "/events")

    async def delete_events_by_date(self, day: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/events/day/{day}")

    async def delete_events_in_week(self, day: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/events/week/{day}")

    async def delete_events_before(self, timestamp: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/events/before/{timestamp}")

    async def get_deleted_events(self) -> List[Dict[str, Any]]:
        result = await self._request("GET", "/events/deleted")
        return result.get("data", [])

    async def restore_event(self, event_id: str) -> Dict[str, Any]:
        return await self._request("POST", f"/events/{event_id}/restore")

    async def add_events_bulk(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for event in events:
            results.append(await self.add_event(**event))
        return results

    async def get_event_stats(self, start: str, end: str) -> Dict[str, Any]:
        result = await self._request("GET", f"/stats/events/{start}/{end}")
        return result.get("data", {})
