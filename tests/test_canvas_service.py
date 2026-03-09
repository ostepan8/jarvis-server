"""
Tests for CanvasService.

Tests verify:
1. Service initialization (with/without token, placeholder URL)
2. Filter helpers (_filter_course_data, _filter_assignment_data, etc.)
3. Date/course helper methods (_is_recent_or_upcoming, _is_current_course, _calculate_importance)
4. API methods: get_courses, get_enrollments, get_course_assignments, get_todo,
   get_calendar_events, get_notifications, get_messages
5. Error handling for each API method
6. Close method
"""

import pytest
import httpx
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from jarvis.services.canvas_service import CanvasService


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = MagicMock()
    logger.log = MagicMock()
    return logger


@pytest.fixture
def canvas_service(mock_logger):
    """Create a CanvasService with test credentials."""
    service = CanvasService(
        base_url="https://test.instructure.com/api/v1",
        api_token="test-token",
        account_id="12345",
        logger=mock_logger,
    )
    return service


class TestCanvasServiceInit:
    """Tests for CanvasService initialization."""

    def test_init_with_explicit_credentials(self, mock_logger):
        """Test initialization with explicitly provided credentials."""
        service = CanvasService(
            base_url="https://school.instructure.com/api/v1",
            api_token="my-token",
            account_id="99",
            logger=mock_logger,
        )
        assert service.base_url == "https://school.instructure.com/api/v1"
        assert service.token == "my-token"
        assert service.account_id == "99"

    def test_init_without_token_raises_value_error(self, mock_logger):
        """Test initialization without token raises ValueError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="Canvas API token not provided"):
                CanvasService(
                    base_url="https://school.instructure.com/api/v1",
                    api_token=None,
                    logger=mock_logger,
                )

    def test_init_with_placeholder_url_raises_value_error(self, mock_logger):
        """Test initialization with placeholder URL raises ValueError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="placeholder"):
                CanvasService(
                    api_token="my-token",
                    logger=mock_logger,
                )

    def test_init_with_env_vars(self, mock_logger):
        """Test initialization from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "CANVAS_API_URL": "https://env-school.instructure.com/api/v1",
                "CANVAS_API_TOKEN": "env-token",
                "CANVAS_ACCOUNT_ID": "777",
            },
        ):
            service = CanvasService(logger=mock_logger)
            assert service.base_url == "https://env-school.instructure.com/api/v1"
            assert service.token == "env-token"
            assert service.account_id == "777"


class TestFilterCourseData:
    """Tests for _filter_course_data helper."""

    def test_filter_course_data_extracts_essential_fields(self, canvas_service):
        """Test that filter only keeps essential fields."""
        courses = [
            {
                "id": 1,
                "name": "Math 101",
                "course_code": "MATH101",
                "workflow_state": "available",
                "enrollment_term_id": 1,
                "start_at": "2024-01-01",
                "end_at": "2024-06-01",
                "enrollments": [{"type": "student"}],
                "html_url": "https://canvas.com/courses/1",
                "created_at": "2024-01-01",
                "updated_at": "2024-02-01",
                "extra_field": "should_not_appear",
                "uuid": "abc123",
            }
        ]

        result = canvas_service._filter_course_data(courses)
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Math 101"
        assert "extra_field" not in result[0]
        assert "uuid" not in result[0]

    def test_filter_course_data_handles_missing_fields(self, canvas_service):
        """Test filter handles courses with missing fields."""
        courses = [{"id": 2}]
        result = canvas_service._filter_course_data(courses)
        assert result[0]["id"] == 2
        assert result[0]["name"] is None
        assert result[0]["enrollments"] == []


class TestFilterAssignmentData:
    """Tests for _filter_assignment_data helper."""

    def test_filter_assignment_data_extracts_essential_fields(self, canvas_service):
        """Test that filter only keeps essential fields."""
        assignments = [
            {
                "id": 10,
                "name": "Homework 1",
                "course_id": 1,
                "due_at": "2024-02-01",
                "points_possible": 100,
                "grading_type": "points",
                "workflow_state": "published",
                "published": True,
                "submission_types": ["online_upload"],
                "html_url": "https://canvas.com/assignments/10",
                "secure_params": "abc",
                "rubric": {"a": 1},
            }
        ]

        result = canvas_service._filter_assignment_data(assignments)
        assert len(result) == 1
        assert result[0]["id"] == 10
        assert result[0]["name"] == "Homework 1"
        assert "secure_params" not in result[0]
        assert "rubric" not in result[0]

    def test_filter_assignment_data_truncates_long_description(self, canvas_service):
        """Test that long HTML descriptions are cleaned and truncated."""
        long_desc = "<p>" + "A" * 500 + "</p>"
        assignments = [
            {
                "id": 11,
                "name": "Long Desc Assignment",
                "description": long_desc,
            }
        ]

        result = canvas_service._filter_assignment_data(assignments)
        desc = result[0]["description"]
        assert len(desc) <= 303  # 300 + "..."
        assert "<p>" not in desc

    def test_filter_assignment_data_short_description_not_truncated(self, canvas_service):
        """Test that short descriptions are not truncated."""
        assignments = [
            {
                "id": 12,
                "name": "Short Desc",
                "description": "<b>Do this</b>",
            }
        ]

        result = canvas_service._filter_assignment_data(assignments)
        assert result[0]["description"] == "Do this"
        assert "..." not in result[0]["description"]

    def test_filter_assignment_data_no_description(self, canvas_service):
        """Test filter handles assignments without description."""
        assignments = [{"id": 13, "name": "No Desc"}]
        result = canvas_service._filter_assignment_data(assignments)
        assert "description" not in result[0]


class TestFilterCalendarEvents:
    """Tests for _filter_calendar_events helper."""

    def test_filter_calendar_events_removes_none_values(self, canvas_service):
        """Test that None values are removed from filtered events."""
        events = [
            {
                "id": 1,
                "title": "Test Event",
                "start_at": "2024-01-15T10:00:00Z",
                "description": None,
                "location_name": None,
            }
        ]

        result = canvas_service._filter_calendar_events(events)
        assert "description" not in result[0]
        assert "location_name" not in result[0]
        assert result[0]["title"] == "Test Event"

    def test_filter_calendar_events_truncates_description(self, canvas_service):
        """Test that event descriptions are truncated to 200 chars."""
        events = [
            {
                "id": 2,
                "title": "Long Event",
                "description": "X" * 300,
            }
        ]

        result = canvas_service._filter_calendar_events(events)
        assert len(result[0]["description"]) == 200


class TestFilterTodoItems:
    """Tests for _filter_todo_items helper."""

    def test_filter_todo_items(self, canvas_service):
        """Test todo item filtering removes None values."""
        todos = [
            {
                "type": "submitting",
                "assignment": {"id": 1, "name": "HW1"},
                "context_type": "Course",
                "context_name": "Math",
                "course_id": 100,
                "html_url": "https://canvas.com/todo/1",
                "quiz": None,
            }
        ]

        result = canvas_service._filter_todo_items(todos)
        assert "quiz" not in result[0]
        assert result[0]["type"] == "submitting"


class TestIsRecentOrUpcoming:
    """Tests for _is_recent_or_upcoming helper."""

    def test_recent_date_returns_true(self, canvas_service):
        """Test that a recent date returns True."""
        recent = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        assert canvas_service._is_recent_or_upcoming(recent) is True

    def test_future_date_returns_true(self, canvas_service):
        """Test that a future date within range returns True."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        assert canvas_service._is_recent_or_upcoming(future) is True

    def test_old_date_returns_false(self, canvas_service):
        """Test that a very old date returns False."""
        old = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        assert canvas_service._is_recent_or_upcoming(old) is False

    def test_far_future_date_returns_false(self, canvas_service):
        """Test that a far future date returns False."""
        far = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        assert canvas_service._is_recent_or_upcoming(far) is False

    def test_none_date_returns_true(self, canvas_service):
        """Test that None date returns True (include items without dates)."""
        assert canvas_service._is_recent_or_upcoming(None) is True

    def test_empty_string_date_returns_true(self, canvas_service):
        """Test that empty string date returns True."""
        assert canvas_service._is_recent_or_upcoming("") is True

    def test_invalid_date_returns_true(self, canvas_service):
        """Test that invalid date string returns True."""
        assert canvas_service._is_recent_or_upcoming("not-a-date") is True


