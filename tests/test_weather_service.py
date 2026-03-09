"""
Tests for WeatherService.

Tests verify:
1. Service initialization (with key, without key raises ConfigurationError)
2. Sync API request with caching
3. Async API request with caching
4. Error handling (404, 401, non-200, timeout, generic errors)
5. Current weather retrieval and formatting
6. Forecast retrieval and daily summaries
7. Location comparison
8. Weather recommendations (temperature, conditions, activities)
9. Location search
10. Air quality
11. Helper methods (_format_time_for_speech, _get_wind_direction_text, _get_air_quality_advice)
"""

import pytest
import httpx
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

from jarvis.services.weather_service import WeatherService
from jarvis.core.errors import (
    ConfigurationError,
    InvalidParameterError,
    AuthenticationError,
    ServiceUnavailableError,
)


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = MagicMock()
    logger.log = MagicMock()
    return logger


@pytest.fixture
def weather_service(mock_logger):
    """Create a WeatherService with a test API key and no-retry config."""
    from jarvis.utils.retry_client import RetryConfig

    # Use 0 retries to make tests fast
    config = RetryConfig(max_retries=0, base_delay=0)
    service = WeatherService(
        api_key="test-weather-key",
        retry_config=config,
        logger=mock_logger,
    )
    return service


class TestWeatherServiceInit:
    """Tests for WeatherService initialization."""

    def test_init_with_explicit_key(self, mock_logger):
        """Test initialization with an explicit API key."""
        from jarvis.utils.retry_client import RetryConfig

        service = WeatherService(
            api_key="my-key",
            retry_config=RetryConfig(max_retries=0),
            logger=mock_logger,
        )
        assert service.api_key == "my-key"

    def test_init_with_env_var_weather_api_key(self, mock_logger):
        """Test initialization from WEATHER_API_KEY env var."""
        from jarvis.utils.retry_client import RetryConfig

        with patch.dict("os.environ", {"WEATHER_API_KEY": "env-key"}, clear=False):
            service = WeatherService(
                retry_config=RetryConfig(max_retries=0),
                logger=mock_logger,
            )
            assert service.api_key == "env-key"

    def test_init_with_env_var_openweather_api_key(self, mock_logger):
        """Test initialization from OPENWEATHER_API_KEY env var."""
        from jarvis.utils.retry_client import RetryConfig

        with patch.dict(
            "os.environ",
            {"OPENWEATHER_API_KEY": "openweather-key"},
            clear=True,
        ):
            service = WeatherService(
                retry_config=RetryConfig(max_retries=0),
                logger=mock_logger,
            )
            assert service.api_key == "openweather-key"

    def test_init_without_key_raises_configuration_error(self, mock_logger):
        """Test that initialization without an API key raises ConfigurationError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigurationError, match="Weather API key required"):
                WeatherService(api_key=None, logger=mock_logger)


class TestFormatTimeForSpeech:
    """Tests for the _format_time_for_speech helper."""

    def test_midnight(self, weather_service):
        """Test formatting midnight (0:00)."""
        # Create timestamp for midnight
        dt = datetime(2024, 1, 1, 0, 0, 0)
        result = weather_service._format_time_for_speech(dt.timestamp())
        assert result == "midnight"

    def test_noon(self, weather_service):
        """Test formatting noon (12:00)."""
        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = weather_service._format_time_for_speech(dt.timestamp())
        assert result == "noon"

    def test_morning_exact_hour(self, weather_service):
        """Test formatting a morning time with zero minutes."""
        dt = datetime(2024, 1, 1, 8, 0, 0)
        result = weather_service._format_time_for_speech(dt.timestamp())
        assert "8 o'clock" in result
        assert "morning" in result

    def test_afternoon_with_minutes(self, weather_service):
        """Test formatting an afternoon time with minutes."""
        dt = datetime(2024, 1, 1, 14, 30, 0)
        result = weather_service._format_time_for_speech(dt.timestamp())
        assert "2:30" in result
        assert "evening" in result

    def test_evening_time(self, weather_service):
        """Test formatting an evening time."""
        dt = datetime(2024, 1, 1, 20, 15, 0)
        result = weather_service._format_time_for_speech(dt.timestamp())
        assert "8:15" in result
        assert "evening" in result

    def test_zero_timestamp_returns_empty(self, weather_service):
        """Test that a zero/falsy timestamp returns empty string."""
        result = weather_service._format_time_for_speech(0)
        # timestamp 0 is falsy so returns ""
        assert result == ""

    def test_none_timestamp_returns_empty(self, weather_service):
        """Test that None timestamp returns empty string."""
        result = weather_service._format_time_for_speech(None)
        assert result == ""

    def test_minutes_less_than_10_padded(self, weather_service):
        """Test that minutes less than 10 are zero-padded."""
        dt = datetime(2024, 1, 1, 9, 5, 0)
        result = weather_service._format_time_for_speech(dt.timestamp())
        assert "9:05" in result


class TestGetWindDirectionText:
    """Tests for the _get_wind_direction_text helper."""

    def test_north(self, weather_service):
        """Test 0 degrees is north."""
        result = weather_service._get_wind_direction_text(0)
        assert "north" in result

    def test_east(self, weather_service):
        """Test 90 degrees is east."""
        result = weather_service._get_wind_direction_text(90)
        assert "east" in result

    def test_south(self, weather_service):
        """Test 180 degrees is south."""
        result = weather_service._get_wind_direction_text(180)
        assert "south" in result

    def test_west(self, weather_service):
        """Test 270 degrees is west."""
        result = weather_service._get_wind_direction_text(270)
        assert "west" in result

    def test_none_degrees(self, weather_service):
        """Test None degrees returns unknown."""
        result = weather_service._get_wind_direction_text(None)
        assert result == "unknown direction"

    def test_360_degrees_wraps_to_north(self, weather_service):
        """Test 360 degrees wraps back to north."""
        result = weather_service._get_wind_direction_text(360)
        assert "north" in result


class TestGetAirQualityAdvice:
    """Tests for the _get_air_quality_advice helper."""

    def test_good_air_quality(self, weather_service):
        """Test AQI 1 returns good advice."""
        result = weather_service._get_air_quality_advice(1)
        assert "good" in result.lower()

    def test_fair_air_quality(self, weather_service):
        """Test AQI 2 returns fair advice."""
        result = weather_service._get_air_quality_advice(2)
        assert "fair" in result.lower()

    def test_moderate_air_quality(self, weather_service):
        """Test AQI 3 returns moderate advice."""
        result = weather_service._get_air_quality_advice(3)
        assert "moderate" in result.lower()

    def test_poor_air_quality(self, weather_service):
        """Test AQI 4 returns poor advice."""
        result = weather_service._get_air_quality_advice(4)
        assert "poor" in result.lower()

    def test_very_poor_air_quality(self, weather_service):
        """Test AQI 5 returns very poor advice."""
        result = weather_service._get_air_quality_advice(5)
        assert "very poor" in result.lower()

    def test_unknown_air_quality(self, weather_service):
        """Test unknown AQI returns unavailable."""
        result = weather_service._get_air_quality_advice(99)
        assert "unavailable" in result.lower()


class TestGetCurrentWeather:
    """Tests for get_current_weather (sync)."""

    def test_get_current_weather_success(self, weather_service):
        """Test successful current weather retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "San Francisco",
            "main": {
                "temp": 65.5,
                "feels_like": 63.0,
                "humidity": 72,
                "pressure": 1013,
            },
            "weather": [{"description": "clear sky", "main": "Clear"}],
            "wind": {"speed": 5.2, "deg": 270},
            "visibility": 16093,
            "sys": {
                "country": "US",
                "sunrise": 1704110400,
                "sunset": 1704146400,
            },
        }

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.get_current_weather("San Francisco")

        assert result["location"] == "San Francisco"
        assert result["country"] == "US"
        assert result["temperature"] == 66  # rounded from 65.5
        assert result["feels_like"] == 63
        assert result["humidity"] == 72
        assert result["description"] == "Clear Sky"  # Title-cased
        assert result["condition"] == "clear"  # lowered
        assert result["wind_speed"] == 5.2
        assert "west" in result["wind_direction_text"]

    def test_get_current_weather_empty_weather_list(self, weather_service):
        """Test weather returns error when weather list is empty."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test City",
            "main": {"temp": 70, "feels_like": 68, "humidity": 50, "pressure": 1000},
            "weather": [],
            "wind": {"speed": 3, "deg": 180},
            "sys": {"country": "US"},
        }

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.get_current_weather("Test City")
        assert "error" in result

    def test_get_current_weather_404_not_found(self, weather_service):
        """Test weather returns error for unknown location."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.get_current_weather("Nonexistent City")
        assert "error" in result

    def test_get_current_weather_401_auth_error(self, weather_service):
        """Test weather returns error for invalid API key."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.get_current_weather("San Francisco")
        assert "error" in result

    def test_get_current_weather_caching(self, weather_service):
        """Test that weather results are cached."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "CachedCity",
            "main": {"temp": 70, "feels_like": 68, "humidity": 50, "pressure": 1000},
            "weather": [{"description": "cloudy", "main": "Clouds"}],
            "wind": {"speed": 3, "deg": 180},
            "visibility": 10000,
            "sys": {"country": "US", "sunrise": 1704110400, "sunset": 1704146400},
        }

        mock_client = MagicMock()
        mock_client.get = MagicMock(return_value=mock_response)
        weather_service._sync_client = mock_client

        # First call
        result1 = weather_service.get_current_weather("CachedCity")
        assert result1["location"] == "CachedCity"
        assert mock_client.get.call_count == 1

        # Second call should use cache
        result2 = weather_service.get_current_weather("CachedCity")
        assert result2["location"] == "CachedCity"
        # Should still be 1 call since cache was used
        assert mock_client.get.call_count == 1

    def test_get_current_weather_visibility_conversion(self, weather_service):
        """Test visibility is converted from meters to miles."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test",
            "main": {"temp": 70, "feels_like": 68, "humidity": 50, "pressure": 1000},
            "weather": [{"description": "clear", "main": "Clear"}],
            "wind": {"speed": 3, "deg": 0},
            "visibility": 16093,  # ~10 miles
            "sys": {"country": "US", "sunrise": 1704110400, "sunset": 1704146400},
        }

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.get_current_weather("Test")
        assert result["visibility"] == 10.0  # 16093 / 1609.34 ~ 10.0

    def test_get_current_weather_no_visibility(self, weather_service):
        """Test weather with no visibility data returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Test",
            "main": {"temp": 70, "feels_like": 68, "humidity": 50, "pressure": 1000},
            "weather": [{"description": "clear", "main": "Clear"}],
            "wind": {"speed": 3, "deg": 0},
            "sys": {"country": "US", "sunrise": 1704110400, "sunset": 1704146400},
        }

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.get_current_weather("Test")
        assert result["visibility"] is None


