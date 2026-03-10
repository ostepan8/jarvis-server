from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..core import JarvisConfig
from ..logging import JarvisLogger
from ..ai_clients import BaseAIClient
from ..agents.agent_network import AgentNetwork
from ..agents.nlu_agent import NLUAgent
from ..agents.protocol_agent import ProtocolAgent
from ..agents.lights_agent.lighting_agent import create_lighting_agent
from ..agents.calendar_agent.agent import CollaborativeCalendarAgent
from ..agents.weather_agent import WeatherAgent
from ..agents.memory_agent import MemoryAgent
from ..agents.chat_agent import ChatAgent
from ..agents.search_agent import SearchAgent
from ..agents.canvas import CanvasAgent
from ..agents.roku_agent import RokuAgent
from ..agents.todo_agent import TodoAgent
from ..services.vector_memory import VectorMemoryService
from ..services.fact_memory import FactMemoryService
from ..services.calendar_service import CalendarService
from ..services.search_service import GoogleSearchService
from ..services.canvas_service import CanvasService
from ..services.todo_service import TodoService
from ..services.health_service import HealthService
from ..utils import get_location_from_ip
from ..night_agents import (
    NightAgent,
    NightModeControllerAgent,
    LogCleanupAgent,
    SelfImprovementAgent,
)

