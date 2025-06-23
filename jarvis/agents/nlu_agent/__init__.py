# agents/nlu_agent.py

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger
from ...utils import extract_json_from_text


class NLUAgent(NetworkAgent):
    """Natural Language Understanding Agent for processing raw user input
    and delegating to the correct agent based on intent."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
        response_timeout: float = 10.0,
    ) -> None:
        super().__init__("NLUAgent", logger)
        self.ai_client = ai_client
        self.response_timeout = response_timeout

    @property
    def description(self) -> str:
        return (
            "Classifies user messages into intents and routes them to the "
            "appropriate agent using intent_matching."
        )

    @property
    def capabilities(self) -> Set[str]:
        # This agent provides a single "intent_matching" capability
        return {"intent_matching"}

    async def _handle_capability_response(self, message):
        self.logger.log("INFO", "NLUAgent received capability response", message)
        return

    async def _handle_capability_request(self, message: Message) -> None:
        if message.content.get("capability") != "intent_matching":
            return

        user_input = message.content["data"]["input"]
        self.logger.log("INFO", "NLU received input", user_input)

        known_capabilities = list(self.network.capability_registry.keys())

        classification = await self.classify(user_input, known_capabilities)

        # AUTO-ASSIGN TARGET AGENTS: For each capability, assign the first available provider
        if classification.get("intent") == "perform_capability":
            capability = classification.get("capability")
            if capability and capability in self.network.capability_registry:
                # Get the first provider for this capability
                providers = self.network.capability_registry[capability]
                if providers:
                    classification["target_agent"] = providers[0]
                    self.logger.log(
                        "INFO",
                        f"Auto-assigned capability '{capability}' to agent '{providers[0]}'",
                    )
                else:
                    self.logger.log(
                        "WARNING", f"No providers found for capability '{capability}'"
                    )
                    # Fallback to orchestrator
                    classification = {
                        "intent": "orchestrate_tasks",
                        "target_agent": "OrchestratorAgent",
                        "protocol_name": None,
                        "capability": None,
                        "args": {},
                    }

        classification["raw"] = user_input
        self.logger.log("INFO", "NLU classification result", classification)

        self.logger.log(
            "DEBUG",
            "NLUAgent sending response",
            {
                "to_agent": message.from_agent,
                "classification": classification,
                "request_id": message.request_id,
            },
        )
        await self.send_capability_response(
            to_agent=message.from_agent,
            result=classification,
            request_id=message.request_id,
            original_message_id=message.id,
        )

    async def classify(
        self,
        user_input: str,
        capabilities: List[str],
    ) -> Dict[str, Any]:
        """Invoke the LLM to classify the user_input into a routing JSON."""
        prompt = self.build_prompt(user_input, capabilities)
        self.logger.log("DEBUG", "NLU prompt built", prompt)

        response = await self.ai_client.weak_chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input},
            ],
            [],
        )
        content = response[0].content
        self.logger.log("INFO", "NLU raw model output", content)

        classification = extract_json_from_text(content)

        # Fallback: if the LLM fails, route to the orchestrator
        if classification is None:
            self.logger.log(
                "WARNING",
                "NLU failed to parse JSON, falling back to orchestrate_tasks",
                content,
            )
            classification = {
                "intent": "orchestrate_tasks",
                "target_agent": "OrchestratorAgent",
                "protocol_name": None,
                "capability": None,
                "args": {},
            }
            return classification

        # CHAT INTENT: Route to ChatAgent
        if classification.get("intent") == "chat":
            classification["target_agent"] = "ChatAgent"
            self.logger.log(
                "INFO",
                "Routing to ChatAgent for chat intent",
                classification,
            )
        if classification.get("intent") == "perform_capability":
            requested_capability = classification.get("capability")
            if requested_capability not in capabilities:
                self.logger.log(
                    "WARNING",
                    f"LLM requested non-existent capability '{requested_capability}', falling back to orchestrator",
                    f"Available capabilities: {capabilities}",
                )
                # Fallback to orchestrator for complex analysis
                classification = {
                    "intent": "orchestrate_tasks",
                    "target_agent": "OrchestratorAgent",
                    "protocol_name": None,
                    "capability": None,
                    "args": {},
                }

        return classification

    def build_prompt(
        self,
        user_input: str,
        capabilities: List[str],
    ) -> str:
        cap_list = ", ".join(capabilities) if capabilities else "none"

        prompt = f"""
You are JARVIS's Natural Language Understanding engine.  
Your job is to read the exact **User Input** below and return **only** a JSON object—no prose—conforming precisely to the schema.

**CRITICAL RULES:**
1. You can ONLY use capabilities that exist in the "Available Capabilities" list below
2. DO NOT invent or hallucinate capability names or intents
3. **INTENT vs CAPABILITY**: 
   - INTENT = what type of action ("perform_capability", "orchestrate_tasks", etc.)
   - CAPABILITY = specific skill from the list ("aider_software_agent_command", "schedule_appointment", etc.)
4. If the user's request matches ONE available capability, use intent "perform_capability" 
5. If no single capability matches OR multiple different agent types needed, use intent "orchestrate_tasks"
6. **SOFTWARE TASKS**: All coding/development work uses capability "aider_software_agent_command" with intent "perform_capability"
7. **MULTI-AGENT TASKS**: Use intent "orchestrate_tasks" only when you need multiple DIFFERENT types of agents (code + calendar, lights + code, etc.)
8. Even if the intent is "chat" you still must return a capability (if it exists in the list, otherwise just put "chat" as capability)

**User Input**  
\"\"\"{user_input}\"\"\"

**Available Capabilities:** {cap_list}

#### Analysis Process:
1. Is this a software/coding task? → intent: "perform_capability", capability: "aider_software_agent_command"
2. Does this match ONE other capability? → intent: "perform_capability", capability: "that_capability" 
3. Does this need multiple different agent types? → intent: "orchestrate_tasks", capability: null
4. Otherwise → intent: "chat"

#### JSON Schema (return ONLY this JSON, no other text):
```json
{{
"intent": "<perform_capability OR orchestrate_tasks OR run_protocol OR ask_about_protocol OR define_protocol OR chat>",
"target_agent": "",
"protocol_name": null,
"capability": "<exact capability name from list above OR null>",
"args": {{}}
}}
"""
        return prompt
