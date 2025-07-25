# jarvis/agents/weather_agent/function_registry.py
from typing import Dict, Callable
from ...services.weather_service import WeatherService
from ...registry import FunctionRegistry


class WeatherFunctionRegistry(FunctionRegistry):
    """Unified registry for weather functions and capabilities"""

    def __init__(self, weather_service: WeatherService):
        self.weather_service = weather_service
        super().__init__(self._build_function_map())

    def _build_function_map(self) -> Dict[str, Callable]:
        """Build the mapping of function names to weather service methods"""
        return {
            # Core weather functions
            "get_current_weather": self.weather_service.get_current_weather,
            "get_weather_forecast": self.weather_service.get_weather_forecast,
            "compare_weather_locations": self.weather_service.compare_weather_locations,
            "get_weather_recommendations": self.weather_service.get_weather_recommendations,
            "search_locations_for_weather_service": self.weather_service.search_locations_for_weather_service,
            "get_air_quality": self.weather_service.get_air_quality,
            # Capability aliases (map user-friendly names to function names)
            "weather_command": self.weather_service.get_current_weather,
            "get_weather": self.weather_service.get_current_weather,
            "weather_forecast": self.weather_service.get_weather_forecast,
            "weather_comparison": self.weather_service.compare_weather_locations,
            "weather_advice": self.weather_service.get_weather_recommendations,
            "weather_planning": self.weather_service.get_weather_recommendations,
            "air_quality": self.weather_service.get_air_quality,
        }
