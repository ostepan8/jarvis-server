"""Tests for jarvis.core.registry — BaseRegistry and FunctionRegistry."""

import pytest

from jarvis.core.registry import BaseRegistry, FunctionRegistry


# ---------------------------------------------------------------------------
# BaseRegistry
# ---------------------------------------------------------------------------
class TestBaseRegistry:
    """Tests for the generic BaseRegistry."""

    def test_empty_registry(self):
        reg = BaseRegistry()
        assert reg.items == {}
        assert reg.keys == set()

    def test_initial_map(self):
        reg = BaseRegistry(initial_map={"a": 1, "b": 2})
        assert reg.get("a") == 1
        assert reg.get("b") == 2
        assert reg.keys == {"a", "b"}

    def test_add_and_get(self):
        reg = BaseRegistry()
        reg.add("item1", "value1")
        assert reg.get("item1") == "value1"

    def test_get_missing_returns_none(self):
        reg = BaseRegistry()
        assert reg.get("nonexistent") is None

    def test_has_existing(self):
        reg = BaseRegistry()
        reg.add("x", 42)
        assert reg.has("x") is True

    def test_has_missing(self):
        reg = BaseRegistry()
        assert reg.has("x") is False

    def test_remove_existing(self):
        reg = BaseRegistry()
        reg.add("key", "val")
        result = reg.remove("key")
        assert result is True
        assert reg.has("key") is False
        assert reg.get("key") is None

    def test_remove_nonexistent(self):
        reg = BaseRegistry()
        result = reg.remove("missing")
        assert result is False

    def test_add_overwrites(self):
        reg = BaseRegistry()
        reg.add("k", "v1")
        reg.add("k", "v2")
        assert reg.get("k") == "v2"

    def test_items_returns_dict(self):
        reg = BaseRegistry(initial_map={"a": 1})
        items = reg.items
        assert isinstance(items, dict)
        assert items["a"] == 1

    def test_keys_returns_set(self):
        reg = BaseRegistry(initial_map={"x": 1, "y": 2})
        k = reg.keys
        assert isinstance(k, set)
        assert k == {"x", "y"}

    def test_multiple_add_and_remove(self):
        reg = BaseRegistry()
        reg.add("a", 1)
        reg.add("b", 2)
        reg.add("c", 3)
        assert len(reg.items) == 3
        reg.remove("b")
        assert len(reg.items) == 2
        assert reg.has("b") is False
        assert reg.has("a") is True
        assert reg.has("c") is True

    def test_none_initial_map(self):
        reg = BaseRegistry(initial_map=None)
        assert reg.items == {}

    def test_stores_various_types(self):
        reg = BaseRegistry()
        reg.add("int", 42)
        reg.add("str", "hello")
        reg.add("list", [1, 2, 3])
        reg.add("dict", {"key": "val"})
        reg.add("none", None)
        assert reg.get("int") == 42
        assert reg.get("str") == "hello"
        assert reg.get("list") == [1, 2, 3]
        assert reg.get("dict") == {"key": "val"}
        assert reg.get("none") is None


# ---------------------------------------------------------------------------
# FunctionRegistry
# ---------------------------------------------------------------------------
class TestFunctionRegistry:
    """Tests for the FunctionRegistry (callable-specialized)."""

    def test_empty_registry(self):
        reg = FunctionRegistry()
        assert reg.functions == {}
        assert reg.capabilities == set()

    def test_add_function_and_retrieve(self):
        def my_func():
            return "result"

        reg = FunctionRegistry()
        reg.add_function("my_func", my_func)
        assert reg.get_function("my_func") is my_func
        assert reg.has_function("my_func") is True

    def test_get_function_missing(self):
        reg = FunctionRegistry()
        assert reg.get_function("missing") is None

    def test_has_function_false(self):
        reg = FunctionRegistry()
        assert reg.has_function("missing") is False

    def test_remove_function(self):
        reg = FunctionRegistry()
        reg.add_function("f", lambda: None)
        result = reg.remove_function("f")
        assert result is True
        assert reg.has_function("f") is False

    def test_remove_function_nonexistent(self):
        reg = FunctionRegistry()
        result = reg.remove_function("nope")
        assert result is False

    def test_capabilities_property(self):
        reg = FunctionRegistry()
        reg.add_function("create_event", lambda: None)
        reg.add_function("delete_event", lambda: None)
        assert reg.capabilities == {"create_event", "delete_event"}

    def test_functions_property(self):
        fn = lambda: "test"
        reg = FunctionRegistry()
        reg.add_function("fn", fn)
        assert "fn" in reg.functions
        assert reg.functions["fn"] is fn

    def test_callable_can_be_invoked(self):
        def add(a, b):
            return a + b

        reg = FunctionRegistry()
        reg.add_function("add", add)
        fn = reg.get_function("add")
        assert fn(2, 3) == 5

    def test_lambda_function(self):
        reg = FunctionRegistry()
        reg.add_function("square", lambda x: x * x)
        assert reg.get_function("square")(4) == 16

    def test_async_function_stored(self):
        async def async_fn():
            return "async_result"

        reg = FunctionRegistry()
        reg.add_function("async_fn", async_fn)
        assert reg.has_function("async_fn") is True
        assert reg.get_function("async_fn") is async_fn

    def test_inherits_base_registry(self):
        reg = FunctionRegistry()
        assert isinstance(reg, BaseRegistry)

    def test_initial_map_with_callables(self):
        fn1 = lambda: 1
        fn2 = lambda: 2
        reg = FunctionRegistry(initial_map={"fn1": fn1, "fn2": fn2})
        assert reg.get_function("fn1") is fn1
        assert reg.get_function("fn2") is fn2
        assert reg.capabilities == {"fn1", "fn2"}
