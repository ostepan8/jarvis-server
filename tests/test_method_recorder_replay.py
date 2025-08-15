import importlib.util
import sys
import types
from pathlib import Path
import pytest

# Dynamically load modules to avoid heavy package-level imports
package_path = Path(__file__).resolve().parents[1] / "jarvis"
core_path = package_path / "core"
agents_path = package_path / "agents"
logging_path = package_path / "logging"
protocols_path = package_path / "protocols"

# Create package stubs
jarvis_pkg = types.ModuleType("jarvis")
jarvis_pkg.__path__ = [str(package_path)]
sys.modules.setdefault("jarvis", jarvis_pkg)

core_pkg = types.ModuleType("jarvis.core")
core_pkg.__path__ = [str(core_path)]
sys.modules.setdefault("jarvis.core", core_pkg)

agents_pkg = types.ModuleType("jarvis.agents")
agents_pkg.__path__ = [str(agents_path)]
sys.modules.setdefault("jarvis.agents", agents_pkg)

logging_pkg = types.ModuleType("jarvis.logging")
logging_pkg.__path__ = [str(logging_path)]
sys.modules.setdefault("jarvis.logging", logging_pkg)

protocols_pkg = types.ModuleType("jarvis.protocols")
protocols_pkg.__path__ = [str(protocols_path)]
sys.modules.setdefault("jarvis.protocols", protocols_pkg)

# Provide minimal loggers submodule to satisfy ProtocolExecutor imports
loggers_pkg = types.ModuleType("jarvis.protocols.loggers")

class _StubLogger:  # pragma: no cover - simple stub
    async def log_usage(self, *_args, **_kwargs):
        return None


def _stub_generate_protocol_log(*_args, **_kwargs):  # pragma: no cover
    return {}


loggers_pkg.ProtocolUsageLogger = _StubLogger
loggers_pkg.generate_protocol_log = _stub_generate_protocol_log
sys.modules.setdefault("jarvis.protocols.loggers", loggers_pkg)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore
    return module

InstructionProtocol = load(
    "jarvis.protocols.instruction_protocol", protocols_path / "instruction_protocol.py"
).InstructionProtocol
sys.modules["jarvis.protocols"].InstructionProtocol = InstructionProtocol
Protocol = load("jarvis.protocols.models", protocols_path / "models/__init__.py").Protocol
sys.modules["jarvis.protocols"].Protocol = Protocol

JarvisLogger = load("jarvis.logging", logging_path / "__init__.py").JarvisLogger
MethodRecorder = load("jarvis.core.method_recorder", core_path / "method_recorder.py").MethodRecorder
AgentNetwork = load("jarvis.agents.agent_network", agents_path / "agent_network.py").AgentNetwork


class DummyAgent:
    def __init__(self) -> None:
        self.name = "dummy"
        self.intent_map = {"dummy_cap": self.echo}
        self.network = None

    @property
    def capabilities(self):
        return set(self.intent_map)

    def set_network(self, network):  # called by AgentNetwork.register_agent
        self.network = network

    async def run_capability(self, function: str, **kwargs):
        return await self.intent_map[function](**kwargs)

    async def echo(self, **kwargs):
        return {"echo": kwargs}


@pytest.mark.asyncio
async def test_replay_last_protocol():
    network = AgentNetwork()
    agent = DummyAgent()
    network.register_agent(agent)
    await network.start()

    logger = JarvisLogger()
    recorder = MethodRecorder()
    recorder.start("demo")
    recorder.record_step("dummy", "dummy_cap", {"msg": "hi"})
    recorder.replace_step(0, "dummy", "dummy_cap", {"msg": "hello"})

    result = await recorder.replay_last_protocol(network, logger)
    await network.stop()

    assert result["step_0_dummy_cap"]["echo"] == {"msg": "hello"}