class TestIsCurrentCourse:
    """Tests for _is_current_course helper."""

    def test_active_course_is_current(self, canvas_service):
        """Test that an active course with active enrollment is current."""
        course = {
            "workflow_state": "available",
            "enrollments": [{"enrollment_state": "active"}],
            "updated_at": datetime.now().isoformat() + "Z",
        }
        assert canvas_service._is_current_course(course) is True

    def test_concluded_course_is_not_current(self, canvas_service):
        """Test that a concluded course is not current."""
        course = {
            "workflow_state": "concluded",
            "enrollments": [{"enrollment_state": "active"}],
        }
        assert canvas_service._is_current_course(course) is False

    def test_no_enrollments_is_not_current(self, canvas_service):
        """Test that a course with no enrollments is not current."""
        course = {
            "workflow_state": "available",
            "enrollments": [],
        }
        assert canvas_service._is_current_course(course) is False

    def test_inactive_enrollment_is_not_current(self, canvas_service):
        """Test that a course with only inactive enrollments is not current."""
        course = {
            "workflow_state": "available",
            "enrollments": [{"enrollment_state": "completed"}],
        }
        assert canvas_service._is_current_course(course) is False

    def test_past_end_date_is_not_current(self, canvas_service):
        """Test that a course with past end date is not current."""
        past_date = (datetime.now() - timedelta(days=60)).isoformat() + "Z"
        course = {
            "workflow_state": "available",
            "enrollments": [{"enrollment_state": "active"}],
            "end_at": past_date,
        }
        assert canvas_service._is_current_course(course) is False


