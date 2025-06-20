from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
import types

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
        self.client = httpx.AsyncClient()

    async def __aenter__(self) -> "CalendarService":
        """Allow use as an async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[types.TracebackType],
    ) -> None:
        await self.close()

    def _format_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize event structure returned by the API."""
        return {
            "id": event.get("id"),
            "title": event.get("title"),
            "time": event.get("time"),
            "duration_minutes": event.get("duration", 0) // 60,
            "description": event.get("description", ""),
            "category": event.get("category", ""),
        }

    def _format_time_slot(self, slot: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize free/busy slot data."""
        return {
            "start": slot.get("start"),
            "end": slot.get("end"),
            "duration_minutes": slot.get("duration", 0) // 60,
        }

    def current_date(self) -> str:
        """Return the current date as YYYY-MM-DD."""
        return date.today().strftime("%Y-%m-%d")

    def current_month(self) -> str:
        """Return the current month as YYYY-MM."""
        return date.today().strftime("%Y-%m")

    def format_datetime(self, dt: datetime) -> str:
        """Format datetime for API consumption."""
        return dt.strftime("%Y-%m-%d %H:%M")

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
        response = await self.client.request(method, url, params=params, json=json)
        result = response.json()
        if result.get("status") == "error":
            raise Exception(result.get("message", "Unknown error"))
        self.logger.log("INFO", "API response", str(result))
        return result

    async def get_events_by_date(self, date: str) -> Dict[str, Any]:
        """Get events for a specific date."""
        result = await self._request("GET", f"/events/day/{date}")
        self.logger.log("INFO", "Fetched events", str(result))
        events = result.get("data", [])

        formatted_events = [self._format_event(event) for event in events]

        return {
            "date": date,
            "event_count": len(formatted_events),
            "events": formatted_events,
        }

    async def get_today_events(self) -> Dict[str, Any]:
        """Get today's events."""
        today = self.current_date()
        return await self.get_events_by_date(today)

    async def get_tomorrow_events(self) -> Dict[str, Any]:
        """Get tomorrow's events."""
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        return await self.get_events_by_date(tomorrow)

    async def get_week_events(self, start_date: Optional[str] = None) -> Dict[str, Any]:
        """Get events for a week starting from the given date (or current week)."""
        if start_date is None:
            today = date.today()
            start = today - timedelta(days=today.weekday())
            start_date = start.strftime("%Y-%m-%d")

        result = await self._request("GET", f"/events/week/{start_date}")
        events = result.get("data", [])

        formatted_events = [self._format_event(event) for event in events]

        # Group events by day
        events_by_day = {}
        for event in formatted_events:
            event_date = event["time"].split(" ")[0]
            if event_date not in events_by_day:
                events_by_day[event_date] = []
            events_by_day[event_date].append(event)

        return {
            "week_start": start_date,
            "total_events": len(formatted_events),
            "events": formatted_events,
            "events_by_day": events_by_day,
        }

    async def get_month_events(
        self, year_month: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get events for a specific month (YYYY-MM format)."""
        if year_month is None:
            year_month = self.current_month()

        result = await self._request("GET", f"/events/month/{year_month}")
        events = result.get("data", [])

        formatted_events = [self._format_event(event) for event in events]

        # Group events by day
        events_by_day = {}
        for event in formatted_events:
            event_date = event["time"].split(" ")[0]
            if event_date not in events_by_day:
                events_by_day[event_date] = []
            events_by_day[event_date].append(event)

        return {
            "month": year_month,
            "total_events": len(formatted_events),
            "events": formatted_events,
            "events_by_day": events_by_day,
            "days_with_events": len(events_by_day),
        }

    # ===== NEW ROUTES: SEARCH AND FILTERING =====

    async def search_events(
        self, query: str, max_results: Optional[int] = None
    ) -> Dict[str, Any]:
        """Search events by query string."""
        params = {"q": query}
        if max_results is not None:
            params["max"] = max_results

        result = await self._request("GET", "/events/search", params=params)
        events = result.get("data", [])
        formatted_events = [self._format_event(event) for event in events]

        return {
            "query": query,
            "result_count": len(formatted_events),
            "events": formatted_events,
        }

    async def get_events_in_range(
        self, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """Get events within a date range."""
        result = await self._request("GET", f"/events/range/{start_date}/{end_date}")
        events = result.get("data", [])
        formatted_events = [self._format_event(event) for event in events]

        return {
            "start_date": start_date,
            "end_date": end_date,
            "event_count": len(formatted_events),
            "events": formatted_events,
        }

    async def get_events_by_duration(
        self, min_minutes: Optional[int] = None, max_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get events filtered by duration."""
        params = {}
        if min_minutes is not None:
            params["min"] = min_minutes
        if max_minutes is not None:
            params["max"] = max_minutes

        result = await self._request("GET", "/events/duration", params=params)
        events = result.get("data", [])
        formatted_events = [self._format_event(event) for event in events]

        return {
            "min_minutes": min_minutes,
            "max_minutes": max_minutes,
            "event_count": len(formatted_events),
            "events": formatted_events,
        }

    # ===== CATEGORIES =====

    async def get_categories(self) -> Dict[str, Any]:
        """Get all event categories."""
        result = await self._request("GET", "/categories")
        categories = result.get("data", [])

        return {
            "category_count": len(categories),
            "categories": categories,
        }

    async def get_events_by_category(self, category: str) -> Dict[str, Any]:
        """Get events filtered by category."""
        result = await self._request("GET", f"/events/category/{category}")
        events = result.get("data", [])
        formatted_events = [self._format_event(event) for event in events]

        return {
            "category": category,
            "event_count": len(formatted_events),
            "events": formatted_events,
        }

    # ===== CONFLICTS AND FREE TIME =====

    async def check_conflicts(
        self, time: str, duration_minutes: int = 60
    ) -> Dict[str, Any]:
        """Check if there are conflicts at a specific time."""
        params = {
            "time": time,
            "duration": duration_minutes,
        }

        result = await self._request("GET", "/events/conflicts", params=params)
        conflicts = result.get("data", [])
        has_conflicts = result.get("has_conflicts", False)
        formatted_conflicts = [self._format_event(event) for event in conflicts]

        return {
            "time": time,
            "duration_minutes": duration_minutes,
            "has_conflicts": has_conflicts,
            "conflict_count": len(formatted_conflicts),
            "conflicts": formatted_conflicts,
        }

    async def validate_event_time(
        self,
        time: str,
        duration_seconds: int = 3600,
        title: str = "Test Event",
    ) -> Dict[str, Any]:
        """Validate if an event can be scheduled at a specific time."""
        data = {
            "time": time,
            "duration": duration_seconds,
            "title": title,
        }

        result = await self._request("POST", "/events/validate", json=data)
        valid = result.get("valid", False)
        conflicts = result.get("conflicts", [])

        return {
            "time": time,
            "duration_seconds": duration_seconds,
            "valid": valid,
            "conflicts": [self._format_event(event) for event in conflicts],
        }

    async def find_free_slots(
        self,
        date: Optional[str] = None,
        start_hour: Optional[int] = None,
        end_hour: Optional[int] = None,
        min_duration_minutes: int = 30,
    ) -> Dict[str, Any]:
        """
        Finds free slots on a specific date:
        • date:            YYYY-MM-DD (defaults to today)
        • start_hour:      integer 0–23 (defaults to current hour)
        • end_hour:        integer 0–23 (defaults to 17)
        • min_duration:    in minutes (defaults to 30)
        """
        now = datetime.now()

        if date is None:
            date = now.strftime("%Y-%m-%d")

        if start_hour is None:
            start_hour = now.hour

        if end_hour is None:
            # if you really want to check TWO WEEKS OUT, call this
            # function again with date = (now + timedelta(weeks=2)).strftime("%Y-%m-%d")
            end_hour = 17

        params = {
            "start": start_hour,
            "end": end_hour,
            "duration": min_duration_minutes,
        }

        result = await self._request("GET", f"/free-slots/{date}", params=params)
        slots = result.get("data", [])
        formatted = [self._format_time_slot(s) for s in slots]

        return {
            "date": date,
            "working_hours": f"{start_hour:02d}:00-{end_hour:02d}:00",
            "min_duration_minutes": min_duration_minutes,
            "free_slots_count": len(formatted),
            "free_slots": formatted,
        }

    async def find_next_available_slot(
        self, duration_minutes: int = 60, after: Optional[str] = None
    ) -> Dict[str, Any]:
        """Find the next available time slot."""
        params = {"duration": duration_minutes}
        if after is not None:
            params["after"] = after

        result = await self._request("GET", "/free-slots/next", params=params)
        slot = result.get("data", {})

        return {
            "duration_minutes": duration_minutes,
            "after": after or "now",
            "slot": self._format_time_slot(slot) if slot else None,
        }

    # ===== STATISTICS =====

    async def get_event_stats(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Get statistics for events in a date range."""
        result = await self._request("GET", f"/stats/events/{start_date}/{end_date}")
        stats = result.get("data", {})

        # Format the response
        formatted_stats = {
            "start_date": start_date,
            "end_date": end_date,
            "total_events": stats.get("total_events", 0),
            "total_minutes": stats.get("total_minutes", 0),
            "events_by_category": stats.get("events_by_category", {}),
            "busiest_days": [
                {
                    "date": day["date"],
                    "event_count": day["event_count"],
                }
                for day in stats.get("busiest_days", [])
            ],
            "busiest_hours": [
                {
                    "hour": hour["hour"],
                    "event_count": hour["event_count"],
                }
                for hour in stats.get("busiest_hours", [])
            ],
        }

        return formatted_stats

    # ===== UPDATE OPERATIONS =====

    async def update_event(
        self,
        event_id: str,
        title: str,
        time: str,
        duration_seconds: int = 3600,
        description: str = "",
        category: str = "",
    ) -> Dict[str, Any]:
        """Update an entire event (PUT)."""
        data = {
            "title": title,
            "time": time,
            "duration": duration_seconds,
            "description": description,
            "category": category,
        }

        result = await self._request("PUT", f"/events/{event_id}", json=data)
        event = result.get("data", {})

        return {
            "success": True,
            "message": f"Event '{title}' updated successfully",
            "event": self._format_event(event),
        }

    async def update_event_fields(
        self, event_id: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update specific fields of an event (PATCH)."""
        result = await self._request("PATCH", f"/events/{event_id}", json=fields)
        event = result.get("data", {})

        return {
            "success": True,
            "message": f"Event {event_id} fields updated successfully",
            "updated_fields": list(fields.keys()),
            "event": self._format_event(event),
        }

    # ===== BULK OPERATIONS =====

    async def add_events_bulk(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add multiple events at once."""
        # Format events for API
        formatted_events = []
        for event in events:
            formatted_event = {
                "title": event["title"],
                "time": event["time"],
                "duration": event.get("duration_seconds", 3600),
                "description": event.get("description", ""),
            }
            if "category" in event:
                formatted_event["category"] = event["category"]
            formatted_events.append(formatted_event)

        data = {"events": formatted_events}
        result = await self._request("POST", "/events/bulk", json=data)
        response_data = result.get("data", {})

        return {
            "success": True,
            "total": response_data.get("total", 0),
            "successful": response_data.get("successful", 0),
            "results": response_data.get("results", []),
        }

    async def delete_events_bulk(self, event_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple events at once."""
        data = {"ids": event_ids}
        result = await self._request("DELETE", "/events/bulk", json=data)

        return {
            "success": True,
            "removed": result.get("removed", 0),
            "requested": result.get("requested", len(event_ids)),
        }

    async def delete_events_by_date(self, date: str) -> Dict[str, Any]:
        """Delete all events on a specific date."""
        try:
            result = await self._request("DELETE", f"/events/day/{date}")
            removed_count = result.get("removed", 0)
            self.logger.log("INFO", f"Deleted {removed_count} events on date", date)
            return {
                "success": True,
                "message": f"Deleted {removed_count} events on {date}",
                "removed_count": removed_count,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def delete_events_in_week(self, start_date: str) -> Dict[str, Any]:
        """Delete all events in a week starting from the given date."""
        try:
            result = await self._request("DELETE", f"/events/week/{start_date}")
            removed_count = result.get("removed", 0)
            self.logger.log(
                "INFO", f"Deleted {removed_count} events in week", start_date
            )
            return {
                "success": True,
                "message": f"Deleted {removed_count} events in week starting {start_date}",
                "removed_count": removed_count,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def delete_events_before(self, datetime_str: str) -> Dict[str, Any]:
        """Delete all events before a specific datetime (format: YYYY-MM-DDTHH:MM)."""
        try:
            result = await self._request("DELETE", f"/events/before/{datetime_str}")
            removed_count = result.get("removed", 0)
            self.logger.log(
                "INFO", f"Deleted {removed_count} events before", datetime_str
            )
            return {
                "success": True,
                "message": f"Deleted {removed_count} events before {datetime_str}",
                "removed_count": removed_count,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ===== SOFT DELETE AND RESTORE =====

    async def get_deleted_events(self) -> Dict[str, Any]:
        """Get all soft-deleted events."""
        result = await self._request("GET", "/events/deleted")
        events = result.get("data", [])
        formatted_events = [self._format_event(event) for event in events]

        return {
            "deleted_count": len(formatted_events),
            "events": formatted_events,
        }

    async def restore_event(self, event_id: str) -> Dict[str, Any]:
        """Restore a soft-deleted event."""
        try:
            result = await self._request("POST", f"/events/{event_id}/restore")
            return {
                "success": True,
                "message": result.get("message", "Event restored successfully"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ===== ENHANCED DELETE OPERATIONS =====

    async def delete_event(
        self, event_id: str, soft_delete: bool = False
    ) -> Dict[str, Any]:
        """Delete an event (with optional soft delete)."""
        try:
            params = {"soft": "true"} if soft_delete else None
            await self._request("DELETE", f"/events/{event_id}", params=params)
            self.logger.log("INFO", f"Deleted event (soft={soft_delete})", event_id)
            return {
                "success": True,
                "message": f"Event {event_id} {'soft' if soft_delete else 'permanently'} deleted successfully",
                "soft_delete": soft_delete,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ===== ORIGINAL METHODS (kept for compatibility) =====

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
            "event": self._format_event(event),
        }

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
        elif date_range == "week":
            week_data = await self.get_week_events()
            events = week_data.get("events", [])
            total_time = sum(e.get("duration_minutes", 0) for e in events)

            return {
                "date_range": date_range,
                "week_start": week_data.get("week_start"),
                "total_events": len(events),
                "total_scheduled_minutes": total_time,
                "days_with_events": len(week_data.get("events_by_day", {})),
                "analysis": f"You have {len(events)} events this week totaling {total_time} minutes across {len(week_data.get('events_by_day', {}))} days",
                "events_by_day": week_data.get("events_by_day", {}),
            }
        elif date_range == "month":
            month_data = await self.get_month_events()
            events = month_data.get("events", [])
            total_time = sum(e.get("duration_minutes", 0) for e in events)

            return {
                "date_range": date_range,
                "month": month_data.get("month"),
                "total_events": len(events),
                "total_scheduled_minutes": total_time,
                "days_with_events": month_data.get("days_with_events", 0),
                "analysis": f"You have {len(events)} events this month totaling {total_time} minutes across {month_data.get('days_with_events', 0)} days",
            }
        return {"status": "error", "message": "Unsupported range"}

    # ------------------------------------------------------------------
    # Additional API wrappers for new C++ routes
    # ------------------------------------------------------------------

    async def get_all_events(self) -> List[Dict[str, Any]]:
        result = await self._request("GET", "/events")
        events = result.get("data", [])
        return [self._format_event(e) for e in events]

    async def get_next_event(self) -> Optional[Dict[str, Any]]:
        result = await self._request("GET", "/events/next")
        event = result.get("data")
        return self._format_event(event) if event else None

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

    async def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Return a single event by its ID if found."""
        events = await self.get_all_events()
        for ev in events:
            if ev.get("id") == event_id:
                return self._format_event(ev)
        return None

    async def get_busy_days(
        self, start_date: str, end_date: str, threshold_events: int = 3
    ) -> List[Dict[str, Any]]:
        """Return days within the range that have many events."""
        events = await self.get_events_in_range(start_date, end_date)
        counts: Dict[str, int] = {}
        for ev in events:
            day = ev["time"].split(" ")[0]
            counts[day] = counts.get(day, 0) + 1
        busy = [
            {"date": day, "event_count": count}
            for day, count in counts.items()
            if count >= threshold_events
        ]
        busy.sort(key=lambda d: d["event_count"], reverse=True)
        return busy

    async def get_overlapping_events(self) -> List[Dict[str, Any]]:
        """Find all overlapping events."""
        events = [self._format_event(e) for e in await self.get_all_events()]
        overlaps = []
        for i, ev1 in enumerate(events):
            start1 = datetime.strptime(ev1["time"], "%Y-%m-%d %H:%M")
            end1 = start1 + timedelta(minutes=ev1["duration_minutes"])
            for ev2 in events[i + 1 :]:
                start2 = datetime.strptime(ev2["time"], "%Y-%m-%d %H:%M")
                end2 = start2 + timedelta(minutes=ev2["duration_minutes"])
                if start1 < end2 and start2 < end1:
                    overlaps.append({"event1": ev1, "event2": ev2})
        return overlaps

    async def find_best_time_for_event(
        self,
        duration_minutes: int,
        preferred_dates: List[str],
        working_hours: Tuple[int, int] = (9, 17),
    ) -> Optional[Dict[str, Any]]:
        """Return the first free slot matching preferences."""
        start_h, end_h = working_hours
        for day in preferred_dates:
            slot_info = await self.find_free_slots(
                date=day,
                start_hour=start_h,
                end_hour=end_h,
                min_duration_minutes=duration_minutes,
            )
            free_slots = slot_info.get("free_slots") or []
            if free_slots:
                return free_slots[0]
        return None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()
