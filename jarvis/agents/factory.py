from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from ..config import JarvisConfig
from ..logger import JarvisLogger
from ..ai_clients import BaseAIClient
from ..agents.agent_network import AgentNetwork
from ..agents.nlu_agent import NLUAgent
from ..agents.protocol_agent import ProtocolAgent
from ..agents.lights_agent import PhillipsHueAgent
from ..agents.calendar_agent.agent import CollaborativeCalendarAgent
from ..agents.orchestrator_agent import OrchestratorAgent
from ..agents.weather_agent import WeatherAgent
from ..agents.memory_agent import MemoryAgent
from ..agents.chat_agent import ChatAgent
from ..agents.canvas import CanvasAgent
from ..services.vector_memory import VectorMemoryService
from ..services.calendar_service import CalendarService
from ..services.canvas_service import CanvasService
from ..night_agents import NightAgent, TriggerPhraseSuggesterAgent, NightModeControllerAgent

if TYPE_CHECKING:
    from ..main_jarvis import JarvisSystem


class AgentFactory:
    """Builds and wires agents/services based on configuration."""

    def __init__(self, config: JarvisConfig, logger: JarvisLogger):
        self.config = config
        self.logger = logger

    def build_all(
        self,
        network: AgentNetwork,
        ai_client: BaseAIClient,
        system: Optional["JarvisSystem"] = None,
    ) -> Dict[str, Any]:
        """Create all agents/services and register them with the network."""
        refs: Dict[str, Any] = {}
        refs.update(self._build_memory(network, ai_client))
        refs.update(self._build_nlu(network, ai_client))
        refs.update(self._build_orchestrator(network, ai_client))
        refs.update(self._build_calendar(network, ai_client))
        refs.update(self._build_chat(network, ai_client))

        if self.config.flags.enable_weather:
            refs.update(self._build_weather(network, ai_client))
        if self.config.flags.enable_canvas:
            refs.update(self._build_canvas(network, ai_client))

        refs.update(self._build_protocol(network))

        if self.config.flags.enable_lights:
            refs.update(self._build_lights(network, ai_client))

        if self.config.flags.enable_night_mode and system is not None:
            refs.update(self._build_night_agents(network, system))

        return refs

    # ----- individual builders -----
    def _build_memory(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        vector_memory = VectorMemoryService(
            persist_directory=self.config.memory_dir, api_key=self.config.api_key
        )
        memory_agent = MemoryAgent(vector_memory, self.logger, ai_client)
        network.register_agent(memory_agent)
        return {"vector_memory": vector_memory, "memory_agent": memory_agent}

    def _build_nlu(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        nlu_agent = NLUAgent(ai_client, self.logger)
        network.register_agent(nlu_agent)
        return {"nlu_agent": nlu_agent}

    def _build_orchestrator(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        orchestrator = OrchestratorAgent(
            ai_client, self.logger, response_timeout=self.config.response_timeout
        )
        network.register_agent(orchestrator)
        return {"orchestrator": orchestrator}

    def _build_calendar(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        calendar_service = CalendarService(self.config.calendar_api_url)
        calendar_agent = CollaborativeCalendarAgent(
            ai_client, calendar_service, self.logger
        )
        network.register_agent(calendar_agent)
        return {"calendar_service": calendar_service}

    def _build_chat(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        chat_agent = ChatAgent(ai_client, self.logger)
        network.register_agent(chat_agent)
        return {"chat_agent": chat_agent}

    def _build_weather(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        try:
            weather_agent = WeatherAgent(
                api_key=self.config.weather_api_key,
                logger=self.logger,
                ai_client=ai_client,
            )
            network.register_agent(weather_agent)
            return {"weather_agent": weather_agent}
        except Exception as exc:
            self.logger.log("WARNING", "WeatherAgent init failed", str(exc))
            return {}

    def _build_protocol(self, network: AgentNetwork) -> Dict[str, Any]:
        protocol_agent = ProtocolAgent(self.logger)
        network.register_agent(protocol_agent)
        return {"protocol_agent": protocol_agent}

    def _build_lights(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        if not self.config.hue_bridge_ip:
            self.logger.log(
                "INFO", "Skipping lights agent", "No Hue bridge IP configured"
            )
            return {}
        lights_agent = PhillipsHueAgent(
            ai_client=ai_client,
            bridge_ip=self.config.hue_bridge_ip,
            username=self.config.hue_username,
        )
        network.register_agent(lights_agent)
        return {"lights_agent": lights_agent}

    def _build_canvas(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        canvas_service = CanvasService(logger=self.logger)
        canvas_agent = CanvasAgent(ai_client, canvas_service, self.logger)
        network.register_agent(canvas_agent)
        return {
            "canvas_service": canvas_service,
            "canvas_agent": canvas_agent,
        }

    def _build_night_agents(
        self, network: AgentNetwork, system: "JarvisSystem"
    ) -> Dict[str, Any]:
        night_agents: list[NightAgent] = []
        controller = NightModeControllerAgent(system, self.logger)
        network.register_agent(controller)

        trigger_agent = TriggerPhraseSuggesterAgent(logger=self.logger)
        network.register_night_agent(trigger_agent)
        night_agents.append(trigger_agent)

        return {
            "night_controller": controller,
            "night_agents": night_agents,
        }