if TYPE_CHECKING:
    from ..core import JarvisSystem


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
        """Synchronous build — kept for backward compat / tests."""
        refs: Dict[str, Any] = {}
        refs.update(self._build_memory(network, ai_client))
        vector_memory = refs.get("vector_memory")
        refs.update(self._build_nlu(network, ai_client, vector_memory))
        refs.update(self._build_calendar(network, ai_client))
        refs.update(self._build_chat(network, ai_client))
        refs.update(self._build_search(network))

        if self.config.flags.enable_weather:
            refs.update(self._build_weather(network, ai_client))
        if self.config.flags.enable_canvas:
            refs.update(self._build_canvas(network, ai_client))

        refs.update(self._build_protocol(network))

        if self.config.flags.enable_lights:
            refs.update(self._build_lights(network, ai_client))

        if self.config.flags.enable_roku:
            refs.update(self._build_roku(network, ai_client))

        if self.config.flags.enable_todo:
            refs.update(self._build_todo(network, ai_client))

        if self.config.flags.enable_health:
            refs.update(self._build_health(network))

        if self.config.flags.enable_night_mode and system is not None:
            refs.update(self._build_night_agents(network, system))

        if self.config.flags.enable_self_improvement and system is not None:
            si_refs = self._build_self_improvement(
                network, system, refs.get("todo_service")
            )
            refs.update(si_refs)
            night_agents = refs.get("night_agents", [])
            night_agents.append(si_refs["self_improvement_agent"])
            refs["night_agents"] = night_agents

        return refs

    async def build_all_async(
        self,
        network: AgentNetwork,
        ai_client: BaseAIClient,
        system: Optional["JarvisSystem"] = None,
    ) -> Dict[str, Any]:
        """Create all agents with heavy I/O running in parallel.

        ChromaDB init and weather geolocation are offloaded to threads
        while instant agents are built immediately on the main thread.
        """
        refs: Dict[str, Any] = {}

        # --- Kick off slow I/O in background threads ---
        chromadb_future = asyncio.to_thread(
            VectorMemoryService,
            persist_directory=self.config.memory_dir,
            api_key=self.config.api_key,
        )

        location_future = None
        if self.config.flags.enable_weather:
            location_future = asyncio.to_thread(get_location_from_ip)

        # --- Build all instant agents while I/O runs ---
        refs.update(self._build_calendar(network, ai_client))
        refs.update(self._build_chat(network, ai_client))
        refs.update(self._build_search(network))
        refs.update(self._build_protocol(network))

        if self.config.flags.enable_canvas:
            refs.update(self._build_canvas(network, ai_client))
        if self.config.flags.enable_lights:
            refs.update(self._build_lights(network, ai_client))
        if self.config.flags.enable_roku:
            refs.update(self._build_roku(network, ai_client))
        if self.config.flags.enable_todo:
            refs.update(self._build_todo(network, ai_client))
        if self.config.flags.enable_health:
            refs.update(self._build_health(network))
        if self.config.flags.enable_night_mode and system is not None:
            refs.update(self._build_night_agents(network, system))

        if self.config.flags.enable_self_improvement and system is not None:
            si_refs = self._build_self_improvement(
                network, system, refs.get("todo_service")
            )
            refs.update(si_refs)
            night_agents = refs.get("night_agents", [])
            night_agents.append(si_refs["self_improvement_agent"])
            refs["night_agents"] = night_agents

        # --- Await ChromaDB init, then build memory + NLU ---
        try:
            vector_memory = await chromadb_future
        except Exception as exc:
            self.logger.log("WARNING", "VectorMemoryService init failed", str(exc))
            vector_memory = None

        if vector_memory is not None:
            fact_service = FactMemoryService()
            memory_agent = MemoryAgent(
                vector_memory, fact_service, self.logger, ai_client
            )
            network.register_agent(memory_agent)
            refs.update({
                "vector_memory": vector_memory,
                "fact_service": fact_service,
                "memory_agent": memory_agent,
            })

        refs.update(self._build_nlu(network, ai_client, vector_memory))

        # --- Await geolocation, then build weather ---
        if location_future is not None:
            try:
                detected_location = await location_future
                if not detected_location:
                    detected_location = "Chicago"
                    self.logger.log(
                        "INFO",
                        "Could not detect location from IP",
                        f"Using default location '{detected_location}'",
                    )
                else:
                    self.logger.log(
                        "INFO",
                        "Detected location from IP address",
                        f"Using '{detected_location}' as default weather location",
                    )
                weather_agent = WeatherAgent(
                    api_key=self.config.weather_api_key,
                    logger=self.logger,
                    ai_client=ai_client,
                    default_location=detected_location,
                )
                network.register_agent(weather_agent)
                refs["weather_agent"] = weather_agent
            except Exception as exc:
                self.logger.log("WARNING", "WeatherAgent init failed", str(exc))

        return refs

    # ----- individual builders -----
    def _build_memory(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        vector_memory = VectorMemoryService(
            persist_directory=self.config.memory_dir, api_key=self.config.api_key
        )
        fact_service = FactMemoryService()
        memory_agent = MemoryAgent(vector_memory, fact_service, self.logger, ai_client)
        network.register_agent(memory_agent)
        return {
            "vector_memory": vector_memory,
            "fact_service": fact_service,
            "memory_agent": memory_agent,
        }

    def _build_nlu(
        self,
        network: AgentNetwork,
        ai_client: BaseAIClient,
        vector_memory: Optional[VectorMemoryService] = None,
    ) -> Dict[str, Any]:
        fast_classifier = None
        if self.config.use_fast_classifier and vector_memory:
            from ..agents.nlu_agent.fast_classifier import FastPathClassifier

            fast_classifier = FastPathClassifier(vector_memory, self.logger)

        nlu_agent = NLUAgent(
            ai_client,
            self.logger,
            fast_classifier=fast_classifier,
            cache_ttl=self.config.classification_cache_ttl,
            cache_max_size=self.config.classification_cache_max_size,
        )
        network.register_agent(nlu_agent)
        return {"nlu_agent": nlu_agent, "fast_classifier": fast_classifier}

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

    def _build_search(self, network: AgentNetwork) -> Dict[str, Any]:
        """Build and register SearchAgent if credentials are available."""
        if not self.config.google_search_api_key or not self.config.google_search_engine_id:
            self.logger.log(
                "INFO",
                "Skipping SearchAgent",
                "Google Search API credentials not configured",
            )
            return {}

        try:
            search_service = GoogleSearchService(
                api_key=self.config.google_search_api_key,
                search_engine_id=self.config.google_search_engine_id,
                logger=self.logger,
            )
            search_agent = SearchAgent(search_service, self.logger)
            network.register_agent(search_agent)
            return {"search_agent": search_agent, "search_service": search_service}
        except Exception as exc:
            self.logger.log("WARNING", "SearchAgent init failed", str(exc))
            return {}

    def _build_weather(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        try:
            # Automatically detect location from IP address
            detected_location = get_location_from_ip()
            if detected_location:
                self.logger.log(
                    "INFO",
                    "Detected location from IP address",
                    f"Using '{detected_location}' as default weather location",
                )
            else:
                detected_location = "Chicago"  # Fallback
                self.logger.log(
                    "INFO",
                    "Could not detect location from IP",
                    f"Using default location '{detected_location}'",
                )

            weather_agent = WeatherAgent(
                api_key=self.config.weather_api_key,
                logger=self.logger,
                ai_client=ai_client,
                default_location=detected_location,
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
        backend_type = self.config.lighting_backend.lower()
        backend_kwargs = {}
        if backend_type == "phillips_hue":
            if not self.config.hue_bridge_ip:
                self.logger.log(
                    "INFO", "Skipping lights agent", "No Hue bridge IP configured"
                )
                return {}
            backend_kwargs = {
                "bridge_ip": self.config.hue_bridge_ip,
                "username": self.config.hue_username,
            }
        elif backend_type == "yeelight":
            backend_kwargs = {
                "bulb_ips": self.config.yeelight_bulb_ips,
            }
        else:
            self.logger.log(
                "WARNING",
                "Unknown lighting backend",
                f"Using 'phillips_hue' as fallback. Got: {backend_type}",
            )
            if not self.config.hue_bridge_ip:
                return {}
            backend_type = "phillips_hue"
            backend_kwargs = {
                "bridge_ip": self.config.hue_bridge_ip,
                "username": self.config.hue_username,
            }

        try:
            lights_agent = create_lighting_agent(
                backend_type=backend_type,
                ai_client=ai_client,
                logger=self.logger,
                **backend_kwargs,
            )
            network.register_agent(lights_agent)
            network.agents["PhillipsHueAgent"] = lights_agent
            network.logger.log(
                "INFO",
                "Registered LightingAgent with alias",
                f"PhillipsHueAgent (backend: {backend_type})",
            )
            return {"lights_agent": lights_agent}
        except Exception as exc:
            self.logger.log(
                "ERROR", f"Failed to create {backend_type} lighting agent", str(exc)
            )
            return {}

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

    def _build_roku(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        if not self.config.roku_ip_address:
            self.logger.log(
                "INFO", "Skipping Roku agent", "No Roku IP address configured"
            )
            return {}

        try:
            roku_agent = RokuAgent(
                ai_client=ai_client,
                device_ip=self.config.roku_ip_address,
                username=self.config.roku_username,
                password=self.config.roku_password,
                logger=self.logger,
            )
            network.register_agent(roku_agent)
            return {"roku_agent": roku_agent}
        except Exception as exc:
            self.logger.log("WARNING", "RokuAgent init failed", str(exc))
            return {}

    def _build_todo(
        self, network: AgentNetwork, ai_client: BaseAIClient
    ) -> Dict[str, Any]:
        """Build and register TodoAgent with SQLite-backed TodoService."""
        try:
            todo_service = TodoService(logger=self.logger)
            todo_agent = TodoAgent(
                ai_client=ai_client,
                todo_service=todo_service,
                logger=self.logger,
            )
            network.register_agent(todo_agent)
            return {"todo_service": todo_service, "todo_agent": todo_agent}
        except Exception as exc:
            self.logger.log("WARNING", "TodoAgent init failed", str(exc))
            return {}

    def _build_health(self, network: AgentNetwork) -> Dict[str, Any]:
        """Build and register HealthAgent for system monitoring."""
        try:
            from ..agents.health_agent import HealthAgent

            health_service = HealthService(timeout=5.0)
            health_agent = HealthAgent(
                health_service=health_service,
                logger=self.logger,
                probe_interval=self.config.health_probe_interval,
                report_interval=self.config.health_report_interval,
                report_dir=self.config.health_report_dir,
            )
            network.register_agent(health_agent)
            return {"health_service": health_service, "health_agent": health_agent}
        except Exception as exc:
            self.logger.log("WARNING", "HealthAgent init failed", str(exc))
            return {}

    def _build_night_agents(
        self, network: AgentNetwork, system: "JarvisSystem"
    ) -> Dict[str, Any]:
        night_agents: list[NightAgent] = []
        controller = NightModeControllerAgent(system, self.logger)
        network.register_agent(controller)

        cleanup_agent = LogCleanupAgent(logger=self.logger)
        network.register_night_agent(cleanup_agent)
        night_agents.append(cleanup_agent)

        return {
            "night_controller": controller,
            "night_agents": night_agents,
        }

    def _build_self_improvement(
        self,
        network: AgentNetwork,
        system: "JarvisSystem",
        todo_service: Optional[TodoService] = None,
    ) -> Dict[str, Any]:
        from pathlib import Path

        project_root = str(Path(__file__).parent.parent.parent)
        agent = SelfImprovementAgent(
            project_root=project_root,
            todo_service=todo_service,
            logger=self.logger,
        )
        network.register_night_agent(agent)
        return {"self_improvement_agent": agent}
