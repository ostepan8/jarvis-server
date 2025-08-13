from __future__ import annotations

from typing import Callable, Dict, Generic, Optional, Set, TypeVar

T = TypeVar("T")


class BaseRegistry(Generic[T]):
    """Generic registry storing items by name."""

    def __init__(self, initial_map: Optional[Dict[str, T]] = None) -> None:
        self._items: Dict[str, T] = initial_map or {}

    @property
    def items(self) -> Dict[str, T]:
        """Return the underlying mapping."""
        return self._items

    @property
    def keys(self) -> Set[str]:
        """Return the registry keys."""
        return set(self._items.keys())

    def get(self, name: str) -> Optional[T]:
        """Retrieve a registered item by name."""
        return self._items.get(name)

    def has(self, name: str) -> bool:
        """Check if the registry contains an item."""
        return name in self._items

    def add(self, name: str, item: T) -> None:
        """Add an item to the registry."""
        self._items[name] = item

    def remove(self, name: str) -> bool:
        """Remove an item from the registry."""
        if name in self._items:
            del self._items[name]
            return True
        return False


class FunctionRegistry(BaseRegistry[Callable]):
    """Registry specialised for callables used by agents."""

    @property
    def functions(self) -> Dict[str, Callable]:
        return self.items

    @property
    def capabilities(self) -> Set[str]:
        return self.keys

    def get_function(self, name: str) -> Optional[Callable]:
        return self.get(name)

    def has_function(self, name: str) -> bool:
        return self.has(name)

    def add_function(self, name: str, func: Callable) -> None:
        self.add(name, func)

    def remove_function(self, name: str) -> bool:
        return self.remove(name)
