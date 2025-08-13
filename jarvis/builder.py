# jarvis/app/builder.py

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from jarvis.config import JarvisConfig
from jarvis.main_jarvis import JarvisSystem


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
        repo_path: str = ".",
    ) -> "JarvisBuilder":
        load_dotenv()
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise ValueError(f"Missing API key. Set {api_key_env} in your environment.")

        cfg = JarvisConfig(
            ai_provider=ai_provider,
            api_key=api_key,
            calendar_api_url=calendar_api_url,
            response_timeout=response_timeout,
            repo_path=repo_path,
            intent_timeout=intent_timeout,
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

        # Selective agent/service creation
        if self._opts.with_memory:
            jarvis._create_memory_agent(ai_client)
        if self._opts.with_nlu:
            jarvis._create_nlu_agent(ai_client)
        if self._opts.with_orchestrator:
            jarvis._create_orchestrator(ai_client)
        if self._opts.with_calendar:
            jarvis._create_calendar_agent(ai_client)
        if self._opts.with_chat:
            jarvis._create_chat_agent(ai_client)
        if self._opts.with_weather:
            jarvis._create_weather_agent(ai_client)
        if self._opts.with_protocols:
            jarvis._create_protocol_agent()
        if self._opts.with_lights:
            jarvis._create_lights_agent(ai_client)
        if self._opts.with_software:
            jarvis._create_software_agent(ai_client)
        if self._opts.with_night_agents:
            jarvis._create_night_agents()

        # Protocol runtime (matcher/executor) + optional file loading
        jarvis._setup_protocol_system(self._opts.load_protocol_directory)

        # Start network
        await jarvis._start_network()

        jarvis.logger.log(
            "INFO",
            "Jarvis built via JarvisBuilder",
            f"Active agents: {list(jarvis.network.agents.keys())}, "
            f"Protocols loaded: {len(jarvis.protocol_registry.protocols)}",
        )
        return jarvis
