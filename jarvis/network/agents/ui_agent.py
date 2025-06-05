from __future__ import annotations


class UIAgent:
    """Placeholder agent representing a user interface in the network."""

    async def prompt(self, message: str) -> str:
        # In a real application this would get input from a user.
        # Here we just echo the prompt for demonstration purposes.
        return message
