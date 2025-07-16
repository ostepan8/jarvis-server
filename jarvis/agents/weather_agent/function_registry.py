# jarvis/agents/weather_agent/function_registry.py
from typing import Dict, Callable, Set
from ...services.weather_service import WeatherService


class WeatherFunctionRegistry:
    """Unified registry for weather functions and capabilities"""

    def __init__(self, weather_service: WeatherService):
        self.weather_service = weather_service
        self._function_map = self._build_function_map()

    def _build_function_map(self) -> Dict[str, Callable]:
        """Build the mapping of function names to weather service methods"""
        return {
            # Core weather functions
            "get_current_weather": self.weather_service.get_current_weather,
            "get_weather_forecast": self.weather_service.get_weather_forecast,
            "compare_weather_locations": self.weather_service.compare_weather_locations,
            "get_weather_recommendations": self.weather_service.get_weather_recommendations,
            "search_locations": self.weather_service.search_locations,
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

    @property
    def functions(self) -> Dict[str, Callable]:
        """Get the function mapping"""
        return self._function_map

    @property
    def capabilities(self) -> Set[str]:
        """Get capabilities as a set of all function names"""
        return set(self._function_map.keys())

    def get_function(self, function_name: str) -> Callable | None:
        """Get a specific function by name"""
        return self._function_map.get(function_name)

    def has_function(self, function_name: str) -> bool:
        """Check if a function exists"""
        return function_name in self._function_map

    def add_function(self, name: str, func: Callable) -> None:
        """Add a new function to the registry"""
        self._function_map[name] = func

    def remove_function(self, name: str) -> bool:
        """Remove a function from the registry"""
        if name in self._function_map:
            del self._function_map[name]
            return True
        return False
