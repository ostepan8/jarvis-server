# jarvis/agents/roku_agent/agent.py
"""
Roku Agent - Controls Roku TV devices via External Control Protocol (ECP)

Supports multi-device routing through the RokuDeviceRegistry.
Each device gets a lazily-initialised RokuService keyed by serial number.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
import asyncio
import functools

from ..base import NetworkAgent
from ..message import Message
from ...logging import JarvisLogger
from ...ai_clients.base import BaseAIClient
from ...services.roku_service import RokuService
from ...services.roku_discovery import RokuDeviceRegistry, RokuDeviceInfo
from .function_registry import RokuFunctionRegistry
from .command_processor import RokuCommandProcessor
from ..response import AgentResponse, ErrorInfo


class RokuAgent(NetworkAgent):
    """
    Conversational Roku control agent that uses LLM to translate natural language
    commands into Roku device control actions via the External Control Protocol.

    Supports multiple Roku devices on the network, routed through a device registry.
    """

    def __init__(
        self,
        ai_client: BaseAIClient,
        device_registry: RokuDeviceRegistry,
        username: Optional[str] = None,
        password: Optional[str] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        """
        Initialize the Roku agent.

        Args:
            ai_client: AI client for natural language processing
            device_registry: Registry tracking all known Roku devices
            username: Optional username for authentication
            password: Optional password for authentication
            logger: Optional logger instance
        """
        super().__init__("RokuAgent", logger)
        self.ai_client = ai_client
        self.device_registry = device_registry
        self.username = username
        self.password = password

        # Lazy-init service cache keyed by serial number
        self._services: Dict[str, RokuService] = {}

        # Bootstrap a service for the default/first device so backwards compat works
        default_dev = self.device_registry.resolve_device()
        if default_dev:
            self._ensure_service(default_dev.serial_number, default_dev.ip_address)

        # Initialize components — registry now flows through the agent
        self.function_registry = RokuFunctionRegistry(self)
        self.command_processor = RokuCommandProcessor(
            ai_client=ai_client,
            function_registry=self.function_registry,
            logger=logger,
            device_registry=device_registry,
        )

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def _ensure_service(self, serial: str, ip: str) -> RokuService:
        """Get or create a RokuService for the given device.

        If the device's IP has changed (stale entry), the old service is
        replaced with a fresh one pointing at the new IP.
        """
        existing = self._services.get(serial)
        if existing is not None:
            if existing.device_ip == ip:
                return existing
            # IP changed — close the stale service and recreate
            asyncio.ensure_future(existing.close())

        service = RokuService(
            device_ip=ip,
            username=self.username,
            password=self.password,
        )
        self._services[serial] = service
        return service

    def get_service(self, serial: Optional[str] = None) -> Optional[RokuService]:
        """Return the RokuService for a device.

        If *serial* is provided, ensure and return that device's service.
        Otherwise, resolve the default device via the registry.
        """
        if serial:
            dev = self.device_registry.get_device_by_serial(serial)
            if dev:
                return self._ensure_service(dev.serial_number, dev.ip_address)
            return None

        default_dev = self.device_registry.resolve_device()
        if default_dev:
            return self._ensure_service(default_dev.serial_number, default_dev.ip_address)
        return None

    @property
    def roku_service(self) -> Optional[RokuService]:
        """Backwards-compat property — returns the service for the default/first online device."""
        return self.get_service()

    # ------------------------------------------------------------------
    # Multi-device execution
    # ------------------------------------------------------------------

    async def execute_on_device(
        self, serial: str, func_name: str, **kwargs: Any
    ) -> Dict[str, Any]:
        """Execute a named service method on a specific device.

        If *serial* is empty, the default device is used.
        On connection error: marks the device offline, triggers re-discovery,
        and retries once with the (potentially updated) IP.
        """
        # Resolve to default when serial is empty
        if not serial:
            dev = self.device_registry.resolve_device()
            if not dev:
                return {"success": False, "error": "No Roku devices available"}
            serial = dev.serial_number

        dev = self.device_registry.get_device_by_serial(serial)
        if not dev:
            return {"success": False, "error": f"Unknown device: {serial}"}

        service = self._ensure_service(dev.serial_number, dev.ip_address)
        method = getattr(service, func_name, None)
        if method is None:
            return {"success": False, "error": f"Unknown method: {func_name}"}

        try:
            result = await method(**kwargs)
            self.device_registry.mark_last_used(serial)
            return result
        except (ConnectionError, OSError, Exception) as exc:
            # First failure — mark offline, try rediscovery, retry once
            if self.logger:
                self.logger.log(
                    "WARN",
                    f"Connection to {dev.friendly_name or dev.device_name or serial} failed: {exc}",
                )
            self.device_registry.mark_offline(serial)

            try:
                await self.device_registry.discover(timeout=3.0)
            except Exception:
                pass

            # Re-resolve — the IP may have changed
            dev = self.device_registry.get_device_by_serial(serial)
            if not dev or not dev.is_online:
                return {
                    "success": False,
                    "error": f"Device {serial} is offline after rediscovery",
                }

            service = self._ensure_service(dev.serial_number, dev.ip_address)
            method = getattr(service, func_name, None)
            if method is None:
                return {"success": False, "error": f"Unknown method: {func_name}"}

            try:
                result = await method(**kwargs)
                self.device_registry.mark_last_used(serial)
                return result
            except Exception as retry_exc:
                return {"success": False, "error": str(retry_exc)}

    async def execute_on_all(
        self, func_name: str, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Execute a named method on ALL online devices concurrently."""
        online = self.device_registry.get_online_devices()
        if not online:
            return [{"success": False, "error": "No online devices"}]

        tasks = [
            self.execute_on_device(dev.serial_number, func_name, **kwargs)
            for dev in online
        ]
        return list(await asyncio.gather(*tasks))

    async def discover_devices(self) -> List[RokuDeviceInfo]:
        """Trigger an SSDP scan and create services for newly found devices."""
        newly = await self.device_registry.discover()
        for dev in newly:
            self._ensure_service(dev.serial_number, dev.ip_address)
        return newly

    # ------------------------------------------------------------------
    # Original agent interface
    # ------------------------------------------------------------------

    async def _process_roku_command(self, command: str) -> Dict[str, Any]:
        """Process a natural language Roku command."""
        return await self.command_processor.process_command(command)

    async def close(self) -> None:
        """Clean up ALL service connections."""
        for service in self._services.values():
            try:
                await service.close()
            except Exception:
                pass
        self._services.clear()

    @property
    def description(self) -> str:
        return "Conversational Roku TV control agent with multi-device support"

    @property
    def capabilities(self) -> Set[str]:
        return self.function_registry.capabilities

    async def run_capability(self, capability: str, **kwargs: Any) -> Any:
        """Execute a Roku capability via the function registry."""
        func = self.function_registry.get_function(capability.replace("roku_", ""))
        if not func:
            raise NotImplementedError(
                f"Capability '{capability}' not implemented in RokuAgent"
            )

        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(func, **kwargs))

    async def _handle_capability_request(self, message: Message) -> None:
        """Handle incoming capability requests."""
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability not in self.capabilities:
            return

        if self.logger:
            self.logger.log("INFO", f"RokuAgent handling: {capability}")

        try:
            command = data.get("prompt", data.get("message", ""))
            if not command:
                await self.send_error(
                    message.from_agent,
                    "No Roku command provided",
                    message.request_id,
                )
                return

            # Extract context and enhance prompt with previous results from DAG
            context_info = self._extract_context_from_message(message)
            previous_results = context_info.get("previous_results", [])

            if previous_results:
                command = self._enhance_prompt_with_context(command, previous_results)
                if self.logger:
                    self.logger.log(
                        "INFO",
                        "Enhanced Roku command with previous results",
                        f"Previous steps: {len(previous_results)}",
                    )

            result = await self._process_roku_command(command)

            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

        except Exception as e:
            if self.logger:
                self.logger.log("ERROR", f"RokuAgent error: {e}")

            # Return standardized error response
            error_response = AgentResponse.error_response(
                response=f"I'm having trouble controlling the Roku device. {str(e)} Could you try again?",
                error=ErrorInfo.from_exception(e),
            ).to_dict()

            await self.send_capability_response(
                message.from_agent, error_response, message.request_id, message.id
            )

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle responses from other agents."""
        if self.logger:
            self.logger.log("DEBUG", f"RokuAgent received response: {message.content}")
