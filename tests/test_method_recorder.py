import importlib.util
import sys
import types
from pathlib import Path

# Import MethodRecorder without importing jarvis package-level dependencies
package_path = Path(__file__).resolve().parents[1] / "jarvis"
core_path = package_path / "core"
protocols_path = package_path / "protocols"

jarvis_pkg = types.ModuleType("jarvis")
jarvis_pkg.__path__ = [str(package_path)]
sys.modules.setdefault("jarvis", jarvis_pkg)

core_pkg = types.ModuleType("jarvis.core")
core_pkg.__path__ = [str(core_path)]
sys.modules.setdefault("jarvis.core", core_pkg)

protocols_pkg = types.ModuleType("jarvis.protocols")
protocols_pkg.__path__ = [str(protocols_path)]
sys.modules.setdefault("jarvis.protocols", protocols_pkg)

spec = importlib.util.spec_from_file_location(
    "jarvis.core.method_recorder", core_path / "method_recorder.py"
)
module = importlib.util.module_from_spec(spec)
sys.modules["jarvis.core.method_recorder"] = module
spec.loader.exec_module(module)
MethodRecorder = module.MethodRecorder


def test_method_recorder_flow():
    recorder = MethodRecorder()
    recorder.start("demo", "desc")

    recorder.record_step("agent", "func", {"a": 1})
    assert recorder.get_protocol() is not None
    assert len(recorder.get_protocol().steps) == 1
    assert recorder.get_protocol().steps[0].agent == "agent"

    recorder.replace_step(0, "agent2", "func2", {"b": 2})
    step = recorder.get_protocol().steps[0]
    assert step.agent == "agent2"
    assert step.function == "func2"

    proto = recorder.stop()
    assert proto is not None
    assert proto.name == "demo"
    assert recorder.get_protocol() is None
    assert recorder.recording is False


def test_clear_resets_state():
    recorder = MethodRecorder()
    recorder.start("x")
    recorder.clear()
    assert recorder.get_protocol() is None
    assert recorder.recording is False