class TestGetWeatherForecast:
    """Tests for get_weather_forecast (sync)."""

    def test_get_forecast_success(self, weather_service):
        """Test successful forecast retrieval."""
        now = datetime.now()
        timestamp1 = int(now.timestamp())
        timestamp2 = int((now + timedelta(hours=3)).timestamp())

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "city": {"name": "TestCity"},
            "list": [
                {
                    "dt": timestamp1,
                    "main": {
                        "temp": 70,
                        "feels_like": 68,
                        "temp_min": 65,
                        "temp_max": 75,
                        "humidity": 55,
                    },
                    "weather": [{"description": "clear sky", "main": "Clear"}],
                    "wind": {"speed": 5},
                    "pop": 0.1,
                },
                {
                    "dt": timestamp2,
                    "main": {
                        "temp": 72,
                        "feels_like": 70,
                        "temp_min": 66,
                        "temp_max": 77,
                        "humidity": 50,
                    },
                    "weather": [{"description": "few clouds", "main": "Clouds"}],
                    "wind": {"speed": 7},
                    "pop": 0.2,
                },
            ],
        }

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.get_weather_forecast("TestCity", days=1)

        assert result["location"] == "TestCity"
        assert len(result["hourly_forecast"]) == 2
        assert result["forecast_days"] >= 1
        assert len(result["daily_forecast"]) >= 1

    def test_get_forecast_empty_list(self, weather_service):
        """Test forecast with empty list returns error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "city": {"name": "EmptyCity"},
            "list": [],
        }

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.get_weather_forecast("EmptyCity")
        assert "error" in result

    def test_get_forecast_with_invalid_items_skipped(self, weather_service):
        """Test that forecast items missing dt or main are skipped."""
        now = datetime.now()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "city": {"name": "TestCity"},
            "list": [
                {"main": {"temp": 70}},  # Missing dt
                {"dt": int(now.timestamp())},  # Missing main
                {
                    "dt": int(now.timestamp()),
                    "main": {
                        "temp": 72,
                        "feels_like": 70,
                        "temp_min": 65,
                        "temp_max": 75,
                        "humidity": 50,
                    },
                    "weather": [{"description": "clear", "main": "Clear"}],
                    "wind": {"speed": 5},
                    "pop": 0.0,
                },
            ],
        }

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.get_weather_forecast("TestCity")
        # Only valid item should be included
        assert len(result["hourly_forecast"]) == 1

    def test_get_forecast_error_handling(self, weather_service):
        """Test forecast error handling for server errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.get_weather_forecast("TestCity")
        assert "error" in result


