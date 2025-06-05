from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from .agent import AICalendarAgent
from .ai_clients import BaseAIClient
from .logger import JarvisLogger


class AIMainAgent:
    """Main Jarvis agent that delegates to specialized agents as tools."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        agents: Dict[str, AICalendarAgent],
        logger: JarvisLogger | None = None,
    ) -> None:
        self.ai_client = ai_client
        self.agents = agents
        self.logger = logger or JarvisLogger()

        self.tools: List[Dict[str, Any]] = []
        self._function_map: Dict[str, AICalendarAgent] = {}
        for name, agent in agents.items():
            func_name = f"{name}_command"
            self.tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": func_name,
                        "description": f"Delegate the command to the {name} agent",
                        "parameters": {
                            "type": "object",
                            "properties": {"command": {"type": "string"}},
                            "required": ["command"],
                        },
                    },
                }
            )
            self._function_map[func_name] = agent

        self.system_prompt = (
            "You are Jarvis, the main assistant. "
            "You can delegate specific tasks to specialized agents using the provided tools."
        )

    async def _execute_function(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        agent = self._function_map.get(function_name)
        if not agent:
            return {"error": f"Unknown function: {function_name}"}
        try:
            command = arguments.get("command", "")
            self.logger.log("INFO", f"Delegating to {function_name}", command)
            response, _ = await agent.process_request(command)
            return {"response": response}
        except Exception as exc:
            self.logger.log("ERROR", f"Error in {function_name}", str(exc))
            return {"error": str(exc)}

    async def process_request(self, user_input: str) -> Tuple[str, List[Dict[str, Any]]]:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]
        actions_taken: List[Dict[str, Any]] = []

        iterations = 0
        MAX_ITERATIONS = 5
        tool_calls = None
        while iterations < MAX_ITERATIONS:
            message, tool_calls = await self.ai_client.chat(messages, self.tools)
            if not tool_calls:
                break
            messages.append(message.model_dump())
            for call in tool_calls:
                function_name = call.function.name
                arguments = json.loads(call.function.arguments)
                result = await self._execute_function(function_name, arguments)
                actions_taken.append({"function": function_name, "arguments": arguments, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
            iterations += 1

        if tool_calls:
            message, _ = await self.ai_client.chat(messages, [])

        return message.content if hasattr(message, "content") else str(message), actions_taken
