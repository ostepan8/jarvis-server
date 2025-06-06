# jarvis/agents/ui_agent.py
import asyncio
import json
from typing import Any, Dict, Set, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from tzlocal import get_localzone_name
import uuid

from .base import NetworkAgent
from .message import Message
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger


class UIAgent(NetworkAgent):
    """Agent that handles user interaction and coordinates complex requests"""

    def __init__(
        self,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
        response_timeout: float = 10.0,
    ):
        super().__init__("UIAgent", logger)
        self.ai_client = ai_client
        self.response_timeout = response_timeout
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.conversation_history: List[Dict[str, Any]] = []

        # Register additional handlers
        self.message_handlers["user_input"] = self._handle_user_input

    async def _handle_user_input(self, message: Message) -> None:
        """Process a user input message from the network."""
        # Message content may be a raw string or a dict with an "input" key
        user_input = message.content
        if isinstance(user_input, dict):
            user_input = user_input.get("input", "")

        if not isinstance(user_input, str):
            self.logger.log("ERROR", "Invalid user input", str(user_input))
            return

        tz_name = get_localzone_name()
        if isinstance(message.content, dict):
            tz_name = message.content.get("timezone", tz_name)
        result = await self.process_user_request(user_input, tz_name)

        # Send the formatted response back to the sender
        await self.send_message(
            message.from_agent,
            "user_response",
            result,
            message.request_id,
            reply_to=message.id,
        )

    @property
    def description(self) -> str:
        return "Handles user interaction, request parsing, and response coordination"

    @property
    def capabilities(self) -> Set[str]:
        return {
            "parse_request",
            "coordinate_response",
            "user_confirmation",
            "format_response",
        }

    @property
    def dependencies(self) -> Set[str]:
        return {
            "view_schedule",
            "add_event",
            "remove_event",  # Calendar
            "send_email",
            "check_email",  # Email
            "web_search",
            "get_news",  # Research
            "control_device",
            "get_device_status",  # Smart home
        }

    async def process_user_request(self, user_input: str, tz_name: str) -> Dict[str, Any]:
        """Main entry point for processing user requests"""
        request_id = f"req_{uuid.uuid4()}"

        self.logger.log("INFO", f"Processing user request", user_input)

        # Store request
        self.pending_requests[request_id] = {
            "user_input": user_input,
            "start_time": datetime.now(ZoneInfo(tz_name)),
            "capability_requests": {},
            "responses": {},
            "status": "processing",
            "timezone": tz_name,
        }

        # Add to conversation history
        self.conversation_history.append(
            {
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now(ZoneInfo(tz_name)).isoformat(),
            }
        )

        try:
            # Parse request with AI
            analysis = await self._analyze_request(user_input, tz_name)

            # Execute capability requests in parallel
            await self._execute_capability_requests(request_id, analysis)

            # Wait for responses (with timeout)
            response = await self._wait_for_responses(
                request_id, timeout=self.response_timeout
            )

            # Format final response
            final_response = await self._format_response(request_id, response, tz_name)

            self.pending_requests[request_id]["status"] = "completed"

            return {
                "success": True,
                "response": final_response,
                "request_id": request_id,
                "agents_involved": list(
                    self.pending_requests[request_id]["responses"].keys()
                ),
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "response": "I'm sorry, the request timed out. Some agents may still be working on it.",
                "request_id": request_id,
            }
        except Exception as e:
            self.logger.log("ERROR", "Request processing error", str(e))
            return {
                "success": False,
                "response": f"I encountered an error: {str(e)}",
                "request_id": request_id,
            }

    async def _analyze_request(self, user_input: str, tz_name: str) -> Dict[str, Any]:
        """Use AI to analyze user request and determine needed capabilities"""

        # Create a system prompt that knows about available capabilities
        available_capabilities = []
        for cap, agents in self.network.capability_registry.items():
            available_capabilities.append(
                f"- {cap}: provided by {', '.join(agents)}"
            )

        current_date = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")
        system_prompt = f"""You are JARVIS, analyzing user requests to determine which capabilities are needed.

Current date: {current_date}

Available capabilities:
{chr(10).join(available_capabilities)}

Analyze the user's request and return a JSON object with:
- "intent": brief description of what the user wants
- "capabilities_needed": list of capability names needed
- "parameters": dict of parameters for each capability
- "coordination_notes": any special coordination needed between capabilities

Be thorough - include all capabilities that might be needed."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        # Get AI analysis
        response = await self.ai_client.chat(messages, [])

        # Parse response (assuming AI returns JSON)
        try:
            analysis = json.loads(response[0].content)
        except:
            # Fallback to simple keyword matching
            analysis = self._simple_request_analysis(user_input)

        return analysis

    async def _execute_capability_requests(
        self, request_id: str, analysis: Dict[str, Any]
    ) -> None:
        """Execute all needed capability requests"""

        capabilities_needed = analysis.get("capabilities_needed", [])
        parameters = analysis.get("parameters", {})

        for capability in capabilities_needed:
            # Get parameters for this capability
            cap_params = parameters.get(capability, {})

            # Request the capability
            cap_request_id = await self.request_capability(
                capability, cap_params, request_id
            )

            # Track it
            self.pending_requests[request_id]["capability_requests"][capability] = {
                "request_id": cap_request_id,
                "status": "requested",
                "parameters": cap_params,
            }

    async def _wait_for_responses(
        self, request_id: str, timeout: float
    ) -> Dict[str, Any]:
        """Wait for all capability responses"""
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check if all responses received
            pending = self.pending_requests[request_id]
            total_requested = len(pending["capability_requests"])
            total_received = len(pending["responses"])

            if total_received >= total_requested:
                break

            # Check timeout
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise asyncio.TimeoutError()

            await asyncio.sleep(0.1)

        return pending["responses"]

    async def _format_response(self, request_id: str, responses: Dict[str, Any], tz_name: str) -> str:
        """Use AI to format a natural response from all agent responses"""

        request_data = self.pending_requests[request_id]

        # Create context for AI
        context = {
            "user_request": request_data["user_input"],
            "agent_responses": responses,
            "timestamp": datetime.now(ZoneInfo(tz_name)).isoformat(),
        }

        system_prompt = """You are JARVIS, Tony Stark's AI assistant. 
Format the agent responses into a natural, conversational response.
Be concise but complete. Don't mention the internal agent names."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User asked: {request_data['user_input']}"},
            {
                "role": "assistant",
                "content": f"Here's what I found: {json.dumps(context)}",
            },
        ]

        response = await self.ai_client.chat(messages, [])
        return response[0].content

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle responses from other agents"""
        request_id = message.request_id

        if request_id not in self.pending_requests:
            return

        # Store the response
        self.pending_requests[request_id]["responses"][
            message.from_agent
        ] = message.content

        # Update status
        for cap, data in self.pending_requests[request_id][
            "capability_requests"
        ].items():
            if data["request_id"] == request_id:
                data["status"] = "completed"

    def _simple_request_analysis(self, user_input: str) -> Dict[str, Any]:
        """Fallback simple analysis based on keywords"""
        lower_input = user_input.lower()

        capabilities_needed = []
        parameters = {}

        # Calendar-related
        if any(
            word in lower_input
            for word in ["schedule", "calendar", "meeting", "appointment"]
        ):
            capabilities_needed.append("calendar_command")
            parameters["calendar_command"] = {"command": user_input}

        # Email-related
        if any(word in lower_input for word in ["email", "mail", "send"]):
            capabilities_needed.append("send_email")

        # Add more patterns as needed

        return {
            "intent": "Process user request",
            "capabilities_needed": capabilities_needed,
            "parameters": parameters,
        }