class TestCompareWeatherLocations:
    """Tests for compare_weather_locations."""

    def test_compare_success(self, weather_service):
        """Test successful comparison of multiple locations."""
        call_count = 0

        def mock_get_weather(location):
            nonlocal call_count
            call_count += 1
            temps = {"City A": 90, "City B": 60}
            return {
                "location": location,
                "temperature": temps.get(location, 70),
                "humidity": 50 + call_count * 10,
                "wind_speed": 5.0 + call_count,
                "description": "Clear",
                "condition": "clear",
            }

        weather_service.get_current_weather = mock_get_weather

        result = weather_service.compare_weather_locations(["City A", "City B"])

        assert result["location_count"] == 2
        assert len(result["locations"]) == 2
        assert result["comparison"]["hottest"]["location"] == "City A"
        assert result["comparison"]["coldest"]["location"] == "City B"

    def test_compare_with_error_location(self, weather_service):
        """Test comparison when one location errors."""

        def mock_get_weather(location):
            if location == "Bad City":
                return {"error": "Not found"}
            return {
                "location": location,
                "temperature": 70,
                "humidity": 50,
                "wind_speed": 5.0,
            }

        weather_service.get_current_weather = mock_get_weather

        result = weather_service.compare_weather_locations(["Good City", "Bad City"])

        assert result["location_count"] == 2
        assert len(result["locations"]) == 2
        # Only Good City should be in comparison
        assert result["comparison"]["hottest"]["location"] == "Good City"

    def test_compare_all_errors_no_comparison(self, weather_service):
        """Test comparison when all locations error returns empty comparison."""

        def mock_get_weather(location):
            return {"error": "Not found"}

        weather_service.get_current_weather = mock_get_weather

        result = weather_service.compare_weather_locations(["Bad1", "Bad2"])
        assert result["comparison"] == {}


