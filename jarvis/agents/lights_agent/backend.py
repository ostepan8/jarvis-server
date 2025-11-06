"""Abstract base class for lighting backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseLightingBackend(ABC):
    """Abstract base class defining the interface for lighting control backends."""

    @abstractmethod
    def turn_on_all_lights(self) -> str:
        """Turn on all lights in the system."""
        pass

    @abstractmethod
    def turn_off_all_lights(self) -> str:
        """Turn off all lights in the system."""
        pass

    @abstractmethod
    def set_all_brightness(self, brightness: int) -> str:
        """Set brightness for all lights (0-254)."""
        pass

    @abstractmethod
    def set_all_color(self, color_name: str) -> str:
        """Set color for all lights using a color name."""
        pass

    @abstractmethod
    def turn_on_light(self, light_name: str) -> str:
        """Turn on a specific light."""
        pass

    @abstractmethod
    def turn_off_light(self, light_name: str) -> str:
        """Turn off a specific light."""
        pass

    @abstractmethod
    def toggle_light(self, light_name: str) -> str:
        """Toggle a light on/off."""
        pass

    @abstractmethod
    def set_brightness(self, light_name: str, brightness: int) -> str:
        """Set brightness of a specific light (0-254)."""
        pass

    @abstractmethod
    def set_color_name(self, light_name: str, color_name: str) -> str:
        """Set color of a specific light using a color name."""
        pass

    @abstractmethod
    def list_lights(self) -> Dict[str, Any]:
        """List all lights with their IDs and names."""
        pass

    @abstractmethod
    def get_color_map(self) -> Dict[str, Dict[str, int]]:
        """Get the color mapping dictionary."""
        pass