class TestCalculateImportance:
    """Tests for _calculate_importance helper."""

    def test_overdue_assignment_highest_importance(self, canvas_service):
        """Test that overdue assignment gets lowest score (most important)."""
        assignment = {"points_possible": 100, "has_submitted_submissions": False}
        score = canvas_service._calculate_importance(assignment, days_until_due=-1)
        assert score == 0  # 0 for overdue + 0 for 100 points

    def test_due_tomorrow_high_importance(self, canvas_service):
        """Test assignment due tomorrow has high importance."""
        assignment = {"points_possible": 50, "has_submitted_submissions": False}
        score = canvas_service._calculate_importance(assignment, days_until_due=1)
        assert score == 2  # 1 for due tomorrow + 1 for 50 points

    def test_no_due_date_low_importance(self, canvas_service):
        """Test assignment with no due date has lower importance."""
        assignment = {"points_possible": 10, "has_submitted_submissions": False}
        score = canvas_service._calculate_importance(assignment, days_until_due=None)
        assert score == 8  # 5 for no date + 3 for <25 points

    def test_submitted_assignment_least_important(self, canvas_service):
        """Test that submitted assignments have much higher score."""
        assignment = {"points_possible": 100, "has_submitted_submissions": True}
        score = canvas_service._calculate_importance(assignment, days_until_due=0)
        # 1 for due today + 0 for 100 points + 10 for submitted = 11
        assert score == 11