class TestWeatherRecommendations:
    """Tests for get_weather_recommendations."""

    def test_very_cold_weather_recommendations(self, weather_service):
        """Test recommendations for very cold weather (<32F)."""

        def mock_get_weather(location):
            return {
                "location": location,
                "temperature": 20,
                "feels_like": 15,
                "humidity": 40,
                "wind_speed": 3.0,
                "description": "Light Snow",
                "condition": "snow",
            }

        weather_service.get_current_weather = mock_get_weather
        result = weather_service.get_weather_recommendations("Cold City")

        recs = result["recommendations"]
        assert any("cold" in r.lower() or "bundle" in r.lower() for r in recs)
        assert any("snow" in r.lower() for r in recs)

    def test_hot_weather_recommendations(self, weather_service):
        """Test recommendations for hot weather (>86F)."""

        def mock_get_weather(location):
            return {
                "location": location,
                "temperature": 95,
                "feels_like": 100,
                "humidity": 85,
                "wind_speed": 2.0,
                "description": "Clear",
                "condition": "clear",
            }

        weather_service.get_current_weather = mock_get_weather
        result = weather_service.get_weather_recommendations("Hot City")

        recs = result["recommendations"]
        assert any("hot" in r.lower() or "hydrated" in r.lower() for r in recs)
        assert any("humidity" in r.lower() for r in recs)

    def test_rainy_weather_recommendations(self, weather_service):
        """Test recommendations for rainy conditions."""

        def mock_get_weather(location):
            return {
                "location": location,
                "temperature": 55,
                "feels_like": 50,
                "humidity": 90,
                "wind_speed": 12.0,
                "description": "Rain",
                "condition": "rain",
            }

        weather_service.get_current_weather = mock_get_weather
        result = weather_service.get_weather_recommendations("Rainy City")

        recs = result["recommendations"]
        assert any("rain" in r.lower() or "umbrella" in r.lower() for r in recs)
        assert any("wind" in r.lower() for r in recs)

    def test_hiking_activity_hot_weather(self, weather_service):
        """Test hiking recommendations in hot weather."""

        def mock_get_weather(location):
            return {
                "location": location,
                "temperature": 95,
                "feels_like": 98,
                "humidity": 30,
                "wind_speed": 5.0,
                "description": "Clear",
                "condition": "clear",
            }

        weather_service.get_current_weather = mock_get_weather
        result = weather_service.get_weather_recommendations("Desert", activity="hiking")

        recs = result["recommendations"]
        assert any("hiking" in r.lower() or "extra water" in r.lower() for r in recs)

    def test_travel_activity_recommendations(self, weather_service):
        """Test travel activity recommendations."""

        def mock_get_weather(location):
            return {
                "location": location,
                "temperature": 70,
                "feels_like": 70,
                "humidity": 50,
                "wind_speed": 5.0,
                "description": "Clear",
                "condition": "clear",
            }

        weather_service.get_current_weather = mock_get_weather
        result = weather_service.get_weather_recommendations("City", activity="travel")

        recs = result["recommendations"]
        assert any("destination" in r.lower() for r in recs)

    def test_recommendations_with_error_weather(self, weather_service):
        """Test recommendations when weather retrieval fails."""

        def mock_get_weather(location):
            return {"error": "Not found"}

        weather_service.get_current_weather = mock_get_weather
        result = weather_service.get_weather_recommendations("Bad City")
        assert "error" in result

    def test_low_humidity_recommendation(self, weather_service):
        """Test recommendation for low humidity."""

        def mock_get_weather(location):
            return {
                "location": location,
                "temperature": 70,
                "feels_like": 70,
                "humidity": 20,
                "wind_speed": 3.0,
                "description": "Clear",
                "condition": "clear",
            }

        weather_service.get_current_weather = mock_get_weather
        result = weather_service.get_weather_recommendations("Dry City")

        recs = result["recommendations"]
        assert any("humidity" in r.lower() or "hydrated" in r.lower() for r in recs)


