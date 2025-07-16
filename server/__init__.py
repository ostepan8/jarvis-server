from importlib import import_module

# Re-export key objects from the legacy `server2` module for backwards
# compatibility with tests that import from `server`.
_server2 = import_module("server2")

app = _server2.app
pwd_context = getattr(_server2, "pwd_context", None)
get_jarvis = _server2.get_jarvis
list_protocols = _server2.list_protocols

__all__ = ["app", "pwd_context", "get_jarvis", "list_protocols"]
