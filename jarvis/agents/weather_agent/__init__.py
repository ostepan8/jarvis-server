from __future__ import annotations

import os
import asyncio
import functools
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Set, List, Union

import httpx

from ..base import NetworkAgent
from ..message import Message
from ...logger import JarvisLogger
from ...ai_clients.base import BaseAIClient


class WeatherAgent(NetworkAgent):
    """
    Conversational weather agent that uses LLM to translate natural language
    weather requests into specific tool calls for comprehensive weather information.
    """

    def __init__(
        self,
        ai_client: BaseAIClient,
        api_key: Optional[str] = None,
        logger: Optional[JarvisLogger] = None,
        default_location: str = "Chicago",  # Default location when none specified
    ) -> None:
        super().__init__("WeatherAgent", logger)
        self.ai_client = ai_client

        # API Configuration
        self.api_key = (
            api_key or os.getenv("WEATHER_API_KEY") or os.getenv("OPENWEATHER_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "Weather API key required. Set WEATHER_API_KEY or OPENWEATHER_API_KEY"
            )

        self.client = httpx.AsyncClient(timeout=10.0)
        self.default_location = default_location

        # Simple cache to avoid repeated API calls
        self.weather_cache = {}
        self.cache_duration = 300  # 5 minutes

        # Enhanced system prompt for natural weather conversations
        self.system_prompt = """
        You are JARVIS, an advanced AI weather assistant with access to comprehensive weather tools. You provide natural, conversational weather information and advice.

        WEATHER CAPABILITIES:
        - Current weather conditions with detailed metrics
        - Multi-day forecasts and hourly breakdowns
        - Weather comparisons between locations
        - Activity-based weather recommendations
        - Travel weather planning and alerts
        - Air quality information
        - Sunrise/sunset times
        - Weather pattern analysis and insights

        CONVERSATION STYLE:
        - Be conversational and personable, not robotic
        - Provide practical insights and actionable advice
        - Consider what weather means for daily activities
        - Use natural language, avoid technical jargon
        - Add context about what to expect or prepare for
        - Share interesting weather observations when relevant
        - Adapt responses to user's specific needs and questions

        LOCATION HANDLING:
        - If user asks about weather without specifying a location, ask them which city they want weather for
        - NEVER use "current location" as a location parameter - always use specific city names
        - If location is unclear, use the search_locations tool to find valid options
        - Default to major cities if user is vague (e.g., "Chicago" for general US queries)

        TOOL USAGE GUIDELINES:
        1. Always get current weather data first when asked about weather
        2. Use forecast data for planning questions or "tomorrow/later" requests
        3. For travel questions, compare weather between locations
        4. Provide recommendations based on actual weather conditions
        5. Use location search if user's location is unclear
        6. Get air quality data when health concerns are mentioned
        7. IMPORTANT: Only use specific city names like "Chicago", "New York", "London" - never "current location"

        RESPONSE APPROACH:
        - Start with the most relevant weather information
        - Explain what it means practically (what to wear, activities, etc.)
        - Provide forward-looking insights when helpful
        - Be encouraging and helpful with weather-related planning
        - Address safety concerns when weather is severe

        Given a user's weather-related question, use the appropriate tools to get current data, then provide a natural, conversational response with practical advice.
        """.strip()

        # Weather tools available to the LLM
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_current_weather",
                    "description": "Get current weather conditions for a specific location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "Specific city name, e.g., 'Chicago', 'New York', 'London'. Never use 'current location' - always ask user for city name if unclear.",
                            }
                        },
                        "required": ["location"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather_forecast",
                    "description": "Get weather forecast for next few days",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "Specific city name, e.g., 'Chicago', 'New York', 'London'. Never use 'current location'.",
                            },
                            "days": {
                                "type": "integer",
                                "description": "Number of days to forecast (1-5)",
                                "default": 3,
                            },
                        },
                        "required": ["location"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "compare_weather_locations",
                    "description": "Compare current weather between multiple locations",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "locations": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of city names to compare",
                            }
                        },
                        "required": ["locations"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather_recommendations",
                    "description": "Get weather-based recommendations for activities, clothing, travel",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "Specific city name, never 'current location'",
                            },
                            "activity": {
                                "type": "string",
                                "description": "Planned activity (e.g., 'outdoor event', 'travel', 'hiking')",
                                "default": "general",
                            },
                        },
                        "required": ["location"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_locations",
                    "description": "Search for location names when user input is unclear",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for location",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_air_quality",
                    "description": "Get air quality information for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "Specific city name, never 'current location'",
                            }
                        },
                        "required": ["location"],
                    },
                },
            },
        ]

        # Map function names to methods
        self.intent_map = {
            "get_current_weather": self._get_current_weather,
            "get_weather_forecast": self._get_weather_forecast,
            "compare_weather_locations": self._compare_weather_locations,
            "get_weather_recommendations": self._get_weather_recommendations,
            "search_locations": self._search_locations,
            "get_air_quality": self._get_air_quality,
        }

    async def close(self) -> None:
        """Clean up resources."""
        await self.client.aclose()

    @property
    def description(self) -> str:
        return "Conversational weather agent providing comprehensive weather information and practical advice"

    @property
    def capabilities(self) -> Set[str]:
        return {
            "weather_command",
            "get_weather",
            "weather_forecast",
            "weather_comparison",
            "weather_advice",
            "weather_planning",
            "air_quality",
        }

    async def _execute_function(
        self, function_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a weather function with proper error handling."""
        func = self.intent_map.get(function_name)
        if not func:
            return {"error": f"Unknown function: {function_name}"}

        try:
            call = functools.partial(func, **arguments)
            result = await asyncio.get_running_loop().run_in_executor(None, call)
            return {"result": result}
        except Exception as exc:
            error = {"error": str(exc), "function": function_name, "args": arguments}
            self.logger.log(
                "ERROR", f"Error executing {function_name}", json.dumps(error)
            )
            return error

    async def _make_api_request(
        self, endpoint: str, params: Dict[str, Any], cache_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make API request with caching and error handling."""
        # Check cache first
        if cache_key and cache_key in self.weather_cache:
            cached_data, cached_time = self.weather_cache[cache_key]
            if datetime.now() - cached_time < timedelta(seconds=self.cache_duration):
                return cached_data

        # Add API key to params and use imperial units (Fahrenheit)
        params["appid"] = self.api_key
        params["units"] = "imperial"  # Use Fahrenheit instead of Celsius

        try:
            response = await self.client.get(
                f"https://api.openweathermap.org/data/2.5/{endpoint}", params=params
            )

            if response.status_code == 404:
                raise ValueError(f"Location not found: {params.get('q', 'unknown')}")
            elif response.status_code == 401:
                raise ValueError("Invalid API key")
            elif response.status_code != 200:
                raise ValueError(f"Weather service error: {response.status_code}")

            data = response.json()

            # Cache successful response
            if cache_key:
                self.weather_cache[cache_key] = (data, datetime.now())

            return data

        except httpx.TimeoutException:
            raise ValueError("Weather service timeout")
        except Exception as e:
            raise ValueError(f"Weather API error: {str(e)}")

    # ==================== WEATHER TOOL FUNCTIONS ====================

    def _get_current_weather(self, location: str) -> Dict[str, Any]:
        """Get comprehensive current weather data in Fahrenheit."""
        try:
            cache_key = f"current_{location}"
            data = asyncio.run(
                self._make_api_request("weather", {"q": location}, cache_key)
            )

            # Extract and format weather data - now in Fahrenheit
            main = data.get("main", {})
            weather = data.get("weather", [{}])[0]
            wind = data.get("wind", {})
            sys = data.get("sys", {})

            return {
                "location": data.get("name", location),
                "country": sys.get("country", ""),
                "temperature": round(
                    main.get("temp", 0)
                ),  # Already in Fahrenheit, rounded
                "feels_like": round(main.get("feels_like", 0)),
                "humidity": main.get("humidity", 0),
                "pressure": main.get("pressure", 0),
                "description": weather.get("description", "").title(),
                "condition": weather.get("main", "").lower(),
                "wind_speed": round(
                    wind.get("speed", 0), 1
                ),  # mph but will be converted to speech
                "wind_direction": wind.get("deg", 0),
                "wind_direction_text": self._get_wind_direction_text(
                    wind.get("deg", 0)
                ),
                "visibility": (
                    round(data.get("visibility", 0) / 1609.34, 1)
                    if data.get("visibility")
                    else None
                ),  # Convert to miles
                "sunrise": (
                    self._format_time_for_speech(sys.get("sunrise"))
                    if sys.get("sunrise")
                    else None
                ),
                "sunset": (
                    self._format_time_for_speech(sys.get("sunset"))
                    if sys.get("sunset")
                    else None
                ),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"error": f"Could not get weather for {location}: {str(e)}"}

    def _get_weather_forecast(self, location: str, days: int = 3) -> Dict[str, Any]:
        """Get weather forecast for multiple days in Fahrenheit."""
        try:
            cache_key = f"forecast_{location}_{days}"
            data = asyncio.run(
                self._make_api_request(
                    "forecast", {"q": location, "cnt": days * 8}, cache_key
                )
            )

            # Process forecast data - now in Fahrenheit
            daily_forecasts = {}
            hourly_forecasts = []

            for item in data.get("list", []):
                dt = datetime.fromtimestamp(item["dt"])
                date_key = dt.date().isoformat()

                forecast_item = {
                    "datetime": dt.isoformat(),
                    "date": date_key,
                    "time": self._format_time_for_speech(dt.timestamp()),
                    "temperature": round(item["main"]["temp"]),
                    "feels_like": round(item["main"]["feels_like"]),
                    "min_temp": round(item["main"]["temp_min"]),
                    "max_temp": round(item["main"]["temp_max"]),
                    "humidity": item["main"]["humidity"],
                    "description": item["weather"][0]["description"].title(),
                    "condition": item["weather"][0]["main"].lower(),
                    "precipitation_chance": round(item.get("pop", 0) * 100),
                    "wind_speed": round(item["wind"]["speed"], 1),  # mph
                }

                hourly_forecasts.append(forecast_item)

                # Group by day
                if date_key not in daily_forecasts:
                    daily_forecasts[date_key] = []
                daily_forecasts[date_key].append(forecast_item)

            # Create daily summaries
            daily_summaries = []
            for date, day_items in daily_forecasts.items():
                daily_summaries.append(
                    {
                        "date": date,
                        "day_name": datetime.fromisoformat(date).strftime("%A"),
                        "min_temp": min(item["min_temp"] for item in day_items),
                        "max_temp": max(item["max_temp"] for item in day_items),
                        "description": max(
                            set(item["description"] for item in day_items),
                            key=[item["description"] for item in day_items].count,
                        ),
                        "precipitation_chance": max(
                            item["precipitation_chance"] for item in day_items
                        ),
                        "avg_humidity": round(
                            sum(item["humidity"] for item in day_items) / len(day_items)
                        ),
                    }
                )

            return {
                "location": data["city"]["name"],
                "daily_forecast": daily_summaries,
                "hourly_forecast": hourly_forecasts,
                "forecast_days": len(daily_summaries),
            }

        except Exception as e:
            return {"error": f"Could not get forecast for {location}: {str(e)}"}

    def _format_time_for_speech(self, timestamp: float) -> str:
        """Format time for natural speech without AM/PM abbreviations."""
        if not timestamp:
            return ""

        dt = datetime.fromtimestamp(timestamp)
        hour = dt.hour
        minute = dt.minute

        # Convert to 12-hour format
        if hour == 0:
            hour_str = "12"
            period = "midnight"
        elif hour < 12:
            hour_str = str(hour)
            period = "in the morning"
        elif hour == 12:
            hour_str = "12"
            period = "noon" if minute == 0 else "in the afternoon"
        else:
            hour_str = str(hour - 12)
            period = "in the evening"

        # Format minutes
        if minute == 0:
            if period in ["midnight", "noon"]:
                return period
            else:
                return f"{hour_str} o'clock {period}"
        else:
            minute_str = f"{minute:02d}" if minute < 10 else str(minute)
            return f"{hour_str}:{minute_str} {period}"

    def _get_wind_direction_text(self, degrees: int) -> str:
        """Convert wind direction degrees to natural speech."""
        if degrees is None:
            return "unknown direction"

        # Convert degrees to cardinal directions
        directions = [
            "north",
            "north northeast",
            "northeast",
            "east northeast",
            "east",
            "east southeast",
            "southeast",
            "south southeast",
            "south",
            "south southwest",
            "southwest",
            "west southwest",
            "west",
            "west northwest",
            "northwest",
            "north northwest",
        ]

        index = round(degrees / 22.5) % 16
        return f"from the {directions[index]}"

    def _compare_weather_locations(self, locations: List[str]) -> Dict[str, Any]:
        """Compare weather between multiple locations in Fahrenheit."""
        try:
            weather_data = []

            for location in locations:
                try:
                    data = self._get_current_weather(location)
                    if "error" not in data:
                        weather_data.append(data)
                    else:
                        weather_data.append(
                            {"location": location, "error": data["error"]}
                        )
                except Exception as e:
                    weather_data.append({"location": location, "error": str(e)})

            # Find extremes for comparison
            valid_data = [d for d in weather_data if "error" not in d]
            comparison = {}

            if valid_data:
                comparison = {
                    "hottest": max(valid_data, key=lambda x: x["temperature"]),
                    "coldest": min(valid_data, key=lambda x: x["temperature"]),
                    "most_humid": max(valid_data, key=lambda x: x["humidity"]),
                    "windiest": max(valid_data, key=lambda x: x["wind_speed"]),
                }

            return {
                "locations": weather_data,
                "comparison": comparison,
                "location_count": len(locations),
            }

        except Exception as e:
            return {"error": f"Could not compare weather: {str(e)}"}

    def _get_weather_recommendations(
        self, location: str, activity: str = "general"
    ) -> Dict[str, Any]:
        """Get weather-based recommendations for activities in Fahrenheit."""
        try:
            weather_data = self._get_current_weather(location)
            if "error" in weather_data:
                return weather_data

            temp = weather_data["temperature"]  # Now in Fahrenheit
            condition = weather_data["condition"].lower()
            humidity = weather_data["humidity"]
            wind_speed = weather_data["wind_speed"]

            recommendations = []

            # Temperature recommendations in Fahrenheit
            if temp < 32:
                recommendations.append(
                    "Very cold weather! Bundle up with winter coat, hat, gloves, and warm boots."
                )
            elif temp < 50:
                recommendations.append(
                    "Cold weather. Wear a warm jacket, scarf, and closed shoes."
                )
            elif temp < 68:
                recommendations.append(
                    "Mild temperature. Light jacket or sweater recommended."
                )
            elif temp < 86:
                recommendations.append(
                    "Pleasant weather! Great for most outdoor activities."
                )
            else:
                recommendations.append(
                    "Very hot! Stay hydrated, seek shade, wear light clothing and sunscreen."
                )

            # Weather condition recommendations
            if "rain" in condition or "drizzle" in condition:
                recommendations.append("Rain expected. Bring an umbrella or raincoat!")
            elif "snow" in condition:
                recommendations.append(
                    "Snow conditions. Wear appropriate footwear and drive carefully."
                )
            elif "storm" in condition or "thunder" in condition:
                recommendations.append(
                    "Thunderstorms possible. Stay indoors if possible, avoid outdoor activities."
                )
            elif "fog" in condition or "mist" in condition:
                recommendations.append(
                    "Foggy conditions. Drive carefully with headlights on."
                )

            # Wind recommendations (mph)
            if wind_speed > 10:
                recommendations.append(
                    "Windy conditions. Secure loose items and be cautious with umbrellas."
                )

            # Humidity recommendations
            if humidity > 80:
                recommendations.append(
                    "High humidity. You might feel warmer than the actual temperature."
                )
            elif humidity < 30:
                recommendations.append(
                    "Low humidity. Stay hydrated and consider moisturizer."
                )

            # Activity-specific recommendations
            if activity == "outdoor event":
                if temp > 77 and "sun" in condition:
                    recommendations.append(
                        "Perfect for outdoor events! Consider shade and hydration stations."
                    )
                elif "rain" in condition:
                    recommendations.append(
                        "Consider indoor alternatives or weatherproof setup."
                    )
            elif activity == "travel":
                recommendations.append(
                    "Check weather at your destination too for appropriate packing."
                )
            elif activity == "hiking":
                if temp > 86:
                    recommendations.append(
                        "Hot hiking conditions. Start early, bring extra water."
                    )
                elif "rain" in condition:
                    recommendations.append(
                        "Wet hiking conditions. Waterproof gear and proper footwear essential."
                    )

            return {
                "location": location,
                "activity": activity,
                "weather_summary": f"{temp} degrees Fahrenheit, {weather_data['description']}",
                "recommendations": recommendations,
            }

        except Exception as e:
            return {"error": f"Could not get recommendations: {str(e)}"}

    def _search_locations(self, query: str) -> Dict[str, Any]:
        """Search for locations matching the query."""
        try:
            response = asyncio.run(
                self.client.get(
                    "https://api.openweathermap.org/geo/1.0/direct",
                    params={"q": query, "limit": 5, "appid": self.api_key},
                )
            )

            if response.status_code == 200:
                locations = []
                for item in response.json():
                    locations.append(
                        {
                            "name": item.get("name"),
                            "country": item.get("country"),
                            "state": item.get("state"),
                            "full_name": f"{item.get('name')}, {item.get('state', '')}, {item.get('country')}".strip(
                                ", "
                            ),
                        }
                    )

                return {"query": query, "locations": locations, "count": len(locations)}

            return {"error": "Location search failed"}

        except Exception as e:
            return {"error": f"Could not search locations: {str(e)}"}

    def _get_air_quality(self, location: str) -> Dict[str, Any]:
        """Get air quality information for a location."""
        try:
            # First get coordinates
            geocode_response = asyncio.run(
                self.client.get(
                    "https://api.openweathermap.org/geo/1.0/direct",
                    params={"q": location, "limit": 1, "appid": self.api_key},
                )
            )

            if geocode_response.status_code != 200 or not geocode_response.json():
                return {"error": f"Could not find coordinates for {location}"}

            coords = geocode_response.json()[0]
            lat, lon = coords["lat"], coords["lon"]

            # Get air quality data
            aqi_response = asyncio.run(
                self.client.get(
                    "https://api.openweathermap.org/data/2.5/air_pollution",
                    params={"lat": lat, "lon": lon, "appid": self.api_key},
                )
            )

            if aqi_response.status_code == 200:
                data = aqi_response.json()
                aqi_data = data.get("list", [{}])[0]

                aqi_levels = {
                    1: "Good",
                    2: "Fair",
                    3: "Moderate",
                    4: "Poor",
                    5: "Very Poor",
                }
                aqi = aqi_data.get("main", {}).get("aqi", 0)

                return {
                    "location": location,
                    "air_quality_index": aqi,
                    "air_quality_level": aqi_levels.get(aqi, "Unknown"),
                    "components": aqi_data.get("components", {}),
                    "health_advice": self._get_air_quality_advice(aqi),
                }

            return {"error": "Air quality data not available"}

        except Exception as e:
            return {"error": f"Could not get air quality: {str(e)}"}

    def _get_air_quality_advice(self, aqi: int) -> str:
        """Get health advice based on air quality index."""
        if aqi == 1:
            return "Air quality is good. Great for outdoor activities!"
        elif aqi == 2:
            return "Air quality is fair. Outdoor activities are generally safe."
        elif aqi == 3:
            return "Air quality is moderate. Sensitive individuals should limit outdoor exertion."
        elif aqi == 4:
            return "Air quality is poor. Everyone should limit outdoor activities."
        elif aqi == 5:
            return "Air quality is very poor. Avoid outdoor activities, especially exercise."
        else:
            return "Air quality data unavailable."

    # ==================== MAIN PROCESSING METHOD ====================

    async def _process_weather_command(self, command: str) -> Dict[str, Any]:
        """Process natural language weather command using LLM and tools."""
        self.logger.log("INFO", "=== PROCESSING WEATHER COMMAND ===", command)

        # Enhanced system message with location context
        system_message = f"""{self.system_prompt}

LOCATION CONTEXT:
- User is likely in or asking about the Chicago area (default location)
- When user asks about weather without specifying location, be helpful by:
  1. Offering to check weather for Chicago (since that's likely where they are)
  2. Or asking which city they'd prefer
- Make it conversational: "I can check the weather for Chicago, or did you have a different city in mind?"
- If user seems to want local weather, go ahead and check Chicago weather
- Always use specific city names in tool calls, never "current location" or similar

IMPORTANT RESPONSE FORMATTING:
- ABSOLUTELY NO symbols, abbreviations, or special characters: no %, °, mph, km, AM, PM, etc.
- Use only complete words in natural speech
- Say "percent" not "%", "degrees" not "°", "miles per hour" not "mph"  
- Use "in the morning" not "AM", "in the evening" not "PM"
- Avoid technical abbreviations - use full descriptive phrases
- Write everything as you would speak it naturally in conversation
- Example: "82 degrees Fahrenheit" not "82°F", "56 percent humidity" not "56%"

Remember: Be conversational and proactive - if they ask "what's the weather today" you can reasonably assume they want local weather (Chicago) unless they specify otherwise."""

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": command},
        ]

        actions_taken = []
        iterations = 0

        while iterations < 5:  # Limit iterations to prevent infinite loops
            self.logger.log("INFO", f"Weather command iteration {iterations + 1}")

            message, tool_calls = await self.ai_client.strong_chat(messages, self.tools)

            self.logger.log("INFO", f"AI response: {message.content}")
            self.logger.log(
                "INFO", f"Tool calls: {len(tool_calls) if tool_calls else 0}"
            )

            if not tool_calls:
                self.logger.log("INFO", "No more tool calls - conversation complete")
                break

            messages.append(message.model_dump())

            # Execute tool calls
            for call in tool_calls:
                function_name = call.function.name
                arguments = json.loads(call.function.arguments)

                self.logger.log(
                    "INFO", f"Executing: {function_name}", json.dumps(arguments)
                )

                result = await self._execute_function(function_name, arguments)

                self.logger.log(
                    "DEBUG", f"Tool result: {function_name}", json.dumps(result)
                )

                actions_taken.append(
                    {
                        "function": function_name,
                        "arguments": arguments,
                        "result": result,
                    }
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )

            iterations += 1

        final_response = (
            message.content if hasattr(message, "content") else str(message)
        )

        self.logger.log("INFO", "=== WEATHER COMMAND COMPLETE ===")
        self.logger.log("INFO", f"Total actions: {len(actions_taken)}")

        return {
            "response": final_response,
            "actions": actions_taken,
            "iterations": iterations,
        }

    # ==================== CAPABILITY HANDLERS ====================

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests."""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        self.logger.log("INFO", f"WeatherAgent handling: {capability}")

        try:
            command = data.get("command", data.get("message", ""))
            if not command:
                await self.send_error(
                    message.from_agent,
                    "No weather command provided",
                    message.request_id,
                )
                return

            result = await self._process_weather_command(command)

            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

        except Exception as e:
            self.logger.log("ERROR", f"WeatherAgent error: {e}")

            error_response = {
                "response": f"I'm having trouble with weather information right now. {str(e)} Could you try again?",
                "actions": [],
                "error": str(e),
            }

            await self.send_capability_response(
                message.from_agent, error_response, message.request_id, message.id
            )

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle responses from other agents."""
        self.logger.log("DEBUG", f"WeatherAgent received response: {message.content}")
