from __future__ import annotations

import os
from typing import Any, Dict, Optional, Set

import httpx

from ..base import NetworkAgent
from ..message import Message
from ...logger import JarvisLogger


class WeatherAgent(NetworkAgent):
    """Agent providing weather information via OpenWeatherMap."""

    def __init__(self, api_key: Optional[str] = None, logger: Optional[JarvisLogger] = None) -> None:
        super().__init__("WeatherAgent", logger)
        self.api_key = api_key or os.getenv("WEATHER_API_KEY") or os.getenv("OPENWEATHER_API_KEY")
        if not self.api_key:
            raise ValueError("Weather API key not provided")
        self.client = httpx.AsyncClient()

    async def close(self) -> None:
        await self.client.aclose()

    @property
    def description(self) -> str:
        return "Provides current weather and forecasts using OpenWeatherMap"

    @property
    def capabilities(self) -> Set[str]:
        return {"get_current_weather", "get_forecast"}

    async def get_current_weather(self, location: str) -> Dict[str, Any]:
        params = {"q": location, "appid": self.api_key, "units": "metric"}
        resp = await self.client.get("https://api.openweathermap.org/data/2.5/weather", params=params)
        data = resp.json()
        weather = data.get("weather", [{}])[0].get("description", "")
        temp = data.get("main", {}).get("temp")
        return {"location": location, "temperature": temp, "description": weather}

    async def get_forecast(self, location: str) -> Dict[str, Any]:
        params = {"q": location, "appid": self.api_key, "units": "metric", "cnt": 5}
        resp = await self.client.get("https://api.openweathermap.org/data/2.5/forecast", params=params)
        data = resp.json()
        forecast = [
            {
                "time": item.get("dt_txt"),
                "temperature": item.get("main", {}).get("temp"),
                "description": item.get("weather", [{}])[0].get("description", ""),
            }
            for item in data.get("list", [])
        ]
        return {"location": location, "forecast": forecast}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})
        if capability not in self.capabilities:
            return
        location = data.get("location") or data.get("city") or ""
        try:
            if capability == "get_current_weather":
                result = await self.get_current_weather(location)
            else:
                result = await self.get_forecast(location)
            await self.send_capability_response(message.from_agent, result, message.request_id, message.id)
        except Exception as exc:
            await self.send_error(message.from_agent, str(exc), message.request_id)

    async def _handle_capability_response(self, message: Message) -> None:
        self.logger.log("INFO", "WeatherAgent received response", str(message.content))
