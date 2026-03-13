"""Tests for TestMapper — source-to-test-file mapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.services.test_mapper import TestMapper


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project structure for testing."""
    # Source files
    (tmp_path / "jarvis" / "services").mkdir(parents=True)
    (tmp_path / "jarvis" / "services" / "foo_service.py").write_text(
        "class FooService:\n    pass\n"
    )
    (tmp_path / "jarvis" / "services" / "bar_service.py").write_text(
        "class BarService:\n    pass\n"
    )
    (tmp_path / "jarvis" / "agents" / "chat_agent").mkdir(parents=True)
    (tmp_path / "jarvis" / "agents" / "chat_agent" / "__init__.py").write_text(
        "class ChatAgent:\n    pass\n"
    )
    (tmp_path / "jarvis" / "core").mkdir(parents=True)
    (tmp_path / "jarvis" / "core" / "config.py").write_text(
        "class Config:\n    pass\n"
    )

    # Test files
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "tests" / "test_foo_service.py").write_text(
        "from jarvis.services.foo_service import FooService\n"
        "\n"
        "def test_foo():\n"
        "    pass\n"
    )
    (tmp_path / "tests" / "test_bar_service.py").write_text(
        "from jarvis.services import bar_service\n"
        "\n"
        "def test_bar():\n"
        "    pass\n"
    )
    (tmp_path / "tests" / "test_chat_agent.py").write_text(
        "from jarvis.agents.chat_agent import ChatAgent\n"
        "\n"
        "def test_chat():\n"
        "    pass\n"
    )
    return tmp_path


class TestImportMapping:
    def test_import_to_test_mapping(self, tmp_path):
        """Test file importing a module should map back to it."""
        root = _setup_project(tmp_path)
        mapper = TestMapper(str(root))
        mapper.build_mapping()

        tests = mapper.tests_for_files(["jarvis/services/foo_service.py"])
        assert "tests/test_foo_service.py" in tests

    def test_from_import_mapping(self, tmp_path):
        """from jarvis.services import bar_service should map correctly."""
        root = _setup_project(tmp_path)
        mapper = TestMapper(str(root))
        mapper.build_mapping()

        tests = mapper.tests_for_files(["jarvis/services/bar_service.py"])
        assert "tests/test_bar_service.py" in tests

    def test_agent_package_mapping(self, tmp_path):
        """Agent packages (directories) should map via __init__.py imports."""
        root = _setup_project(tmp_path)
        mapper = TestMapper(str(root))
        mapper.build_mapping()

        tests = mapper.tests_for_files(["jarvis/agents/chat_agent/__init__.py"])
        assert "tests/test_chat_agent.py" in tests


class TestUnknownFiles:
    def test_unknown_file_returns_empty(self, tmp_path):
        """Files with no known test should return empty list."""
        root = _setup_project(tmp_path)
        mapper = TestMapper(str(root))
        mapper.build_mapping()

        tests = mapper.tests_for_files(["jarvis/services/unknown_service.py"])
        assert tests == []


class TestDeduplication:
    def test_no_duplicates(self, tmp_path):
        """Same test file should not appear twice."""
        root = _setup_project(tmp_path)
        mapper = TestMapper(str(root))
        mapper.build_mapping()

        # foo_service.py is mapped both by import and convention
        tests = mapper.tests_for_files(["jarvis/services/foo_service.py"])
        assert len(tests) == len(set(tests))


class TestConventionFallback:
    def test_convention_maps_without_import(self, tmp_path):
        """Even without an import, naming convention should create mapping."""
        root = _setup_project(tmp_path)
        # Create a test file that doesn't import the source but follows naming convention
        (root / "tests" / "test_config.py").write_text(
            "def test_config_works():\n    pass\n"
        )

        mapper = TestMapper(str(root))
        mapper.build_mapping()

        tests = mapper.tests_for_files(["jarvis/core/config.py"])
        assert "tests/test_config.py" in tests


class TestLazyBuild:
    def test_auto_builds_on_first_call(self, tmp_path):
        """tests_for_files should build mapping lazily."""
        root = _setup_project(tmp_path)
        mapper = TestMapper(str(root))

        # Don't call build_mapping explicitly
        tests = mapper.tests_for_files(["jarvis/services/foo_service.py"])
        assert "tests/test_foo_service.py" in tests


class TestInvalidate:
    def test_invalidate_forces_rebuild(self, tmp_path):
        """After invalidate(), the mapping should be rebuilt on next call."""
        root = _setup_project(tmp_path)
        mapper = TestMapper(str(root))
        mapper.build_mapping()

        # Get initial results
        tests1 = mapper.tests_for_files(["jarvis/services/foo_service.py"])

        # Add a new test file
        (root / "tests" / "test_foo_extra.py").write_text(
            "from jarvis.services.foo_service import FooService\n"
            "def test_extra():\n    pass\n"
        )

        # Without invalidate, old mapping
        tests2 = mapper.tests_for_files(["jarvis/services/foo_service.py"])
        assert tests2 == tests1

        # After invalidate, should pick up new file
        mapper.invalidate()
        tests3 = mapper.tests_for_files(["jarvis/services/foo_service.py"])
        assert "tests/test_foo_extra.py" in tests3


class TestEmptyProject:
    def test_no_tests_dir(self, tmp_path):
        """Project with no tests/ directory should return empty."""
        mapper = TestMapper(str(tmp_path))
        mapper.build_mapping()

        tests = mapper.tests_for_files(["jarvis/services/foo.py"])
        assert tests == []
