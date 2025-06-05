import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta
import aiohttp
import os
from openai import AsyncOpenAI
import anthropic

# You can use either OpenAI or Anthropic for the AI reasoning
# Comment out the one you're not using


class AICalendarAgent:
    """AI agent that interprets natural language and executes calendar operations"""

    def __init__(
        self,
        api_base_url: str = "http://localhost:8080",
        ai_provider: str = "openai",  # or "anthropic"
        api_key: str = None,
    ):

        self.api_base_url = api_base_url
        self.ai_provider = ai_provider

        # Initialize AI client
        if ai_provider == "openai":
            self.ai_client = AsyncOpenAI(
                api_key=api_key or os.environ.get("OPENAI_API_KEY")
            )
            self.model = "gpt-4-turbo-preview"
        elif ai_provider == "anthropic":
            self.ai_client = anthropic.AsyncAnthropic(
                api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
            )
            self.model = "claude-3-opus-20240229"
        else:
            raise ValueError(f"Unsupported AI provider: {ai_provider}")

        # Define available tools for the AI
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_today_events",
                    "description": "Get all events scheduled for today",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_events_by_date",
                    "description": "Get all events for a specific date",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format",
                            }
                        },
                        "required": ["date"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_event",
                    "description": "Add a new event to the calendar",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format",
                            },
                            "time": {
                                "type": "string",
                                "description": "Time in HH:MM format",
                            },
                            "duration_minutes": {"type": "integer", "default": 60},
                            "description": {"type": "string", "default": ""},
                        },
                        "required": ["title", "date", "time"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_event",
                    "description": "Delete an event by its ID",
                    "parameters": {
                        "type": "object",
                        "properties": {"event_id": {"type": "string"}},
                        "required": ["event_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_schedule",
                    "description": "Analyze schedule patterns and provide insights",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_range": {"type": "string", "default": "today"}
                        },
                        "required": [],
                    },
                },
            },
        ]

        # System prompt to guide the AI
        self.system_prompt = """You are a calendar management assistant. You help users manage their schedule by:
1. Understanding their natural language requests
2. Breaking down complex requests into individual API calls
3. Executing the necessary calendar operations in the correct order
4. Providing clear feedback about what was done

Current date: {current_date}

When moving events, always:
- First get the events from the source
- Delete each event
- Add it to the new date/time

Be proactive in understanding user intent. For example:
- "Clear my afternoon" means delete all events after 12:00 PM
- "Move everything to tomorrow" means get today's events and recreate them tomorrow
- "Find time for a meeting" means analyze the schedule and suggest free slots
"""

    async def _make_api_request(
        self, method: str, endpoint: str, data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to the C++ API"""
        url = f"{self.api_base_url}{endpoint}"

        async with aiohttp.ClientSession() as session:
            try:
                if method == "GET":
                    async with session.get(url) as response:
                        result = await response.json()
                elif method == "POST":
                    async with session.post(url, json=data) as response:
                        result = await response.json()
                elif method == "DELETE":
                    async with session.delete(url) as response:
                        result = await response.json()

                if result.get("status") == "error":
                    raise Exception(
                        f"API Error: {result.get('message', 'Unknown error')}"
                    )

                return result
            except Exception as e:
                return {"error": str(e)}

    async def _execute_function(
        self, function_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a calendar function based on AI's decision"""

        if function_name == "get_today_events":
            today = date.today().strftime("%Y-%m-%d")
            result = await self._make_api_request("GET", f"/events/day/{today}")
            events = result.get("data", [])
            return {"date": today, "event_count": len(events), "events": events}

        elif function_name == "get_events_by_date":
            date_str = arguments["date"]
            result = await self._make_api_request("GET", f"/events/day/{date_str}")
            events = result.get("data", [])
            return {"date": date_str, "event_count": len(events), "events": events}

        elif function_name == "add_event":
            datetime_str = f"{arguments['date']} {arguments['time']}"
            duration_seconds = arguments.get("duration_minutes", 60) * 60

            data = {
                "title": arguments["title"],
                "time": datetime_str,
                "duration": duration_seconds,
                "description": arguments.get("description", ""),
            }

            result = await self._make_api_request("POST", "/events", data)
            return {
                "success": True,
                "event": result.get("data", {}),
                "message": f"Added event '{arguments['title']}' on {arguments['date']} at {arguments['time']}",
            }

        elif function_name == "delete_event":
            result = await self._make_api_request(
                "DELETE", f"/events/{arguments['event_id']}"
            )
            return {
                "success": result.get("status") == "ok",
                "message": f"Deleted event {arguments['event_id']}",
            }

        elif function_name == "analyze_schedule":
            # Implement schedule analysis
            date_range = arguments.get("date_range", "today")
            if date_range == "today":
                today_result = await self._execute_function("get_today_events", {})
                events = today_result.get("events", [])

                total_time = sum(e.get("duration", 0) // 60 for e in events)

                return {
                    "date_range": date_range,
                    "total_events": len(events),
                    "total_scheduled_minutes": total_time,
                    "analysis": f"You have {len(events)} events today totaling {total_time} minutes",
                }

        return {"error": f"Unknown function: {function_name}"}

    async def process_request(
        self, user_input: str
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Process a natural language request and execute calendar operations

        Returns:
            Tuple of (response_text, list_of_actions_taken)
        """
        current_date = date.today().strftime("%Y-%m-%d")
        messages = [
            {
                "role": "system",
                "content": self.system_prompt.format(current_date=current_date),
            },
            {"role": "user", "content": user_input},
        ]

        actions_taken = []

        if self.ai_provider == "openai":
            # OpenAI function calling
            response = await self.ai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
            )

            message = response.choices[0].message

            # Process any function calls
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)

                    # Execute the function
                    result = await self._execute_function(function_name, arguments)

                    actions_taken.append(
                        {
                            "function": function_name,
                            "arguments": arguments,
                            "result": result,
                        }
                    )

                    # Add function result to conversation
                    messages.append(message)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result),
                        }
                    )

                # Get final response from AI after executing functions
                final_response = await self.ai_client.chat.completions.create(
                    model=self.model, messages=messages
                )

                return final_response.choices[0].message.content, actions_taken
            else:
                return message.content, actions_taken

        elif self.ai_provider == "anthropic":
            # For Anthropic, we need to handle tool use differently
            # This is a simplified version - you'd need to implement proper tool use
            response = await self.ai_client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": user_input}],
                system=self.system_prompt.format(current_date=current_date),
                max_tokens=1000,
            )

            # You would need to parse the response and extract function calls
            # This is a placeholder
            return response.content[0].text, actions_taken

    async def process_request_with_reasoning(self, user_input: str) -> Dict[str, Any]:
        """
        Process request and return detailed information about what happened
        """
        print(f"\n🤔 Processing: '{user_input}'")
        print("-" * 50)

        response_text, actions = await self.process_request(user_input)

        # Print actions taken
        if actions:
            print("\n📋 Actions taken:")
            for i, action in enumerate(actions, 1):
                print(
                    f"\n{i}. {action['function']}({json.dumps(action['arguments'], indent=2)})"
                )
                if "error" not in action["result"]:
                    print(f"   ✅ Result: {json.dumps(action['result'], indent=2)}")
                else:
                    print(f"   ❌ Error: {action['result']['error']}")

        print(f"\n💬 Response: {response_text}")
        print("-" * 50)

        return {
            "user_input": user_input,
            "response": response_text,
            "actions": actions,
            "success": all("error" not in a["result"] for a in actions),
        }


# Example usage
async def main():
    # Initialize the agent (make sure to set your API key)
    agent = AICalendarAgent(
        api_base_url="http://localhost:8080",
        ai_provider="openai",  # or "anthropic"
        api_key="your-api-key-here",  # or set OPENAI_API_KEY env variable
    )

    # Example natural language requests
    examples = [
        "What's on my schedule today?",
        "Move all of today's meetings to tomorrow",
        "Clear my afternoon schedule",
        "Add a team meeting tomorrow at 2 PM for 1 hour",
        "Delete all events with 'review' in the title",
        "Find me a 2-hour slot this week for deep work",
        "Reschedule my 10 AM meeting to 3 PM",
        "What's my busiest day this week?",
        "Block out lunch time every day this week from 12 to 1",
    ]

    # Process a request
    result = await agent.process_request_with_reasoning(
        "I'm feeling overwhelmed. Clear my entire schedule for today and just add a 2-hour break at 2 PM"
    )

    # Or process multiple requests
    # for example in examples[:3]:
    #     result = await agent.process_request_with_reasoning(example)
    #     await asyncio.sleep(1)  # Rate limiting


# Simple interface function
async def calendar_ai(command: str, api_key: str = None):
    """Simple function to execute calendar commands using AI"""
    agent = AICalendarAgent(api_key=api_key)
    response, actions = await agent.process_request(command)
    return response


if __name__ == "__main__":
    # Make sure your C++ server is running on port 8080
    asyncio.run(main())

    # Or use the simple interface:
    # asyncio.run(calendar_ai("Move all today's meetings to next Monday"))
