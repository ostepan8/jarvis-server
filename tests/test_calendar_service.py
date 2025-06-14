import asyncio
import pytest
from jarvis.services.calendar_service import CalendarService

class MockResponse:
    def __init__(self, data):
        self._data = data
    def json(self):
        return self._data

@pytest.mark.asyncio
async def test_get_events_by_date(monkeypatch):
    service = CalendarService(base_url="http://test")

    async def mock_request(method, url, params=None, json=None):
        assert method == "GET"
        assert url.endswith("/events/day/2024-01-01")
        return MockResponse({
            "data": [
                {
                    "id": "1",
                    "title": "Meeting",
                    "time": "2024-01-01 10:00",
                    "duration": 3600,
                    "description": "Discuss project",
                    "category": "work",
                }
            ]
        })

    monkeypatch.setattr(service.client, "request", mock_request)
    result = await service.get_events_by_date("2024-01-01")

    assert result["date"] == "2024-01-01"
    assert result["event_count"] == 1
    assert result["events"][0]["title"] == "Meeting"