class TestGetCourses:
    """Tests for get_courses API method."""

    @pytest.mark.asyncio
    async def test_get_courses_success(self, canvas_service):
        """Test successful course retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'[...]'
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {
                "id": 1,
                "name": "Math 101",
                "course_code": "MATH101",
                "workflow_state": "available",
                "enrollments": [{"type": "student"}],
            },
            {
                "id": 2,
                "name": "English 201",
                "course_code": "ENG201",
                "workflow_state": "completed",
                "enrollments": [{"type": "student"}],
            },
        ]

        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(return_value=mock_response)

        result = await canvas_service.get_courses()

        assert result["success"] is True
        assert result["total_courses"] == 2
        assert result["active_courses"] == 1

    @pytest.mark.asyncio
    async def test_get_courses_api_error(self, canvas_service):
        """Test course retrieval with API error."""
        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "500 Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
        )

        result = await canvas_service.get_courses()

        assert result["success"] is False
        assert "error" in result


class TestGetEnrollments:
    """Tests for get_enrollments API method."""

    @pytest.mark.asyncio
    async def test_get_enrollments_success(self, canvas_service):
        """Test successful enrollment retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'[...]'
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {"type": "StudentEnrollment", "enrollment_state": "active"},
            {"type": "TeacherEnrollment", "enrollment_state": "active"},
            {"type": "StudentEnrollment", "enrollment_state": "completed"},
        ]

        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(return_value=mock_response)

        result = await canvas_service.get_enrollments()

        assert result["success"] is True
        assert result["total_enrollments"] == 3
        assert result["active_count"] == 2
        assert result["inactive_count"] == 1
        assert result["student_count"] == 2
        assert result["teacher_count"] == 1

    @pytest.mark.asyncio
    async def test_get_enrollments_for_specific_user(self, canvas_service):
        """Test enrollment retrieval for a specific user ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'[...]'
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = []

        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(return_value=mock_response)

        result = await canvas_service.get_enrollments(user_id="42")

        assert result["success"] is True
        # Verify the URL used
        call_args = canvas_service.client.get.call_args
        assert "42" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_enrollments_api_error(self, canvas_service):
        """Test enrollment retrieval with API error."""
        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=MagicMock(status_code=401),
            )
        )

        result = await canvas_service.get_enrollments()
        assert result["success"] is False


class TestGetCourseAssignments:
    """Tests for get_course_assignments API method."""

    @pytest.mark.asyncio
    async def test_get_course_assignments_success(self, canvas_service):
        """Test successful assignment retrieval."""
        now = datetime.now()
        future = (now + timedelta(days=5)).isoformat() + "Z"
        past = (now - timedelta(days=5)).isoformat() + "Z"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'[...]'
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {
                "id": 1,
                "name": "Future HW",
                "due_at": future,
                "has_submitted_submissions": False,
            },
            {
                "id": 2,
                "name": "Past HW",
                "due_at": past,
                "has_submitted_submissions": False,
            },
            {
                "id": 3,
                "name": "Completed HW",
                "due_at": future,
                "has_submitted_submissions": True,
            },
            {
                "id": 4,
                "name": "No Date HW",
                "has_submitted_submissions": False,
            },
        ]

        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(return_value=mock_response)

        result = await canvas_service.get_course_assignments("101")

        assert result["success"] is True
        assert result["course_id"] == "101"
        assert result["upcoming_count"] == 1
        assert result["overdue_count"] == 1
        assert result["completed_count"] == 1
        assert result["no_due_date_count"] == 1

    @pytest.mark.asyncio
    async def test_get_course_assignments_api_error(self, canvas_service):
        """Test assignment retrieval with API error."""
        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(
            side_effect=RuntimeError("Network error")
        )

        result = await canvas_service.get_course_assignments("101")
        assert result["success"] is False
        assert "error" in result


class TestGetTodo:
    """Tests for get_todo API method."""

    @pytest.mark.asyncio
    async def test_get_todo_success(self, canvas_service):
        """Test successful todo retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'[...]'
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {"type": "submitting", "assignment": {"id": 1}, "context_type": "Course"},
            {"type": "quiz", "quiz": {"id": 2}, "context_type": "Course"},
            {"type": "discussion_topic", "context_type": "Course"},
        ]

        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(return_value=mock_response)

        result = await canvas_service.get_todo()

        assert result["success"] is True
        assert result["total_todos"] == 3
        assert result["assignments_count"] == 1
        assert result["quizzes_count"] == 1
        assert result["discussions_count"] == 1

    @pytest.mark.asyncio
    async def test_get_todo_api_error(self, canvas_service):
        """Test todo retrieval with API error."""
        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(
            side_effect=RuntimeError("Failed")
        )

        result = await canvas_service.get_todo()
        assert result["success"] is False


class TestGetCalendarEvents:
    """Tests for get_calendar_events API method."""

    @pytest.mark.asyncio
    async def test_get_calendar_events_success(self, canvas_service):
        """Test successful calendar event retrieval."""
        now = datetime.now(timezone.utc)
        today = now.isoformat()
        future = (now + timedelta(days=5)).isoformat()
        past = (now - timedelta(days=2)).isoformat()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'[...]'
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {"id": 1, "title": "Today Event", "start_at": today},
            {"id": 2, "title": "Future Event", "start_at": future},
            {"id": 3, "title": "Past Event", "start_at": past},
        ]

        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(return_value=mock_response)

        result = await canvas_service.get_calendar_events()

        assert result["success"] is True
        assert result["total_events"] == 3
        # Exact counts depend on timezone; just verify structure
        assert "today_events" in result
        assert "upcoming_events" in result
        assert "past_events" in result

    @pytest.mark.asyncio
    async def test_get_calendar_events_error(self, canvas_service):
        """Test calendar event retrieval with API error."""
        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(
            side_effect=RuntimeError("Failed")
        )

        result = await canvas_service.get_calendar_events()
        assert result["success"] is False


