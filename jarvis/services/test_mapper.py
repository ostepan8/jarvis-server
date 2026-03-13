"""Maps source modules to their test files via import scanning.

Enables targeted test runs by identifying which test files exercise
a given source module. Uses AST parsing to extract imports from test
files and builds a reverse mapping from source path to test paths.
"""

from __future__ import annotations

import ast
from pathlib import Path


class TestMapper:
    """Maps source files to test files that import them."""

    def __init__(self, project_root: str) -> None:
        self._project_root = Path(project_root)
        self._mapping: dict[str, set[str]] | None = None  # source_path -> set of test paths

    def build_mapping(self) -> None:
        """Scan all test files and build the import-to-test mapping."""
        self._mapping = {}
        tests_dir = self._project_root / "tests"
        if not tests_dir.is_dir():
            return

        for test_file in tests_dir.glob("test_*.py"):
            rel_test = str(test_file.relative_to(self._project_root))
            try:
                source = test_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(test_file))
            except Exception:
                continue

            imported_modules: set[str] = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("jarvis."):
                            imported_modules.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("jarvis."):
                        imported_modules.add(node.module)

            # Resolve import paths to file paths
            for mod in imported_modules:
                source_path = self._resolve_module(mod)
                if source_path:
                    self._mapping.setdefault(source_path, set()).add(rel_test)

            # Also apply naming convention: test_foo_service.py -> jarvis/services/foo_service.py
            stem = test_file.stem  # e.g. "test_foo_service"
            if stem.startswith("test_"):
                module_name = stem[5:]  # "foo_service"
                convention_paths = self._convention_paths(module_name)
                for cp in convention_paths:
                    if (self._project_root / cp).exists():
                        self._mapping.setdefault(cp, set()).add(rel_test)

    def tests_for_files(self, changed_files: list[str]) -> list[str]:
        """Return test files that cover the given source files.

        Lazy-builds the mapping on first call. Returns [] when no
        mapping found (caller should run full suite).
        """
        if self._mapping is None:
            self.build_mapping()

        result: set[str] = set()
        for f in changed_files:
            # Normalize to relative path
            normalized = f.replace(str(self._project_root) + "/", "")
            if normalized in self._mapping:
                result.update(self._mapping[normalized])

        return sorted(result)

    def invalidate(self) -> None:
        """Force the mapping to be rebuilt on next call."""
        self._mapping = None

    def _resolve_module(self, module_path: str) -> str | None:
        """Convert a dotted import path to a relative file path.

        Examples:
            jarvis.services.todo_service -> jarvis/services/todo_service.py
            jarvis.agents.calendar_agent -> jarvis/agents/calendar_agent/__init__.py
        """
        parts = module_path.split(".")
        # Try as a .py file first
        file_path = Path(*parts).with_suffix(".py")
        if (self._project_root / file_path).exists():
            return str(file_path)

        # Try as a package (__init__.py)
        package_path = Path(*parts) / "__init__.py"
        if (self._project_root / package_path).exists():
            return str(package_path)

        # Module may be a submodule reference — try parent as package
        if len(parts) > 1:
            parent_file = Path(*parts[:-1]).with_suffix(".py")
            if (self._project_root / parent_file).exists():
                return str(parent_file)

        return None

    @staticmethod
    def _convention_paths(module_name: str) -> list[str]:
        """Generate possible source paths from a test module name.

        test_foo_service -> [jarvis/services/foo_service.py, jarvis/agents/foo_service.py, ...]
        test_foo_agent -> [jarvis/agents/foo_agent/__init__.py, ...]
        """
        paths = [
            f"jarvis/services/{module_name}.py",
            f"jarvis/agents/{module_name}.py",
            f"jarvis/core/{module_name}.py",
        ]
        if module_name.endswith("_agent"):
            paths.append(f"jarvis/agents/{module_name}/__init__.py")
        return paths
