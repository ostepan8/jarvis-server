# jarvis/services/canvas_service.py

import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import httpx
from ..logging import JarvisLogger


class CanvasService:
    """
    Service layer for interacting with the Canvas LMS REST API.
    Reads CANVAS_API_URL and CANVAS_API_TOKEN (and optionally CANVAS_ACCOUNT_ID)
    from the environment by default.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        account_id: Optional[str] = None,
        logger: Optional[JarvisLogger] = None,
    ):
        self.logger = logger or JarvisLogger()

        # Log what we're getting from environment
        env_url = os.getenv("CANVAS_API_URL")
        env_token = os.getenv("CANVAS_API_TOKEN")
        env_account = os.getenv("CANVAS_ACCOUNT_ID")

        self.logger.log(
            "INFO",
            "Canvas environment check",
            {
                "env_url": env_url,
                "env_token": "***" if env_token else None,
                "env_account": env_account,
                "provided_url": base_url,
                "provided_token": "***" if api_token else None,
            },
        )

        self.base_url = (
            base_url or env_url or "https://<your-school>.instructure.com/api/v1"
        )

        self.token = api_token or env_token

        # Log final configuration
        self.logger.log(
            "INFO",
            "Canvas service initialized",
            {
                "base_url": self.base_url,
                "has_token": bool(self.token),
                "account_id": account_id or env_account,
            },
        )

        if not self.token:
            error_msg = "Canvas API token not provided. Set CANVAS_API_TOKEN."
            self.logger.log("ERROR", "Canvas initialization failed", error_msg)
            raise ValueError(error_msg)

        # Check if URL looks invalid
        if "<your-school>" in self.base_url:
            error_msg = f"Canvas URL appears to be placeholder: {self.base_url}"
            self.logger.log("ERROR", "Canvas URL invalid", error_msg)
            raise ValueError(error_msg)

        self.account_id = account_id or env_account
        headers = {"Authorization": f"Bearer {self.token}"}
        self.client = httpx.AsyncClient(headers=headers)

    def _filter_course_data(
        self, courses: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter course data to only include essential fields."""
        filtered_courses = []

        for course in courses:
            # Only keep essential fields
            filtered_course = {
                "id": course.get("id"),
                "name": course.get("name"),
                "course_code": course.get("course_code"),
                "workflow_state": course.get("workflow_state"),
                "enrollment_term_id": course.get("enrollment_term_id"),
                "start_at": course.get("start_at"),
                "end_at": course.get("end_at"),
                "enrollments": course.get("enrollments", []),
                "html_url": course.get("html_url"),
                "created_at": course.get("created_at"),
                "updated_at": course.get("updated_at"),
            }

            filtered_courses.append(filtered_course)

        return filtered_courses

    def _filter_assignment_data(
        self, assignments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter assignment data to only include essential fields."""
        filtered_assignments = []

        for assignment in assignments:
            # Only keep essential fields
            filtered_assignment = {
                "id": assignment.get("id"),
                "name": assignment.get("name"),
                "course_id": assignment.get("course_id"),
                "due_at": assignment.get("due_at"),
                "unlock_at": assignment.get("unlock_at"),
                "lock_at": assignment.get("lock_at"),
                "points_possible": assignment.get("points_possible"),
                "grading_type": assignment.get("grading_type"),
                "workflow_state": assignment.get("workflow_state"),
                "published": assignment.get("published", True),
                "locked_for_user": assignment.get("locked_for_user", False),
                "submission_types": assignment.get("submission_types", []),
                "has_submitted_submissions": assignment.get(
                    "has_submitted_submissions", False
                ),
                "html_url": assignment.get("html_url"),
                "created_at": assignment.get("created_at"),
                "updated_at": assignment.get("updated_at"),
            }

            # Include description but truncate it to avoid token bloat
            description = assignment.get("description")
            if description:
                # Remove HTML tags and truncate
                import re

                clean_description = re.sub(r"<[^>]+>", "", description)
                if len(clean_description) > 300:
                    filtered_assignment["description"] = clean_description[:300] + "..."
                else:
                    filtered_assignment["description"] = clean_description

            filtered_assignments.append(filtered_assignment)

        return filtered_assignments

    def _filter_calendar_events(
        self, events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter calendar events to only include essential fields."""
        filtered_events = []

        for event in events:
            filtered_event = {
                "id": event.get("id"),
                "title": event.get("title"),
                "description": (
                    event.get("description", "")[:200]
                    if event.get("description")
                    else None
                ),
                "start_at": event.get("start_at"),
                "end_at": event.get("end_at"),
                "location_name": event.get("location_name"),
                "context_code": event.get("context_code"),
                "workflow_state": event.get("workflow_state"),
                "html_url": event.get("html_url"),
            }

            # Remove None values to reduce payload size
            filtered_event = {k: v for k, v in filtered_event.items() if v is not None}
            filtered_events.append(filtered_event)

        return filtered_events

    def _filter_todo_items(self, todos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter todo items to only include essential fields."""
        filtered_todos = []

        for todo in todos:
            filtered_todo = {
                "type": todo.get("type"),
                "assignment": todo.get("assignment"),
                "quiz": todo.get("quiz"),
                "context_type": todo.get("context_type"),
                "context_name": todo.get("context_name"),
                "course_id": todo.get("course_id"),
                "html_url": todo.get("html_url"),
                "ignore": todo.get("ignore"),
                "needs_grading_count": todo.get("needs_grading_count"),
                "visible_in_planner": todo.get("visible_in_planner", True),
            }

            # Remove None values to reduce payload size
            filtered_todo = {k: v for k, v in filtered_todo.items() if v is not None}
            filtered_todos.append(filtered_todo)

        return filtered_todos

    def _filter_conversations(
        self, conversations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter conversations to only include essential fields."""
        filtered_conversations = []

        for conversation in conversations:
            filtered_conversation = {
                "id": conversation.get("id"),
                "subject": conversation.get("subject"),
                "workflow_state": conversation.get("workflow_state"),
                "last_message": conversation.get("last_message"),
                "last_message_at": conversation.get("last_message_at"),
                "message_count": conversation.get("message_count"),
                "starred": conversation.get("starred", False),
                "participants": conversation.get("participants", []),
                "context_name": conversation.get("context_name"),
            }

            # Remove None values to reduce payload size
            filtered_conversation = {
                k: v for k, v in filtered_conversation.items() if v is not None
            }
            filtered_conversations.append(filtered_conversation)

        return filtered_conversations

    def _filter_notifications(
        self, notifications: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter notifications to only include essential fields."""
        filtered_notifications = []

        for notification in notifications:
            filtered_notification = {
                "id": notification.get("id"),
                "subject": notification.get("subject"),
                "message": (
                    notification.get("message", "")[:300]
                    if notification.get("message")
                    else None
                ),
                "start_at": notification.get("start_at"),
                "end_at": notification.get("end_at"),
                "icon": notification.get("icon"),
                "roles": notification.get("roles", []),
            }

            # Remove None values to reduce payload size
            filtered_notification = {
                k: v for k, v in filtered_notification.items() if v is not None
            }
            filtered_notifications.append(filtered_notification)

        return filtered_notifications

    def _is_recent_or_upcoming(
        self, date_str: str, days_back: int = 30, days_forward: int = 90
    ) -> bool:
        """Check if a date is within the recent past or upcoming future."""
        if not date_str:
            return True  # Include items without dates

        try:
            date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            now = datetime.now(date.tzinfo)
            past_cutoff = now - timedelta(days=days_back)
            future_cutoff = now + timedelta(days=days_forward)

            return past_cutoff <= date <= future_cutoff
        except (ValueError, TypeError):
            return True  # Include items with invalid dates

    def _is_current_course(self, course: Dict[str, Any]) -> bool:
        """Determine if a course is currently active/relevant."""
        workflow_state = course.get("workflow_state", "")
        if workflow_state != "available":
            return False

        # Check enrollment state
        enrollments = course.get("enrollments", [])
        if not enrollments:
            return False

        active_enrollment = False
        for enrollment in enrollments:
            if enrollment.get("enrollment_state") == "active":
                active_enrollment = True
                break

        if not active_enrollment:
            return False

        # Check course dates
        now = datetime.now()

        # If course has an end date and it's in the past, it's not current
        if course.get("end_at"):
            try:
                end_date = datetime.fromisoformat(
                    course["end_at"].replace("Z", "+00:00")
                )
                if end_date.replace(tzinfo=None) < now:
                    return False
            except (ValueError, TypeError):
                pass

        # Check if course was updated recently (assignments, announcements, etc.)
        if course.get("updated_at"):
            try:
                updated_date = datetime.fromisoformat(
                    course["updated_at"].replace("Z", "+00:00")
                )
                # If course was updated within the last 30 days, it's likely current
                if updated_date.replace(tzinfo=None) > now - timedelta(days=30):
                    return True
            except (ValueError, TypeError):
                pass

        return True  # Default to current if we can't determine otherwise

    def _calculate_importance(
        self, assignment: Dict[str, Any], days_until_due: Optional[int]
    ) -> int:
        """Calculate assignment importance score (lower = more important)."""
        score = 0

        # Due date importance
        if days_until_due is not None:
            if days_until_due < 0:  # Overdue
                score += 0
            elif days_until_due <= 1:  # Due today or tomorrow
                score += 1
            elif days_until_due <= 3:  # Due within 3 days
                score += 2
            elif days_until_due <= 7:  # Due within a week
                score += 3
            else:  # Due later
                score += 4
        else:  # No due date
            score += 5

        # Points importance
        points = assignment.get("points_possible", 0)
        if points >= 100:
            score += 0
        elif points >= 50:
            score += 1
        elif points >= 25:
            score += 2
        else:
            score += 3

        # Submission status
        if assignment.get("has_submitted_submissions", False):
            score += 10  # Much less important if already submitted

        return score

    async def get_current_courses(self) -> Dict[str, Any]:
        """Get only currently active/relevant courses."""
        # First get all courses
        all_courses_result = await self.get_courses(include_concluded=False)
        if not all_courses_result.get("success"):
            return all_courses_result

        all_courses = all_courses_result.get("courses", [])

        # Filter for current courses
        current_courses = []
        for course in all_courses:
            if self._is_current_course(course):
                current_courses.append(course)

        self.logger.log(
            "INFO",
            "Filtered for current courses",
            {
                "all_courses": len(all_courses),
                "current_courses": len(current_courses),
                "current_course_names": [
                    c.get("name", "Unknown") for c in current_courses
                ],
            },
        )

        return {
            "success": True,
            "total_courses": len(all_courses),
            "current_courses": len(current_courses),
            "courses": current_courses,
            "all_courses": all_courses,
            "summary": f"You have {len(current_courses)} current courses out of {len(all_courses)} total enrolled courses",
        }

    async def get_comprehensive_homework(self) -> Dict[str, Any]:
        """Get comprehensive homework information including to-dos and assignments with full details."""
        try:
            # Start with to-dos for immediate actionable items
            todos_result = await self.get_todo()
            if not todos_result.get("success", False):
                return todos_result

            # Get current courses only to understand context
            courses_result = await self.get_current_courses()
            if not courses_result.get("success", False):
                return courses_result

            # Parse to-dos to extract assignment details
            all_todos = todos_result.get("all_todos", [])
            assignment_todos = []

            for todo in all_todos:
                if todo.get("type") == "submitting" and todo.get("assignment"):
                    assignment = todo["assignment"]
                    course_name = todo.get("context_name", "Unknown Course")

                    # Calculate days until due
                    due_date = assignment.get("due_at")
                    days_until_due = None
                    due_date_formatted = "No due date"

                    if due_date:
                        try:
                            due_datetime = datetime.fromisoformat(
                                due_date.replace("Z", "+00:00")
                            )
                            now = datetime.now(due_datetime.tzinfo)
                            days_until_due = (due_datetime - now).days

                            # Format the due date nicely
                            due_date_formatted = due_datetime.strftime(
                                "%A, %B %d at %I:%M %p"
                            )

                        except (ValueError, TypeError):
                            pass

                    # Extract assignment type and description
                    assignment_type = "Assignment"
                    if assignment.get("submission_types"):
                        submission_types = assignment["submission_types"]
                        if "discussion_topic" in submission_types:
                            assignment_type = "Discussion Forum"
                        elif "external_tool" in submission_types:
                            assignment_type = "External Tool/Project"
                        elif "online_upload" in submission_types:
                            assignment_type = "File Upload"
                        elif "none" in submission_types:
                            assignment_type = "No Submission Required"

                    # Get a brief description
                    description = assignment.get("description", "")
                    brief_description = ""
                    if description:
                        # Extract first sentence or first 100 characters
                        import re

                        # Remove HTML tags
                        clean_desc = re.sub(r"<[^>]+>", "", description)
                        # Get first sentence or first 100 chars
                        sentences = clean_desc.split(".")
                        if len(sentences) > 0 and len(sentences[0]) > 10:
                            brief_description = sentences[0][:150] + (
                                "..." if len(sentences[0]) > 150 else ""
                            )
                        else:
                            brief_description = clean_desc[:150] + (
                                "..." if len(clean_desc) > 150 else ""
                            )

                    assignment_todo = {
                        "id": assignment.get("id"),
                        "name": assignment.get("name", "Untitled Assignment"),
                        "course_name": course_name,
                        "assignment_type": assignment_type,
                        "due_date": due_date,
                        "due_date_formatted": due_date_formatted,
                        "days_until_due": days_until_due,
                        "points_possible": assignment.get("points_possible", 0),
                        "has_submitted": assignment.get(
                            "has_submitted_submissions", False
                        ),
                        "brief_description": brief_description,
                        "html_url": assignment.get("html_url"),
                        "workflow_state": assignment.get("workflow_state", "unknown"),
                        "locked_for_user": assignment.get("locked_for_user", False),
                        "unlock_at": assignment.get("unlock_at"),
                        "lock_at": assignment.get("lock_at"),
                        "grading_type": assignment.get("grading_type", "points"),
                        "muted": assignment.get("muted", False),
                        "importance": self._calculate_importance(
                            assignment, days_until_due
                        ),
                    }
                    assignment_todos.append(assignment_todo)

            # Sort by importance (due date, points, submission status)
            assignment_todos.sort(
                key=lambda x: (
                    x["has_submitted"],  # Unsubmitted first
                    (
                        x["days_until_due"] if x["days_until_due"] is not None else 999
                    ),  # Soonest first
                    -x["points_possible"],  # Higher points first
                )
            )

            # Categorize assignments
            due_soon = []  # Due within 3 days
            due_this_week = []  # Due within 7 days
            due_later = []  # Due later
            no_due_date = []  # No due date
            submitted = []  # Already submitted

            for assignment in assignment_todos:
                if assignment["has_submitted"]:
                    submitted.append(assignment)
                elif assignment["days_until_due"] is None:
                    no_due_date.append(assignment)
                elif assignment["days_until_due"] < 0:
                    # Overdue - add to due_soon with negative days
                    due_soon.append(assignment)
                elif assignment["days_until_due"] <= 3:
                    due_soon.append(assignment)
                elif assignment["days_until_due"] <= 7:
                    due_this_week.append(assignment)
                else:
                    due_later.append(assignment)

            # Get weekend homework specifically
            weekend_homework = []
            now = datetime.now()
            saturday = now.date()
            while saturday.weekday() != 5:  # Find next Saturday
                saturday += timedelta(days=1)
            sunday = saturday + timedelta(days=1)
            monday = sunday + timedelta(days=1)

            for assignment in assignment_todos:
                if assignment["due_date"] and not assignment["has_submitted"]:
                    try:
                        due_date = datetime.fromisoformat(
                            assignment["due_date"].replace("Z", "+00:00")
                        ).date()
                        if due_date in [saturday, sunday, monday]:
                            weekend_homework.append(assignment)
                    except (ValueError, TypeError):
                        pass

            return {
                "success": True,
                "total_assignments": len(assignment_todos),
                "due_soon_count": len(due_soon),
                "due_this_week_count": len(due_this_week),
                "due_later_count": len(due_later),
                "no_due_date_count": len(no_due_date),
                "submitted_count": len(submitted),
                "weekend_homework_count": len(weekend_homework),
                "due_soon": due_soon,
                "due_this_week": due_this_week,
                "due_later": due_later,
                "no_due_date": no_due_date,
                "submitted": submitted,
                "weekend_homework": weekend_homework,
                "all_assignments": assignment_todos,
                "summary": f"You have {len(assignment_todos)} assignments: {len(due_soon)} due soon, {len(due_this_week)} due this week, {len(weekend_homework)} due this weekend",
                "courses": courses_result.get("courses", []),
            }

        except Exception as e:
            self.logger.log(
                "ERROR",
                "Failed to get comprehensive homework",
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve comprehensive homework information from Canvas",
            }

    async def get_homework_summary(self, weekend_focus: bool = True) -> Dict[str, Any]:
        """Get a summary of homework focused on weekend assignments."""
        try:
            # Get current courses first
            courses_result = await self.get_current_courses()
            if not courses_result.get("success", False):
                return courses_result

            courses = courses_result.get("courses", [])

            # Get assignments for each current course
            assignments_by_course = {}
            for course in courses:
                course_id = str(course.get("id", ""))
                try:
                    assignment_result = await self.get_course_assignments(course_id)
                    assignments_by_course[course_id] = assignment_result
                except Exception as e:
                    self.logger.log(
                        "WARNING",
                        f"Failed to get assignments for course {course_id}",
                        str(e),
                    )
                    assignments_by_course[course_id] = {
                        "success": False,
                        "error": str(e),
                        "course_name": course.get("name", "Unknown Course"),
                    }

            # Create homework summary
            if weekend_focus:
                homework_summary = self._format_homework_summary(
                    courses, assignments_by_course
                )
            else:
                # General homework summary
                total_upcoming = sum(
                    len(data.get("upcoming", []))
                    for data in assignments_by_course.values()
                    if data.get("success")
                )
                total_overdue = sum(
                    len(data.get("overdue", []))
                    for data in assignments_by_course.values()
                    if data.get("success")
                )
                total_completed = sum(
                    len(data.get("completed", []))
                    for data in assignments_by_course.values()
                    if data.get("success")
                )

                homework_summary = {
                    "total_upcoming": total_upcoming,
                    "total_overdue": total_overdue,
                    "total_completed": total_completed,
                    "courses_with_assignments": len(
                        [
                            c
                            for c in assignments_by_course.values()
                            if c.get("success") and c.get("total_assignments", 0) > 0
                        ]
                    ),
                    "summary": f"You have {total_upcoming} upcoming assignments, {total_overdue} overdue, and {total_completed} completed across {len(courses)} active courses",
                }

            return {
                "success": True,
                "total_courses": len(courses),
                "active_courses": len(courses),
                "homework_summary": homework_summary,
                "assignments_by_course": assignments_by_course,
                "weekend_focus": weekend_focus,
            }

        except Exception as e:
            self.logger.log(
                "ERROR",
                "Failed to get homework summary",
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve homework summary from Canvas",
            }

    def _format_homework_summary(
        self,
        courses: List[Dict[str, Any]],
        assignments_by_course: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a homework-focused summary for weekend planning."""
        weekend_homework = []
        upcoming_homework = []
        overdue_homework = []

        # Get weekend dates (Saturday and Sunday)
        now = datetime.now()
        today = now.date()

        # Find next Saturday
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0 and now.weekday() == 5:  # Today is Saturday
            saturday = today
        else:
            saturday = today + timedelta(days=days_until_saturday)

        sunday = saturday + timedelta(days=1)
        monday = sunday + timedelta(days=1)

        for course in courses:
            course_id = str(course.get("id", ""))
            course_name = course.get("name", "Unknown Course")

            if course_id in assignments_by_course:
                assignment_data = assignments_by_course[course_id]
                if not assignment_data.get("success", False):
                    continue

                # Check upcoming assignments
                for assignment in assignment_data.get("upcoming", []):
                    if assignment.get("due_at"):
                        try:
                            due_date = datetime.fromisoformat(
                                assignment["due_at"].replace("Z", "+00:00")
                            ).date()

                            # Assignments due this weekend or Monday
                            if due_date in [saturday, sunday, monday]:
                                weekend_homework.append(
                                    {
                                        "course_name": course_name,
                                        "assignment": assignment,
                                        "due_date": due_date.strftime("%A, %B %d"),
                                        "days_until_due": (due_date - today).days,
                                    }
                                )
                            # Other upcoming assignments
                            elif due_date > today:
                                upcoming_homework.append(
                                    {
                                        "course_name": course_name,
                                        "assignment": assignment,
                                        "due_date": due_date.strftime("%A, %B %d"),
                                        "days_until_due": (due_date - today).days,
                                    }
                                )
                        except (ValueError, TypeError):
                            pass

                # Check overdue assignments
                for assignment in assignment_data.get("overdue", []):
                    overdue_homework.append(
                        {
                            "course_name": course_name,
                            "assignment": assignment,
                            "overdue": True,
                        }
                    )

        # Sort by due date
        weekend_homework.sort(key=lambda x: x["days_until_due"])
        upcoming_homework.sort(key=lambda x: x["days_until_due"])

        return {
            "weekend_homework": weekend_homework,
            "upcoming_homework": upcoming_homework[:10],  # Limit to next 10 assignments
            "overdue_homework": overdue_homework,
            "weekend_count": len(weekend_homework),
            "upcoming_count": len(upcoming_homework),
            "overdue_count": len(overdue_homework),
            "weekend_dates": {
                "saturday": saturday.strftime("%A, %B %d"),
                "sunday": sunday.strftime("%A, %B %d"),
                "monday": monday.strftime("%A, %B %d"),
            },
            "summary": f"Weekend homework: {len(weekend_homework)} assignments due this weekend/Monday, {len(overdue_homework)} overdue, {len(upcoming_homework)} upcoming",
        }

    async def get_courses(self, include_concluded: bool = False) -> Dict[str, Any]:
        """List all courses the user is enrolled in."""
        url = f"{self.base_url}/courses"
        params = {"include": ["enrollments"]}
        if not include_concluded:
            params["enrollment_state"] = "active"

        self.logger.log(
            "DEBUG",
            "Making Canvas API request",
            {"url": url, "method": "GET", "params": params},
        )

        try:
            resp = await self.client.get(url, params=params)
            self.logger.log(
                "DEBUG",
                "Canvas API response",
                {
                    "status_code": resp.status_code,
                    "url": url,
                    "response_length": len(resp.content) if resp.content else 0,
                },
            )
            resp.raise_for_status()
            courses = resp.json()

            # Filter the data to reduce token usage
            filtered_courses = self._filter_course_data(courses)

            # Group courses by status
            active_courses = [
                c for c in filtered_courses if c.get("workflow_state") == "available"
            ]

            return {
                "success": True,
                "total_courses": len(filtered_courses),
                "active_courses": len(active_courses),
                "courses": filtered_courses,
                "summary": f"You are enrolled in {len(active_courses)} active courses",
            }
        except Exception as e:
            self.logger.log(
                "ERROR",
                "Canvas API request failed",
                {
                    "url": url,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve courses from Canvas",
            }

    async def get_enrollments(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        List all enrollments for a given user.
        If user_id is None, uses 'self'.
        """
        uid = user_id or "self"
        url = f"{self.base_url}/users/{uid}/enrollments"
        self.logger.log(
            "DEBUG", "Making Canvas API request", {"url": url, "method": "GET"}
        )

        try:
            resp = await self.client.get(url)
            self.logger.log(
                "DEBUG",
                "Canvas API response",
                {
                    "status_code": resp.status_code,
                    "url": url,
                    "response_length": len(resp.content) if resp.content else 0,
                },
            )
            resp.raise_for_status()
            enrollments = resp.json()

            # Categorize enrollments by type and status
            active_enrollments = []
            inactive_enrollments = []
            student_enrollments = []
            teacher_enrollments = []

            for enrollment in enrollments:
                # By status
                if enrollment.get("enrollment_state") == "active":
                    active_enrollments.append(enrollment)
                else:
                    inactive_enrollments.append(enrollment)

                # By type
                role = enrollment.get("type", "").lower()
                if "student" in role:
                    student_enrollments.append(enrollment)
                elif "teacher" in role or "instructor" in role:
                    teacher_enrollments.append(enrollment)

            return {
                "success": True,
                "total_enrollments": len(enrollments),
                "active_count": len(active_enrollments),
                "inactive_count": len(inactive_enrollments),
                "student_count": len(student_enrollments),
                "teacher_count": len(teacher_enrollments),
                "active_enrollments": active_enrollments,
                "student_enrollments": student_enrollments,
                "teacher_enrollments": teacher_enrollments,
                "summary": f"You have {len(enrollments)} total enrollments: {len(active_enrollments)} active, {len(student_enrollments)} as student, {len(teacher_enrollments)} as teacher",
            }
        except Exception as e:
            self.logger.log(
                "ERROR",
                "Canvas API request failed",
                {
                    "url": url,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve enrollments from Canvas",
            }

    async def get_course_assignments(
        self, course_id: str, include_concluded: bool = False, recent_only: bool = True
    ) -> Dict[str, Any]:
        """List all assignments for a specific course."""
        url = f"{self.base_url}/courses/{course_id}/assignments"
        params = {"per_page": 100}  # Limit to reduce payload

        self.logger.log(
            "DEBUG",
            "Making Canvas API request",
            {"url": url, "method": "GET", "params": params},
        )

        try:
            resp = await self.client.get(url, params=params)
            self.logger.log(
                "DEBUG",
                "Canvas API response",
                {
                    "status_code": resp.status_code,
                    "url": url,
                    "response_length": len(resp.content) if resp.content else 0,
                },
            )
            resp.raise_for_status()
            assignments = resp.json()

            # Filter assignments by date if requested
            if recent_only:
                assignments = [
                    a
                    for a in assignments
                    if self._is_recent_or_upcoming(a.get("due_at"))
                    or self._is_recent_or_upcoming(a.get("unlock_at"))
                    or a.get("due_at") is None  # Include assignments without due dates
                ]

            # Filter the data to reduce token usage
            filtered_assignments = self._filter_assignment_data(assignments)

            # Categorize assignments
            upcoming = []
            overdue = []
            no_due_date = []
            completed = []

            now = datetime.now()

            for assignment in filtered_assignments:
                if assignment.get("has_submitted_submissions"):
                    completed.append(assignment)
                elif assignment.get("due_at"):
                    try:
                        due_date = datetime.fromisoformat(
                            assignment["due_at"].replace("Z", "+00:00")
                        )
                        if due_date.replace(tzinfo=None) > now:
                            upcoming.append(assignment)
                        else:
                            overdue.append(assignment)
                    except (ValueError, TypeError):
                        no_due_date.append(assignment)
                else:
                    no_due_date.append(assignment)

            # Sort by due date
            upcoming.sort(key=lambda a: a.get("due_at", ""))
            overdue.sort(key=lambda a: a.get("due_at", ""))

            return {
                "success": True,
                "course_id": course_id,
                "total_assignments": len(filtered_assignments),
                "upcoming_count": len(upcoming),
                "overdue_count": len(overdue),
                "completed_count": len(completed),
                "no_due_date_count": len(no_due_date),
                "upcoming": upcoming,
                "overdue": overdue,
                "completed": completed,
                "no_due_date": no_due_date,
                "summary": f"Found {len(filtered_assignments)} assignments: {len(upcoming)} upcoming, {len(overdue)} overdue, {len(completed)} completed",
            }
        except Exception as e:
            self.logger.log(
                "ERROR",
                "Canvas API request failed",
                {
                    "url": url,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to retrieve assignments for course {course_id}",
            }

    async def get_todo(self) -> Dict[str, Any]:
        """Fetch to-do items (assignments, discussions, quizzes, calendar events)."""
        url = f"{self.base_url}/users/self/todo"
        self.logger.log(
            "DEBUG", "Making Canvas API request", {"url": url, "method": "GET"}
        )

        try:
            resp = await self.client.get(url)
            self.logger.log(
                "DEBUG",
                "Canvas API response",
                {
                    "status_code": resp.status_code,
                    "url": url,
                    "response_length": len(resp.content) if resp.content else 0,
                },
            )
            resp.raise_for_status()
            todos = resp.json()

            # Filter the data to reduce token usage
            filtered_todos = self._filter_todo_items(todos)

            # Categorize todos by type
            assignments = []
            quizzes = []
            discussions = []
            other = []

            for todo in filtered_todos:
                todo_type = todo.get("type", "").lower()
                if "assignment" in todo_type or "submitting" in todo_type:
                    assignments.append(todo)
                elif "quiz" in todo_type:
                    quizzes.append(todo)
                elif "discussion" in todo_type:
                    discussions.append(todo)
                else:
                    other.append(todo)

            return {
                "success": True,
                "total_todos": len(filtered_todos),
                "assignments_count": len(assignments),
                "quizzes_count": len(quizzes),
                "discussions_count": len(discussions),
                "other_count": len(other),
                "assignments": assignments,
                "quizzes": quizzes,
                "discussions": discussions,
                "other": other,
                "all_todos": filtered_todos,
                "summary": f"You have {len(filtered_todos)} items in your to-do list: {len(assignments)} assignments, {len(quizzes)} quizzes, {len(discussions)} discussions",
            }
        except Exception as e:
            self.logger.log(
                "ERROR",
                "Canvas API request failed",
                {
                    "url": url,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve to-do items from Canvas",
            }

    async def get_calendar_events(self, upcoming_only: bool = True) -> Dict[str, Any]:
        """Fetch all calendar events visible to the user."""
        url = f"{self.base_url}/calendar_events"
        params = {"per_page": 100}

        if upcoming_only:
            # Only get events from the last 7 days to next 30 days
            start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            params["start_date"] = start_date
            params["end_date"] = end_date

        self.logger.log(
            "DEBUG",
            "Making Canvas API request",
            {"url": url, "method": "GET", "params": params},
        )

        try:
            resp = await self.client.get(url, params=params)
            self.logger.log(
                "DEBUG",
                "Canvas API response",
                {
                    "status_code": resp.status_code,
                    "url": url,
                    "response_length": len(resp.content) if resp.content else 0,
                },
            )
            resp.raise_for_status()
            events = resp.json()

            # Filter the data to reduce token usage
            filtered_events = self._filter_calendar_events(events)

            # Categorize events
            upcoming_events = []
            past_events = []
            today_events = []

            now = datetime.now()
            today_date = now.date()

            for event in filtered_events:
                if event.get("start_at"):
                    try:
                        start_date = datetime.fromisoformat(
                            event["start_at"].replace("Z", "+00:00")
                        )
                        event_date = start_date.date()

                        if event_date == today_date:
                            today_events.append(event)
                        elif event_date > today_date:
                            upcoming_events.append(event)
                        else:
                            past_events.append(event)
                    except (ValueError, TypeError):
                        upcoming_events.append(event)
                else:
                    upcoming_events.append(event)

            # Sort by start date
            upcoming_events.sort(key=lambda e: e.get("start_at", ""))
            today_events.sort(key=lambda e: e.get("start_at", ""))

            return {
                "success": True,
                "total_events": len(filtered_events),
                "today_count": len(today_events),
                "upcoming_count": len(upcoming_events),
                "past_count": len(past_events),
                "today_events": today_events,
                "upcoming_events": upcoming_events,
                "past_events": past_events,
                "summary": f"Found {len(filtered_events)} calendar events: {len(today_events)} today, {len(upcoming_events)} upcoming, {len(past_events)} past",
            }
        except Exception as e:
            self.logger.log(
                "ERROR",
                "Canvas API request failed",
                {
                    "url": url,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve calendar events from Canvas",
            }

    async def get_notifications(self) -> Dict[str, Any]:
        """
        Fetch global account notifications (announcements).
        Requires an account_id; if not set, it will fetch your accounts and pick the first.
        """
        try:
            acct = self.account_id or await self._get_default_account_id()
            url = f"{self.base_url}/accounts/{acct}/account_notifications"
            params = {"include_past": True, "include_all": True}
            self.logger.log(
                "DEBUG",
                "Making Canvas API request",
                {"url": url, "method": "GET", "params": params},
            )

            resp = await self.client.get(url, params=params)
            self.logger.log(
                "DEBUG",
                "Canvas API response",
                {
                    "status_code": resp.status_code,
                    "url": url,
                    "response_length": len(resp.content) if resp.content else 0,
                },
            )
            resp.raise_for_status()
            notifications = resp.json()

            # Filter the data to reduce token usage
            filtered_notifications = self._filter_notifications(notifications)

            # Categorize notifications by date
            current_notifications = []
            past_notifications = []

            now = datetime.now()

            for notification in filtered_notifications:
                if notification.get("end_at"):
                    try:
                        end_date = datetime.fromisoformat(
                            notification["end_at"].replace("Z", "+00:00")
                        )
                        if end_date.replace(tzinfo=None) > now:
                            current_notifications.append(notification)
                        else:
                            past_notifications.append(notification)
                    except (ValueError, TypeError):
                        current_notifications.append(notification)
                else:
                    current_notifications.append(notification)

            # Sort by start date
            current_notifications.sort(
                key=lambda n: n.get("start_at", ""), reverse=True
            )

            return {
                "success": True,
                "total_notifications": len(filtered_notifications),
                "current_count": len(current_notifications),
                "past_count": len(past_notifications),
                "current_notifications": current_notifications,
                "past_notifications": past_notifications,
                "summary": f"Found {len(filtered_notifications)} notifications: {len(current_notifications)} current, {len(past_notifications)} past",
            }
        except Exception as e:
            self.logger.log(
                "ERROR",
                "Canvas API request failed",
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve notifications from Canvas",
            }

    async def _get_default_account_id(self) -> str:
        """Helper to fetch the user's first Canvas account ID."""
        url = f"{self.base_url}/users/self/accounts"
        self.logger.log(
            "DEBUG", "Making Canvas API request", {"url": url, "method": "GET"}
        )

        try:
            resp = await self.client.get(url)
            self.logger.log(
                "DEBUG",
                "Canvas API response",
                {
                    "status_code": resp.status_code,
                    "url": url,
                    "response_length": len(resp.content) if resp.content else 0,
                },
            )
            resp.raise_for_status()
            accounts = resp.json()
            if not accounts:
                raise ValueError("No Canvas accounts found for this user.")
            account_id = str(accounts[0]["id"])
            self.logger.log(
                "INFO", "Found default Canvas account", {"account_id": account_id}
            )
            return account_id
        except Exception as e:
            self.logger.log(
                "ERROR",
                "Canvas API request failed",
                {
                    "url": url,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    async def get_messages(self, per_page: int = 50) -> Dict[str, Any]:
        """
        List conversation threads (inbox messages).
        You can page through with `per_page` or add additional Canvas params if needed.
        """
        url = f"{self.base_url}/conversations"
        params = {"per_page": per_page}
        self.logger.log(
            "DEBUG",
            "Making Canvas API request",
            {"url": url, "method": "GET", "params": params},
        )

        try:
            resp = await self.client.get(url, params=params)
            self.logger.log(
                "DEBUG",
                "Canvas API response",
                {
                    "status_code": resp.status_code,
                    "url": url,
                    "response_length": len(resp.content) if resp.content else 0,
                },
            )
            resp.raise_for_status()
            conversations = resp.json()

            # Filter the data to reduce token usage
            filtered_conversations = self._filter_conversations(conversations)

            # Categorize messages
            unread_messages = []
            read_messages = []
            starred_messages = []

            for conversation in filtered_conversations:
                if conversation.get("workflow_state") == "unread":
                    unread_messages.append(conversation)
                else:
                    read_messages.append(conversation)

                if conversation.get("starred"):
                    starred_messages.append(conversation)

            # Sort by last message date
            filtered_conversations.sort(
                key=lambda c: c.get("last_message_at", ""), reverse=True
            )

            return {
                "success": True,
                "total_conversations": len(filtered_conversations),
                "unread_count": len(unread_messages),
                "read_count": len(read_messages),
                "starred_count": len(starred_messages),
                "unread_messages": unread_messages,
                "read_messages": read_messages,
                "starred_messages": starred_messages,
                "summary": f"You have {len(filtered_conversations)} conversations: {len(unread_messages)} unread, {len(starred_messages)} starred",
            }
        except Exception as e:
            self.logger.log(
                "ERROR",
                "Canvas API request failed",
                {
                    "url": url,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve messages from Canvas",
            }

    async def close(self):
        """Clean up the HTTP client when shutting down."""
        self.logger.log("INFO", "Closing Canvas service")
        await self.client.aclose()
