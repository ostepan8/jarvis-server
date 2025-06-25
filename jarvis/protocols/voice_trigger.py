# jarvis/protocols/voice_trigger.py
"""Enhanced voice trigger detection for protocols with arguments"""

import re
from typing import Dict, Optional, Any, List
from .models import Protocol, ArgumentDefinition, ArgumentType


class ParameterizedProtocol:
    """Enhanced protocol that can handle arguments in trigger phrases."""

    def __init__(self, protocol: Protocol):
        self.protocol = protocol
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for each trigger phrase with placeholders."""
        self.patterns = []

        for phrase in self.protocol.trigger_phrases:
            # Find placeholders like {color} or {brightness}
            pattern = phrase
            placeholders = re.findall(r"\{(\w+)\}", phrase)

            for placeholder in placeholders:
                arg_def = self._get_argument_definition(placeholder)
                if arg_def:
                    if arg_def.type == ArgumentType.CHOICE:
                        # Replace {color} with (red|blue|green)
                        choices_pattern = "|".join(
                            re.escape(choice) for choice in arg_def.choices
                        )
                        pattern = pattern.replace(
                            f"{{{placeholder}}}", f"({choices_pattern})"
                        )
                    elif arg_def.type == ArgumentType.RANGE:
                        # Replace {brightness} with number pattern
                        pattern = pattern.replace(f"{{{placeholder}}}", r"(\d+)")
                    elif arg_def.type == ArgumentType.TEXT:
                        # Replace {text} with word pattern
                        pattern = pattern.replace(
                            f"{{{placeholder}}}", r"([^\s]+(?:\s+[^\s]+)*)"
                        )
                    elif arg_def.type == ArgumentType.BOOLEAN:
                        pattern = pattern.replace(
                            f"{{{placeholder}}}", r"(on|off|true|false|yes|no)"
                        )
                else:
                    # No definition found, treat as generic text
                    pattern = pattern.replace(f"{{{placeholder}}}", r"([^\s]+)")

            self.patterns.append(
                (re.compile(pattern, re.IGNORECASE), placeholders, phrase)
            )

    def _get_argument_definition(self, name: str) -> Optional[ArgumentDefinition]:
        """Get argument definition by name."""
        for arg_def in self.protocol.argument_definitions:
            if arg_def.name == name:
                return arg_def
        return None

    def match_and_extract(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Match user input and extract arguments."""
        normalized_input = user_input.strip()

        for pattern, placeholders, original_phrase in self.patterns:
            match = pattern.search(normalized_input)
            if match:
                # Extract arguments
                arguments = {}
                for i, placeholder in enumerate(placeholders):
                    if i + 1 <= len(match.groups()):
                        value = match.group(i + 1)
                        arg_def = self._get_argument_definition(placeholder)

                        if arg_def:
                            # Validate and convert the value
                            converted_value = self._convert_argument(value, arg_def)
                            if converted_value is not None:
                                arguments[placeholder] = converted_value
                            else:
                                return None  # Invalid argument
                        else:
                            arguments[placeholder] = value

                return {
                    "protocol": self.protocol,
                    "arguments": arguments,
                    "matched_phrase": original_phrase,
                }

        return None

    def _convert_argument(self, value: str, arg_def: ArgumentDefinition) -> Any:
        """Convert and validate argument value."""
        try:
            if arg_def.type == ArgumentType.CHOICE:
                if value.lower() in [choice.lower() for choice in arg_def.choices]:
                    return value.lower()
                return None

            elif arg_def.type == ArgumentType.RANGE:
                num_val = int(value)
                if arg_def.min_val is not None and num_val < arg_def.min_val:
                    return None
                if arg_def.max_val is not None and num_val > arg_def.max_val:
                    return None
                return num_val

            elif arg_def.type == ArgumentType.BOOLEAN:
                lower_val = value.lower()
                if lower_val in ["on", "true", "yes"]:
                    return True
                elif lower_val in ["off", "false", "no"]:
                    return False
                return None

            elif arg_def.type == ArgumentType.TEXT:
                return value.strip()

        except (ValueError, TypeError):
            return None

        return value


class VoiceTriggerMatcher:
    """Enhanced matcher that handles parameterized protocols."""

    def __init__(self, protocols: Dict[str, Protocol]):
        self.protocols = protocols
        self.parameterized_protocols: List[ParameterizedProtocol] = []
        self._build_trigger_map()

    def _build_trigger_map(self):
        """Build enhanced trigger map with argument support."""
        self.simple_triggers = {}  # For protocols without arguments
        self.parameterized_protocols = []  # For protocols with arguments

        for protocol in self.protocols.values():
            # Check if protocol has argument definitions or placeholders in triggers
            has_arguments = bool(protocol.argument_definitions)
            has_placeholders = any("{" in phrase for phrase in protocol.trigger_phrases)

            if has_arguments or has_placeholders:
                param_protocol = ParameterizedProtocol(protocol)
                self.parameterized_protocols.append(param_protocol)
            else:
                # Handle as simple trigger
                for phrase in protocol.trigger_phrases:
                    normalized = phrase.lower().strip()
                    self.simple_triggers[normalized] = protocol

    def match_command(self, voice_command: str) -> Optional[Dict[str, Any]]:
        """Match command and return protocol with extracted arguments."""
        normalized = voice_command.lower().strip()

        # First try parameterized protocols (more specific)
        for param_protocol in self.parameterized_protocols:
            result = param_protocol.match_and_extract(voice_command)
            if result:
                return result

        # Try simple exact matches
        if normalized in self.simple_triggers:
            return {
                "protocol": self.simple_triggers[normalized],
                "arguments": {},
                "matched_phrase": normalized,
            }

        # Try partial matches for simple triggers
        for trigger, protocol in self.simple_triggers.items():
            if trigger in normalized:
                return {
                    "protocol": protocol,
                    "arguments": {},
                    "matched_phrase": trigger,
                }

        return None

    def update_protocols(self, protocols: Dict[str, Protocol]):
        """Update the protocols and rebuild the trigger map."""
        self.protocols = protocols
        self._build_trigger_map()

    def get_all_triggers(self) -> Dict[str, str]:
        """Get all trigger phrases and their associated protocol names."""
        triggers = {}

        # Add simple triggers
        for trigger, protocol in self.simple_triggers.items():
            triggers[trigger] = protocol.name

        # Add parameterized triggers
        for param_proto in self.parameterized_protocols:
            for phrase in param_proto.protocol.trigger_phrases:
                triggers[phrase] = param_proto.protocol.name

        return triggers
