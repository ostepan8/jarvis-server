"""ServerManagerService — process lifecycle, health checks, auto-restart."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.agents.health_agent.models import ProbeResult

from jarvis.agents.server_manager_agent.models import (
    RestartPolicy,
    ServerConfig,
    ServerMode,
    ServerState,
    ServerStatus,
)
from jarvis.logging import JarvisLogger


def _health_models():
    """Lazy import to break circular dependency."""
    from jarvis.agents.health_agent.models import ProbeResult, ComponentStatus
    return ProbeResult, ComponentStatus


DEFAULT_REGISTRY_PATH = str(Path.home() / ".jarvis" / "servers.json")


class ServerManagerService:
    """Manages a registry of servers — spawning, monitoring, and restarting."""

    def __init__(
        self,
        registry_path: Optional[str] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self._registry_path = registry_path or DEFAULT_REGISTRY_PATH
        self.logger = logger or JarvisLogger()
        self._servers: Dict[str, ServerState] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._restart_timers: Dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Registry I/O
    # ------------------------------------------------------------------

    def load_registry(self) -> None:
        """Load servers.json, creating it if missing."""
        path = Path(self._registry_path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"servers": []}, indent=2))
            self.logger.log("INFO", "Created empty server registry", str(path))
            return

        try:
            data = json.loads(path.read_text())
            for entry in data.get("servers", []):
                config = ServerConfig.from_dict(entry)
                self._servers[config.name] = ServerState(config=config)
            self.logger.log(
                "INFO",
                "Loaded server registry",
                f"{len(self._servers)} server(s) from {path}",
            )
        except (json.JSONDecodeError, KeyError) as exc:
            self.logger.log("WARNING", "Failed to parse server registry", str(exc))

    def _save_registry(self) -> None:
        """Persist current configs back to disk."""
        path = Path(self._registry_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "servers": [
                state.config.to_dict() for state in self._servers.values()
            ]
        }
        path.write_text(json.dumps(data, indent=2))

    def register_server(self, config: ServerConfig) -> None:
        """Add a server to the registry at runtime."""
        self._servers[config.name] = ServerState(config=config)
        self._save_registry()
        self.logger.log("INFO", "Registered server", config.name)

    def unregister_server(self, name: str) -> bool:
        """Remove a server from the registry. Returns False if not found."""
        if name not in self._servers:
            return False
        # Cancel any pending restart timer
        timer = self._restart_timers.pop(name, None)
        if timer and not timer.done():
            timer.cancel()
        del self._servers[name]
        self._processes.pop(name, None)
        self._save_registry()
        self.logger.log("INFO", "Unregistered server", name)
        return True

    @property
    def servers(self) -> Dict[str, ServerState]:
        return dict(self._servers)

    def get_server(self, name: str) -> Optional[ServerState]:
        return self._servers.get(name)

    def get_servers_by_tag(self, tag: str) -> List[ServerState]:
        return [s for s in self._servers.values() if tag in s.config.tags]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_server(self, name: str) -> ServerState:
        """Start a managed server. Raises ValueError for external servers."""
        state = self._servers.get(name)
        if not state:
            raise KeyError(f"Unknown server: {name}")

        if state.config.mode == ServerMode.EXTERNAL:
            raise ValueError(f"Cannot start external server '{name}' — it is managed outside Jarvis")

        if state.status == ServerStatus.RUNNING:
            return state

        state.status = ServerStatus.STARTING
        cmd = state.config.command
        if not cmd:
            state.status = ServerStatus.CRASHED
            state.error_message = "No command configured"
            raise ValueError(f"Server '{name}' has no command configured")

        env = dict(os.environ)
        env.update(state.config.environment)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=state.config.working_directory,
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._processes[name] = proc
            state.pid = proc.pid
            state.status = ServerStatus.RUNNING
            state.started_at = datetime.now(timezone.utc)
            state.error_message = None
            self.logger.log("INFO", f"Started server '{name}'", f"PID {proc.pid}")
        except Exception as exc:
            state.status = ServerStatus.CRASHED
            state.error_message = str(exc)
            self.logger.log("ERROR", f"Failed to start '{name}'", str(exc))
            raise

        return state

    async def stop_server(self, name: str, timeout: float = 10.0) -> ServerState:
        """Stop a managed server. SIGTERM then SIGKILL after timeout."""
        state = self._servers.get(name)
        if not state:
            raise KeyError(f"Unknown server: {name}")

        if state.config.mode == ServerMode.EXTERNAL:
            raise ValueError(f"Cannot stop external server '{name}'")

        proc = self._processes.get(name)
        if not proc or proc.returncode is not None:
            state.status = ServerStatus.STOPPED
            state.pid = None
            return state

        state.status = ServerStatus.STOPPING

        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                self.logger.log("WARNING", f"Force-killed '{name}'", f"PID {proc.pid}")
        except ProcessLookupError:
            pass

        state.last_exit_code = proc.returncode
        state.status = ServerStatus.STOPPED
        state.pid = None
        self._processes.pop(name, None)
        self.logger.log("INFO", f"Stopped server '{name}'", f"exit={proc.returncode}")
        return state

    async def restart_server(self, name: str) -> ServerState:
        """Stop then start a managed server."""
        await self.stop_server(name)
        return await self.start_server(name)

    async def start_boot_servers(self) -> List[str]:
        """Start all servers with start_on_boot=True. Returns names started."""
        started: List[str] = []
        for name, state in self._servers.items():
            if state.config.start_on_boot and state.config.mode == ServerMode.MANAGED:
                try:
                    await self.start_server(name)
                    started.append(name)
                except Exception as exc:
                    self.logger.log("WARNING", f"Boot start failed for '{name}'", str(exc))
        return started

    async def stop_all(self) -> None:
        """Gracefully stop all managed servers."""
        for name, state in list(self._servers.items()):
            if state.config.mode == ServerMode.MANAGED and state.status == ServerStatus.RUNNING:
                try:
                    await self.stop_server(name)
                except Exception as exc:
                    self.logger.log("WARNING", f"Failed to stop '{name}'", str(exc))

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    async def check_health(self, name: str) -> "ProbeResult":
        """Check health of a single server. Returns a ProbeResult."""
        ProbeResult, ComponentStatus = _health_models()

        state = self._servers.get(name)
        if not state:
            return ProbeResult(
                component=name,
                component_type="service",
                status=ComponentStatus.UNKNOWN,
                message=f"Unknown server: {name}",
            )

        url = state.config.health_url()
        start = time.monotonic()

        # Strategy 1: HTTP health endpoint
        if url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(url)
                latency = (time.monotonic() - start) * 1000
                state.last_health_check = datetime.now(timezone.utc)
                state.last_health_latency_ms = latency

                if resp.status_code < 400:
                    state.consecutive_failures = 0
                    if state.status in (ServerStatus.UNHEALTHY, ServerStatus.STARTING):
                        state.status = ServerStatus.RUNNING
                    return ProbeResult(
                        component=f"server:{name}",
                        component_type="service",
                        status=ComponentStatus.HEALTHY,
                        latency_ms=latency,
                        message=f"HTTP {resp.status_code}",
                        details={"port": state.config.port},
                    )
                else:
                    state.consecutive_failures += 1
                    state.status = ServerStatus.UNHEALTHY
                    return ProbeResult(
                        component=f"server:{name}",
                        component_type="service",
                        status=ComponentStatus.UNHEALTHY,
                        latency_ms=latency,
                        message=f"HTTP {resp.status_code}",
                        details={"port": state.config.port},
                    )
            except Exception as exc:
                latency = (time.monotonic() - start) * 1000
                state.last_health_check = datetime.now(timezone.utc)
                state.last_health_latency_ms = latency
                state.consecutive_failures += 1
                state.status = ServerStatus.UNHEALTHY
                return ProbeResult(
                    component=f"server:{name}",
                    component_type="service",
                    status=ComponentStatus.UNHEALTHY,
                    latency_ms=latency,
                    message=str(exc),
                )

        # Strategy 2: TCP connect (port only, no health endpoint)
        if state.config.port:
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(state.config.host, state.config.port),
                    timeout=5.0,
                )
                writer.close()
                await writer.wait_closed()
                latency = (time.monotonic() - start) * 1000
                state.last_health_check = datetime.now(timezone.utc)
                state.last_health_latency_ms = latency
                state.consecutive_failures = 0
                if state.status in (ServerStatus.UNHEALTHY, ServerStatus.STARTING):
                    state.status = ServerStatus.RUNNING
                return ProbeResult(
                    component=f"server:{name}",
                    component_type="service",
                    status=ComponentStatus.HEALTHY,
                    latency_ms=latency,
                    message=f"TCP port {state.config.port} open",
                )
            except Exception:
                latency = (time.monotonic() - start) * 1000
                state.last_health_check = datetime.now(timezone.utc)
                state.last_health_latency_ms = latency
                state.consecutive_failures += 1
                state.status = ServerStatus.UNHEALTHY
                return ProbeResult(
                    component=f"server:{name}",
                    component_type="service",
                    status=ComponentStatus.UNHEALTHY,
                    latency_ms=latency,
                    message=f"TCP port {state.config.port} refused",
                )

        # Strategy 3: PID alive check (managed only)
        if state.config.mode == ServerMode.MANAGED:
            proc = self._processes.get(name)
            if proc and proc.returncode is None:
                state.last_health_check = datetime.now(timezone.utc)
                state.consecutive_failures = 0
                return ProbeResult(
                    component=f"server:{name}",
                    component_type="service",
                    status=ComponentStatus.HEALTHY,
                    message=f"PID {proc.pid} alive",
                )
            else:
                state.consecutive_failures += 1
                state.status = ServerStatus.CRASHED
                state.last_exit_code = proc.returncode if proc else None
                return ProbeResult(
                    component=f"server:{name}",
                    component_type="service",
                    status=ComponentStatus.UNHEALTHY,
                    message=f"Process exited (code={proc.returncode if proc else '?'})",
                )

        # No way to check health
        return ProbeResult(
            component=f"server:{name}",
            component_type="service",
            status=ComponentStatus.UNKNOWN,
            message="No health check method available",
        )

    async def check_all_health(self) -> List["ProbeResult"]:
        """Check health of all registered servers."""
        results = []
        for name in self._servers:
            results.append(await self.check_health(name))
        return results

    # ------------------------------------------------------------------
    # Auto-restart
    # ------------------------------------------------------------------

    async def maybe_auto_restart(self, name: str) -> bool:
        """Check if a crashed/unhealthy managed server should be restarted.

        Returns True if a restart was scheduled/initiated.
        Uses exponential backoff: min(1 * 2^count, 60) seconds.
        """
        state = self._servers.get(name)
        if not state:
            return False

        if state.config.mode != ServerMode.MANAGED:
            return False

        policy = state.config.restart_policy
        if policy == RestartPolicy.NEVER:
            return False

        if policy == RestartPolicy.ON_FAILURE and state.status not in (
            ServerStatus.CRASHED, ServerStatus.UNHEALTHY
        ):
            return False

        if state.restart_count >= state.config.max_restarts:
            self.logger.log(
                "WARNING",
                f"Max restarts reached for '{name}'",
                f"{state.restart_count}/{state.config.max_restarts}",
            )
            return False

        # Check if restart_window elapsed since last start → reset counter
        if state.started_at:
            elapsed = (datetime.now(timezone.utc) - state.started_at).total_seconds()
            if elapsed >= state.config.restart_window:
                state.restart_count = 0

        delay = min(1.0 * (2 ** state.restart_count), 60.0)
        state.restart_count += 1

        self.logger.log(
            "INFO",
            f"Scheduling restart for '{name}'",
            f"attempt {state.restart_count}/{state.config.max_restarts}, delay {delay:.1f}s",
        )

        async def _delayed_restart():
            await asyncio.sleep(delay)
            try:
                await self.start_server(name)
            except Exception as exc:
                self.logger.log("ERROR", f"Restart failed for '{name}'", str(exc))

        # Cancel any existing timer
        existing = self._restart_timers.pop(name, None)
        if existing and not existing.done():
            existing.cancel()

        self._restart_timers[name] = asyncio.create_task(_delayed_restart())
        return True

    async def detect_crashes(self) -> List[str]:
        """Check managed processes for unexpected exits. Returns names of crashed servers."""
        crashed: List[str] = []
        for name, state in self._servers.items():
            if state.config.mode != ServerMode.MANAGED:
                continue
            if state.status not in (ServerStatus.RUNNING, ServerStatus.STARTING):
                continue
            proc = self._processes.get(name)
            if proc and proc.returncode is not None:
                state.status = ServerStatus.CRASHED
                state.last_exit_code = proc.returncode
                state.error_message = f"Process exited unexpectedly with code {proc.returncode}"
                crashed.append(name)
                self.logger.log(
                    "WARNING",
                    f"Detected crash: '{name}'",
                    f"exit={proc.returncode}",
                )
        return crashed