class TestSearchLocations:
    """Tests for search_locations_for_weather_service."""

    def test_search_locations_success(self, weather_service):
        """Test successful location search."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "San Francisco", "country": "US", "state": "California"},
            {"name": "San Fernando", "country": "PH"},
        ]

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.search_locations_for_weather_service("San")

        assert result["query"] == "San"
        assert result["count"] == 2
        assert result["locations"][0]["name"] == "San Francisco"

    def test_search_locations_not_found(self, weather_service):
        """Test location search returns 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.search_locations_for_weather_service("XYZ")
        assert "error" in result

    def test_search_locations_server_error(self, weather_service):
        """Test location search with server error."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service.search_locations_for_weather_service("Test")
        assert "error" in result

    def test_search_locations_exception(self, weather_service):
        """Test location search with network exception."""
        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(
            side_effect=httpx.ConnectError("Connection failed")
        )

        result = weather_service.search_locations_for_weather_service("Test")
        assert "error" in result


class TestGetAirQuality:
    """Tests for get_air_quality."""

    def test_get_air_quality_success(self, weather_service):
        """Test successful air quality retrieval."""
        geo_response = MagicMock()
        geo_response.status_code = 200
        geo_response.json.return_value = [
            {"lat": 37.7749, "lon": -122.4194, "name": "San Francisco"}
        ]

        aqi_response = MagicMock()
        aqi_response.status_code = 200
        aqi_response.json.return_value = {
            "list": [
                {
                    "main": {"aqi": 2},
                    "components": {"pm2_5": 10.5, "pm10": 20.3},
                }
            ]
        }

        call_count = 0

        def mock_get(url, params=None):
            nonlocal call_count
            call_count += 1
            if "geo" in url:
                return geo_response
            return aqi_response

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = mock_get

        result = weather_service.get_air_quality("San Francisco")

        assert result["location"] == "San Francisco"
        assert result["air_quality_index"] == 2
        assert result["air_quality_level"] == "Fair"
        assert "fair" in result["health_advice"].lower()

    def test_get_air_quality_location_not_found(self, weather_service):
        """Test air quality when geocoding returns no results."""
        geo_response = MagicMock()
        geo_response.status_code = 200
        geo_response.json.return_value = []

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=geo_response)

        result = weather_service.get_air_quality("Nowhere")
        assert "error" in result

    def test_get_air_quality_geocode_api_error(self, weather_service):
        """Test air quality when geocode API returns error status."""
        geo_response = MagicMock()
        geo_response.status_code = 404

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=geo_response)

        result = weather_service.get_air_quality("Bad City")
        assert "error" in result

    def test_get_air_quality_missing_coordinates(self, weather_service):
        """Test air quality when geocode returns data without coordinates."""
        geo_response = MagicMock()
        geo_response.status_code = 200
        geo_response.json.return_value = [{"name": "Test"}]  # no lat/lon

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=geo_response)

        result = weather_service.get_air_quality("Test")
        assert "error" in result

    def test_get_air_quality_aqi_api_error(self, weather_service):
        """Test air quality when AQI API returns error status."""
        geo_response = MagicMock()
        geo_response.status_code = 200
        geo_response.json.return_value = [{"lat": 37.0, "lon": -122.0}]

        aqi_response = MagicMock()
        aqi_response.status_code = 500

        def mock_get(url, params=None):
            if "geo" in url:
                return geo_response
            return aqi_response

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = mock_get

        result = weather_service.get_air_quality("Test")
        assert "error" in result


class TestSyncApiRequestErrorHandling:
    """Tests for _make_sync_api_request error handling."""

    def test_timeout_raises_service_unavailable(self, weather_service):
        """Test that timeout raises ServiceUnavailableError."""
        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(
            side_effect=httpx.TimeoutException("timed out")
        )

        with pytest.raises(ServiceUnavailableError, match="timeout"):
            weather_service._make_sync_api_request("weather", {"q": "Test"})

    def test_404_raises_invalid_parameter(self, weather_service):
        """Test that 404 raises InvalidParameterError."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        with pytest.raises(InvalidParameterError, match="Location not found"):
            weather_service._make_sync_api_request("weather", {"q": "Unknown"})

    def test_401_raises_authentication_error(self, weather_service):
        """Test that 401 raises AuthenticationError."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        with pytest.raises(AuthenticationError, match="Invalid Weather API key"):
            weather_service._make_sync_api_request("weather", {"q": "Test"})

    def test_500_raises_service_unavailable(self, weather_service):
        """Test that 500 raises ServiceUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        with pytest.raises(ServiceUnavailableError, match="500"):
            weather_service._make_sync_api_request("weather", {"q": "Test"})

    def test_cache_hit_returns_cached_data(self, weather_service):
        """Test that cached data is returned for valid cache key."""
        cached_data = {"temp": 70}
        weather_service.weather_cache["test_key"] = (cached_data, datetime.now())

        result = weather_service._make_sync_api_request(
            "weather", {"q": "Test"}, cache_key="test_key"
        )
        assert result == cached_data

    def test_expired_cache_makes_new_request(self, weather_service):
        """Test that expired cache triggers a new request."""
        expired_time = datetime.now() - timedelta(seconds=600)
        weather_service.weather_cache["test_key"] = ({"old": True}, expired_time)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"new": True}

        weather_service._sync_client = MagicMock()
        weather_service._sync_client.get = MagicMock(return_value=mock_response)

        result = weather_service._make_sync_api_request(
            "weather", {"q": "Test"}, cache_key="test_key"
        )
        assert result == {"new": True}
