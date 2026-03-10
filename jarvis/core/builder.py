# jarvis/app/builder.py

from __future__ import annotations
import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from .config import JarvisConfig
from .system import JarvisSystem
from ..agents.factory import AgentFactory


@dataclass
class BuilderOptions:
    load_protocol_directory: bool = True
    with_memory: bool = True
    with_nlu: bool = True
    with_calendar: bool = True
    with_chat: bool = True
    with_search: bool = True
    with_protocols: bool = True
    with_weather: bool = True
    with_lights: bool = True
    with_roku: bool = True
    with_software: bool = False  # was commented out in your code
    with_health: bool = True
    with_canvas: bool = True
    with_todo: bool = True
    with_night_agents: bool = True
    with_self_improvement: bool = True


class JarvisBuilder:
    """
    Minimal-intrusion builder that wires up JarvisSystem using its existing
    private factory helpers. No broad refactor required.
    """

    def __init__(self, config: JarvisConfig | Dict[str, Any]):
        # Accept dict for convenience, just like JarvisSystem
        self._config = JarvisConfig(**config) if isinstance(config, dict) else config
        self._opts = BuilderOptions()
        self._dotenv_loaded = False

    # ------- Fluent toggles --------
    def protocols(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_protocols = enabled
        return self

    def protocol_directory(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.load_protocol_directory = enabled
        return self

    def memory(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_memory = enabled
        return self

    def nlu(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_nlu = enabled
        return self

    def calendar(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_calendar = enabled
        return self

    def chat(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_chat = enabled
        return self

    def search(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_search = enabled
        return self

    def weather(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_weather = enabled
        return self

    def lights(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_lights = enabled
        return self

    def roku(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_roku = enabled
        return self


    def health(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_health = enabled
        return self

    def canvas(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_canvas = enabled
        return self

    def todo(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_todo = enabled
        return self

    def software_agent(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_software = enabled
        return self

    def night_agents(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_night_agents = enabled
        return self

    def self_improvement(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_self_improvement = enabled
        return self

    # ------- Convenience creators --------
    @staticmethod
    def from_env(
        *,
        ai_provider: str = "openai",
        api_key_env: str = "OPENAI_API_KEY",
        calendar_api_url: str = "http://localhost:8080",
        response_timeout: float = 60.0,
        intent_timeout: float = 5.0,
        hue_bridge_ip_env: Optional[str] = "PHILLIPS_HUE_BRIDGE_IP",
    ) -> "JarvisBuilder":
        load_dotenv()
        api_key = os.getenv(api_key_env)
        hue_bridge_ip = os.getenv(hue_bridge_ip_env)
        if not api_key:
            raise ValueError(f"Missing API key. Set {api_key_env} in your environment.")
        if not hue_bridge_ip:
            logging.getLogger("jarvis").info(
                "%s not set; Philips Hue integration disabled", hue_bridge_ip_env
            )

        lighting_backend = os.getenv("LIGHTING_BACKEND", "phillips_hue")
        yeelight_bulb_ips_str = os.getenv("YEELIGHT_BULB_IPS", "")
        yeelight_bulb_ips = (
            [ip.strip() for ip in yeelight_bulb_ips_str.split(",")]
            if yeelight_bulb_ips_str.strip()
            else None
        )
        hue_username = os.getenv("PHILLIPS_HUE_USERNAME")

        # Roku configuration
        roku_ip_address = os.getenv("ROKU_IP_ADDRESS")
        roku_username = os.getenv("ROKU_USERNAME")
        roku_password = os.getenv("ROKU_PASSWORD")

        cfg = JarvisConfig(
            ai_provider=ai_provider,
            api_key=api_key,
            calendar_api_url=calendar_api_url,
            response_timeout=response_timeout,
            intent_timeout=intent_timeout,
            hue_bridge_ip=hue_bridge_ip,
            hue_username=hue_username,
            lighting_backend=lighting_backend,
            yeelight_bulb_ips=yeelight_bulb_ips,
            roku_ip_address=roku_ip_address,
            roku_username=roku_username,
            roku_password=roku_password,
        )
        b = JarvisBuilder(cfg)
        b._dotenv_loaded = True
        return b

    # ------- Build (async) --------
    async def build(self) -> JarvisSystem:
        """
        Assemble a JarvisSystem with only the selected components.
        Uses existing private helpers to avoid a larger refactor.
        """
        if not self._dotenv_loaded:
            # Keep behavior consistent with your current code paths
            load_dotenv()

        jarvis = JarvisSystem(self._config)

        # Create shared client + connect MongoDB loggers
        ai_client = jarvis._create_ai_client()
        await jarvis._connect_mongo_loggers()

        factory = AgentFactory(jarvis.config, jarvis.logger)
        refs = {}
        if self._opts.with_memory:
            refs.update(factory._build_memory(jarvis.network, ai_client))
        if self._opts.with_nlu:
            refs.update(factory._build_nlu(jarvis.network, ai_client))
        if self._opts.with_calendar:
            refs.update(factory._build_calendar(jarvis.network, ai_client))
        if self._opts.with_chat:
            refs.update(factory._build_chat(jarvis.network, ai_client))
        if self._opts.with_search:
            refs.update(factory._build_search(jarvis.network, ai_client))
        if self._opts.with_protocols:
            refs.update(factory._build_protocol(jarvis.network))
        if self._opts.with_lights and jarvis.config.flags.enable_lights:
            refs.update(factory._build_lights(jarvis.network, ai_client))
        if self._opts.with_roku and jarvis.config.flags.enable_roku:
            refs.update(factory._build_roku(jarvis.network, ai_client))
        if self._opts.with_health and jarvis.config.flags.enable_health:
            refs.update(factory._build_health(jarvis.network))
        if self._opts.with_canvas and jarvis.config.flags.enable_canvas:
            refs.update(factory._build_canvas(jarvis.network, ai_client))
        if self._opts.with_todo and jarvis.config.flags.enable_todo:
            refs.update(factory._build_todo(jarvis.network, ai_client))

        if self._opts.with_software:
            # Placeholder for future implementation
            pass
        if self._opts.with_night_agents and jarvis.config.flags.enable_night_mode:
            refs.update(factory._build_night_agents(jarvis.network, jarvis))

        if (
            self._opts.with_self_improvement
            and jarvis.config.flags.enable_self_improvement
        ):
            si_refs = factory._build_self_improvement(
                jarvis.network, jarvis, refs.get("todo_service")
            )
            refs.update(si_refs)
            night_agents = refs.get("night_agents", [])
            night_agents.append(si_refs["self_improvement_agent"])
            refs["night_agents"] = night_agents

        # Store agent refs internally (properties provide backward-compatible access)
        jarvis._agent_refs = refs
        jarvis.night_controller = refs.get("night_controller")
        jarvis.night_agents = refs.get("night_agents", [])

        # Protocol runtime (matcher/executor) + optional file loading
        jarvis._setup_protocol_system(
            load_protocol_directory=self._opts.load_protocol_directory
        )

        # Start network
        await jarvis._start_network()
        
        # Initialize feedback collector
        from .feedback import FeedbackCollector
        from .response_logger import ResponseLogger
        from .orchestrator import RequestOrchestrator

        feedback_collector = None
        if jarvis.config.flags.enable_feedback:
            feedback_collector = FeedbackCollector(
                feedback_dir=jarvis.config.feedback_dir,
            )
            chat_agent = jarvis.network.agents.get("ChatAgent")
            if chat_agent and hasattr(chat_agent, "feedback_collector"):
                chat_agent.feedback_collector = feedback_collector

        # Initialize orchestrator and response logger
        jarvis._response_logger = ResponseLogger(jarvis.interaction_logger)
        jarvis._orchestrator = RequestOrchestrator(
            network=jarvis.network,
            protocol_runtime=jarvis.protocol_runtime,
            response_logger=jarvis._response_logger,
            logger=jarvis.logger,
            response_timeout=jarvis.config.response_timeout,
            max_history_length=10,
            ai_client=ai_client,
            enable_coordinator=jarvis.config.flags.enable_coordinator,
            feedback_collector=feedback_collector,
        )

        protocol_count = (
            len(jarvis.protocol_runtime.registry.protocols)
            if jarvis.protocol_runtime
            else 0
        )
        jarvis.logger.log(
            "INFO",
            "Jarvis built via JarvisBuilder",
            f"Active agents: {list(jarvis.network.agents.keys())}, "
            f"Protocols loaded: {protocol_count}",
        )
        return jarvis
