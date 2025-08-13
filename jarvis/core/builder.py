# jarvis/app/builder.py

from __future__ import annotations
import os
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
    with_orchestrator: bool = True
    with_calendar: bool = True
    with_chat: bool = True
    with_weather: bool = True
    with_protocols: bool = True
    with_lights: bool = True
    with_software: bool = False  # was commented out in your code
    with_night_agents: bool = True


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

    def orchestrator(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_orchestrator = enabled
        return self

    def calendar(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_calendar = enabled
        return self

    def chat(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_chat = enabled
        return self

    def weather(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_weather = enabled
        return self

    def lights(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_lights = enabled
        return self

    def software_agent(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_software = enabled
        return self

    def night_agents(self, enabled: bool = True) -> "JarvisBuilder":
        self._opts.with_night_agents = enabled
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
        repo_path: str = ".",
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

        cfg = JarvisConfig(
            ai_provider=ai_provider,
            api_key=api_key,
            calendar_api_url=calendar_api_url,
            response_timeout=response_timeout,
            repo_path=repo_path,
            intent_timeout=intent_timeout,
            hue_bridge_ip=hue_bridge_ip,
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

        # Create shared client + connect usage logger
        ai_client = jarvis._create_ai_client()
        await jarvis._connect_usage_logger()

        factory = AgentFactory(jarvis.config, jarvis.logger)
        refs = {}
        if self._opts.with_memory:
            refs.update(factory._build_memory(jarvis.network, ai_client))
        if self._opts.with_nlu:
            refs.update(factory._build_nlu(jarvis.network, ai_client))
        if self._opts.with_orchestrator:
            refs.update(factory._build_orchestrator(jarvis.network, ai_client))
        if self._opts.with_calendar:
            refs.update(factory._build_calendar(jarvis.network, ai_client))
        if self._opts.with_chat:
            refs.update(factory._build_chat(jarvis.network, ai_client))
        if self._opts.with_weather and jarvis.config.flags.enable_weather:
            refs.update(factory._build_weather(jarvis.network, ai_client))
        if self._opts.with_protocols:
            refs.update(factory._build_protocol(jarvis.network))
        if self._opts.with_lights and jarvis.config.flags.enable_lights:
            refs.update(factory._build_lights(jarvis.network, ai_client))
        if self._opts.with_software:
            # Placeholder for future implementation
            pass
        if self._opts.with_night_agents and jarvis.config.flags.enable_night_mode:
            refs.update(factory._build_night_agents(jarvis.network, jarvis))

        jarvis.vector_memory = refs.get("vector_memory")
        jarvis.nlu_agent = refs.get("nlu_agent")
        jarvis.orchestrator = refs.get("orchestrator")
        jarvis.calendar_service = refs.get("calendar_service")
        jarvis.chat_agent = refs.get("chat_agent")
        jarvis.protocol_agent = refs.get("protocol_agent")
        jarvis.lights_agent = refs.get("lights_agent")
        jarvis.canvas_service = refs.get("canvas_service")
        jarvis.night_controller = refs.get("night_controller")
        jarvis.night_agents = refs.get("night_agents", [])

        # Protocol runtime (matcher/executor) + optional file loading
        jarvis._setup_protocol_system(
            load_protocol_directory=self._opts.load_protocol_directory
        )

        # Start network
        await jarvis._start_network()

        jarvis.logger.log(
            "INFO",
            "Jarvis built via JarvisBuilder",
            f"Active agents: {list(jarvis.network.agents.keys())}, "
            f"Protocols loaded: {len(jarvis.protocol_registry.protocols)}",
        )
        return jarvis
