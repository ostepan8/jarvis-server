# jarvis/protocols/voice_trigger.py
"""Simple voice trigger detection for protocols"""

from typing import Dict, Optional
from .models import Protocol


class VoiceTriggerMatcher:
    """Match voice commands to protocols using simple keyword matching."""

    def __init__(self, protocols: Dict[str, Protocol]):
        self.protocols = protocols
        self._build_trigger_map()

    def _build_trigger_map(self):
        """Build a map of trigger phrases to protocols."""
        self.trigger_map = {}
        for protocol in self.protocols.values():
            for phrase in protocol.trigger_phrases:
                # Normalize phrase
                normalized = phrase.lower().strip()
                self.trigger_map[normalized] = protocol

    def match_command(self, voice_command: str) -> Optional[Protocol]:
        """Find protocol that matches the voice command."""
        normalized = voice_command.lower().strip()

        # Exact match
        if normalized in self.trigger_map:
            return self.trigger_map[normalized]

        # Partial match (command contains trigger phrase)
        for trigger, protocol in self.trigger_map.items():
            if trigger in normalized:
                return protocol

        return None

    def update_protocols(self, protocols: Dict[str, Protocol]):
        """Update the protocols and rebuild the trigger map."""
        self.protocols = protocols
        self._build_trigger_map()

    def get_all_triggers(self) -> Dict[str, str]:
        """Get all trigger phrases and their associated protocol names."""
        return {
            trigger: protocol.name for trigger, protocol in self.trigger_map.items()
        }