class TestGetMessages:
    """Tests for get_messages API method."""

    @pytest.mark.asyncio
    async def test_get_messages_success(self, canvas_service):
        """Test successful message retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'[...]'
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {
                "id": 1,
                "subject": "Important",
                "workflow_state": "unread",
                "starred": True,
                "last_message_at": "2024-01-15",
            },
            {
                "id": 2,
                "subject": "General",
                "workflow_state": "read",
                "starred": False,
                "last_message_at": "2024-01-14",
            },
        ]

        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(return_value=mock_response)

        result = await canvas_service.get_messages()

        assert result["success"] is True
        assert result["total_conversations"] == 2
        assert result["unread_count"] == 1
        assert result["starred_count"] == 1

    @pytest.mark.asyncio
    async def test_get_messages_error(self, canvas_service):
        """Test message retrieval with API error."""
        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(
            side_effect=RuntimeError("Failed")
        )

        result = await canvas_service.get_messages()
        assert result["success"] is False


class TestGetNotifications:
    """Tests for get_notifications API method."""

    @pytest.mark.asyncio
    async def test_get_notifications_success_with_account_id(self, canvas_service):
        """Test successful notification retrieval with pre-set account ID."""
        future = (datetime.now() + timedelta(days=5)).isoformat() + "Z"
        past = (datetime.now() - timedelta(days=60)).isoformat() + "Z"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'[...]'
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = [
            {"id": 1, "subject": "Active Notice", "end_at": future, "start_at": future},
            {"id": 2, "subject": "Old Notice", "end_at": past, "start_at": past},
        ]

        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(return_value=mock_response)

        result = await canvas_service.get_notifications()

        assert result["success"] is True
        assert result["total_notifications"] == 2
        assert result["current_count"] == 1
        assert result["past_count"] == 1

    @pytest.mark.asyncio
    async def test_get_notifications_error(self, canvas_service):
        """Test notification retrieval with API error."""
        canvas_service.client = AsyncMock()
        canvas_service.client.get = AsyncMock(
            side_effect=RuntimeError("Failed")
        )

        result = await canvas_service.get_notifications()
        assert result["success"] is False


class TestClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close_calls_aclose(self, canvas_service):
        """Test that close calls aclose on the HTTP client."""
        canvas_service.client = AsyncMock()
        canvas_service.client.aclose = AsyncMock()

        await canvas_service.close()
        canvas_service.client.aclose.assert_called_once()


class TestFilterConversations:
    """Tests for _filter_conversations helper."""

    def test_filter_conversations(self, canvas_service):
        """Test conversation filtering removes None values."""
        conversations = [
            {
                "id": 1,
                "subject": "Hello",
                "workflow_state": "unread",
                "last_message": "Hi there",
                "last_message_at": "2024-01-15",
                "message_count": 3,
                "starred": True,
                "participants": [{"id": 10, "name": "Alice"}],
                "context_name": "Math 101",
                "extra_data": "should be ignored",
            }
        ]

        result = canvas_service._filter_conversations(conversations)
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["subject"] == "Hello"
        assert result[0]["starred"] is True
        assert "extra_data" not in result[0]


class TestFilterNotifications:
    """Tests for _filter_notifications helper."""

    def test_filter_notifications_truncates_message(self, canvas_service):
        """Test that notification messages are truncated to 300 chars."""
        notifications = [
            {
                "id": 1,
                "subject": "Long Notice",
                "message": "A" * 500,
                "start_at": "2024-01-01",
            }
        ]

        result = canvas_service._filter_notifications(notifications)
        assert len(result[0]["message"]) == 300

    def test_filter_notifications_removes_none_values(self, canvas_service):
        """Test that None values are removed."""
        notifications = [
            {
                "id": 2,
                "subject": "Test",
                "message": None,
                "end_at": None,
            }
        ]

        result = canvas_service._filter_notifications(notifications)
        assert "message" not in result[0]
        assert "end_at" not in result[0]
