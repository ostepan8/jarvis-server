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


@pytest.mark.asyncio
async def test_validate_event_time_uses_json(monkeypatch):
    service = CalendarService(base_url="http://test")

    captured = {}

    async def mock_request(method, endpoint, *, params=None, json=None):
        captured["method"] = method
        captured["endpoint"] = endpoint
        captured["json"] = json
        return {"valid": True, "conflicts": []}

    monkeypatch.setattr(service, "_request", mock_request)

    await service.validate_event_time("2024-01-02 10:00", duration_seconds=1800, title="Call")

    assert captured["json"] == {
        "time": "2024-01-02 10:00",
        "duration": 1800,
        "title": "Call",
    }


@pytest.mark.asyncio
async def test_update_event_uses_json(monkeypatch):
    service = CalendarService(base_url="http://test")

    expected = {
        "title": "Meet",
        "time": "2024-01-03 09:00",
        "duration_seconds": 3600,
        "description": "desc",
        "category": "work",
    }
    captured = {}

    async def mock_request(method, endpoint, *, params=None, json=None):
        captured["json"] = json
        return {"data": {"id": "123", **json}}

    monkeypatch.setattr(service, "_request", mock_request)

    result = await service.update_event("123", **expected)

    json_expected = {
        "title": "Meet",
        "time": "2024-01-03 09:00",
        "duration": 3600,
        "description": "desc",
        "category": "work",
    }
    assert captured["json"] == json_expected
    assert result["event"]["title"] == "Meet"


@pytest.mark.asyncio
async def test_update_event_fields_uses_json(monkeypatch):
    service = CalendarService(base_url="http://test")

    fields = {"title": "New Title"}
    captured = {}

    async def mock_request(method, endpoint, *, params=None, json=None):
        captured["json"] = json
        return {"data": {"id": "1", **json, "time": "2024-01-04 08:00", "duration": 0}}

    monkeypatch.setattr(service, "_request", mock_request)

    await service.update_event_fields("1", fields)

    assert captured["json"] == fields


@pytest.mark.asyncio
async def test_add_events_bulk_uses_json(monkeypatch):
    service = CalendarService(base_url="http://test")

    events = [
        {"title": "A", "time": "2024-01-05 12:00", "duration_seconds": 3600, "description": ""}
    ]
    expected_json = {
        "events": [
            {
                "title": "A",
                "time": "2024-01-05 12:00",
                "duration": 3600,
                "description": "",
            }
        ]
    }
    captured = {}

    async def mock_request(method, endpoint, *, params=None, json=None):
        captured["json"] = json
        return {"data": {"total": 1, "successful": 1, "results": []}}

    monkeypatch.setattr(service, "_request", mock_request)

    await service.add_events_bulk(events)

    assert captured["json"] == expected_json


@pytest.mark.asyncio
async def test_delete_events_bulk_uses_json(monkeypatch):
    service = CalendarService(base_url="http://test")

    ids = ["1", "2"]
    captured = {}

    async def mock_request(method, endpoint, *, params=None, json=None):
        captured["json"] = json
        return {"removed": 2, "requested": 2}

    monkeypatch.setattr(service, "_request", mock_request)

    await service.delete_events_bulk(ids)

    assert captured["json"] == {"ids": ids}
