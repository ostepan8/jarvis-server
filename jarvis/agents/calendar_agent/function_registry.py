# jarvis/agents/calendar_agent/function_registry.py
from typing import Dict, Callable
from ...services.calendar_service import CalendarService
from ...registry import FunctionRegistry


class CalendarFunctionRegistry(FunctionRegistry):
    """Unified registry for calendar functions and capabilities"""

    def __init__(self, calendar_service: CalendarService):
        self.calendar_service = calendar_service
        super().__init__(self._build_function_map())

    def _build_function_map(self) -> Dict[str, Callable]:
        """Build the mapping of function names to calendar service methods"""
        return {
            # Basic event operations
            "get_all_events": self.calendar_service.get_all_events,
            "get_next_event": self.calendar_service.get_next_event,
            "get_today_events": self.calendar_service.get_today_events,
            "get_tomorrow_events": self.calendar_service.get_tomorrow_events,
            "get_events_by_date": self.calendar_service.get_events_by_date,
            "get_week_events": self.calendar_service.get_week_events,
            "get_month_events": self.calendar_service.get_month_events,
            # Search and filtering
            "search_events": self.calendar_service.search_events,
            "get_events_in_range": self.calendar_service.get_events_in_range,
            "get_events_by_duration": self.calendar_service.get_events_by_duration,
            # Categories
            "get_categories": self.calendar_service.get_categories,
            "get_events_by_category": self.calendar_service.get_events_by_category,
            # Conflicts and free time
            "check_conflicts": self.calendar_service.check_conflicts,
            "validate_event_time": self.calendar_service.validate_event_time,
            "find_free_slots": self.calendar_service.find_free_slots,
            "find_next_available_slot": self.calendar_service.find_next_available_slot,
            # Statistics
            "get_event_stats": self.calendar_service.get_event_stats,
            # Create/Update operations
            "add_event": self.calendar_service.add_event,
            "update_event": self.calendar_service.update_event,
            "update_event_fields": self.calendar_service.update_event_fields,
            "reschedule_event": self.calendar_service.reschedule_event,
            # Recurring events
            "get_recurring_events": self.calendar_service.get_recurring_events,
            "add_recurring_event": self.calendar_service.add_recurring_event,
            "update_recurring_event": self.calendar_service.update_recurring_event,
            "delete_recurring_event": self.calendar_service.delete_recurring_event,
            # Bulk operations
            "add_events_bulk": self.calendar_service.add_events_bulk,
            "delete_events_bulk": self.calendar_service.delete_events_bulk,
            # Delete operations
            "delete_event": self.calendar_service.delete_event,
            "delete_all_events": self.calendar_service.delete_all_events,
            "delete_events_by_date": self.calendar_service.delete_events_by_date,
            "delete_events_in_week": self.calendar_service.delete_events_in_week,
            "delete_events_before": self.calendar_service.delete_events_before,
            # Soft delete and restore
            "get_deleted_events": self.calendar_service.get_deleted_events,
            "restore_event": self.calendar_service.restore_event,
            # Summary and analysis
            "get_schedule_summary": self.calendar_service.get_schedule_summary,
            "get_busy_days": self.calendar_service.get_busy_days,
            "get_overlapping_events": self.calendar_service.get_overlapping_events,
            # Advanced helpers
            "find_best_time_for_event": self.calendar_service.find_best_time_for_event,
            "get_event_by_id": self.calendar_service.get_event_by_id,
            # Capability aliases (map user-friendly names to function names)
            "view_calendar_schedule": self.calendar_service.get_all_events,
            "view_calendar_events": self.calendar_service.get_all_events,
            "search_calendar_events": self.calendar_service.search_events,
            "get_calendar_statistics": self.calendar_service.get_event_stats,
            "view_upcoming_appointments": self.calendar_service.get_next_event,
            "check_calendar_availability": self.calendar_service.find_free_slots,
            "schedule_appointment": self.calendar_service.add_event,
            "update_calendar_event": self.calendar_service.update_event,
            "reschedule_appointment": self.calendar_service.reschedule_event,
            "remove_calendar_event": self.calendar_service.delete_event,
            "cancel_appointment": self.calendar_service.delete_event,
            "bulk_calendar_operations": self.calendar_service.add_events_bulk,
            "find_free_time_slots": self.calendar_service.find_free_slots,
            "check_scheduling_conflicts": self.calendar_service.check_conflicts,
            "analyze_calendar_patterns": self.calendar_service.get_event_stats,
            "find_meeting_times": self.calendar_service.find_best_time_for_event,
            "manage_event_categories": self.calendar_service.get_categories,
            "restore_deleted_appointments": self.calendar_service.restore_event,
            "organize_calendar": self.calendar_service.get_schedule_summary,
            "get_today_schedule": self.calendar_service.get_today_events,
            "get_week_schedule": self.calendar_service.get_week_events,
            "get_month_schedule": self.calendar_service.get_month_events,
            "check_busy_days": self.calendar_service.get_busy_days,
        }

