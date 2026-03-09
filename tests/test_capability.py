"""Tests for Capability data structure."""

import pytest

from jarvis.agents.capability import Capability


class TestCapabilityCreation:
    """Test Capability dataclass creation."""

    def test_create_capability(self):
        """Test creating a basic capability."""
        def handler(**kwargs):
            return "result"

        cap = Capability(
            name="get_weather",
            description="Get current weather for a location",
            parameters={"location": {"type": "string", "required": True}},
            handler=handler,
        )
        assert cap.name == "get_weather"
        assert cap.description == "Get current weather for a location"
        assert "location" in cap.parameters
        assert cap.handler is handler

    def test_capability_handler_is_callable(self):
        """Test capability handler is callable."""
        def handler(**kwargs):
            return "result"

        cap = Capability(
            name="test",
            description="test capability",
            parameters={},
            handler=handler,
        )
        assert callable(cap.handler)

    def test_capability_handler_can_be_invoked(self):
        """Test capability handler can be called directly."""
        def handler(name="World"):
            return f"Hello, {name}!"

        cap = Capability(
            name="greet",
            description="Greet a person",
            parameters={"name": {"type": "string"}},
            handler=handler,
        )
        result = cap.handler(name="Alice")
        assert result == "Hello, Alice!"

    def test_capability_with_empty_parameters(self):
        """Test capability with no parameters."""
        cap = Capability(
            name="status",
            description="Get system status",
            parameters={},
            handler=lambda: "OK",
        )
        assert cap.parameters == {}

    def test_capability_with_complex_parameters(self):
        """Test capability with complex parameter definitions."""
        params = {
            "location": {
                "type": "string",
                "required": True,
                "description": "City name",
            },
            "unit": {
                "type": "string",
                "required": False,
                "default": "celsius",
                "enum": ["celsius", "fahrenheit"],
            },
        }
        cap = Capability(
            name="get_weather",
            description="Get weather",
            parameters=params,
            handler=lambda **kwargs: None,
        )
        assert cap.parameters["location"]["required"] is True
        assert cap.parameters["unit"]["default"] == "celsius"

    def test_capability_with_lambda_handler(self):
        """Test capability with a lambda handler."""
        cap = Capability(
            name="echo",
            description="Echo input",
            parameters={"text": {"type": "string"}},
            handler=lambda text="": text,
        )
        result = cap.handler(text="hello")
        assert result == "hello"

    def test_capability_with_async_handler(self):
        """Test capability can store an async handler."""
        async def async_handler(**kwargs):
            return "async result"

        cap = Capability(
            name="async_test",
            description="Async capability",
            parameters={},
            handler=async_handler,
        )
        assert callable(cap.handler)

    def test_capability_equality(self):
        """Test two capabilities with same fields are equal."""
        handler = lambda: None
        cap1 = Capability(name="test", description="desc", parameters={}, handler=handler)
        cap2 = Capability(name="test", description="desc", parameters={}, handler=handler)
        assert cap1 == cap2

    def test_capability_inequality(self):
        """Test two capabilities with different names are not equal."""
        handler = lambda: None
        cap1 = Capability(name="test1", description="desc", parameters={}, handler=handler)
        cap2 = Capability(name="test2", description="desc", parameters={}, handler=handler)
        assert cap1 != cap2


class TestCapabilityWithMethodHandler:
    """Test Capability with class method handlers."""

    def test_capability_with_bound_method(self):
        """Test capability handler as a bound method."""
        class MyService:
            def process(self, data=""):
                return f"Processed: {data}"

        service = MyService()
        cap = Capability(
            name="process",
            description="Process data",
            parameters={"data": {"type": "string"}},
            handler=service.process,
        )
        result = cap.handler(data="test")
        assert result == "Processed: test"


class TestCapabilityFieldAccess:
    """Test accessing Capability fields."""

    def test_name_field(self):
        """Test accessing name field."""
        cap = Capability(
            name="my_capability",
            description="desc",
            parameters={},
            handler=lambda: None,
        )
        assert cap.name == "my_capability"

    def test_description_field(self):
        """Test accessing description field."""
        cap = Capability(
            name="cap",
            description="A detailed description of what this does",
            parameters={},
            handler=lambda: None,
        )
        assert "detailed description" in cap.description

    def test_parameters_field_is_dict(self):
        """Test parameters is a dict."""
        cap = Capability(
            name="cap",
            description="desc",
            parameters={"p1": "v1"},
            handler=lambda: None,
        )
        assert isinstance(cap.parameters, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
