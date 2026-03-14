"""Import smoke test for main.py — catches missing dependencies in the
full import chain before they ambush us at runtime.

The croniter incident of '26 taught us a valuable lesson: if the module
can't even import, nothing else matters.
"""

import importlib
import subprocess
import sys

import pytest


class TestMainModuleImports:
    """Verify that ``main.py`` and its transitive imports resolve cleanly."""

    def test_main_module_imports_without_error(self):
        """Importing main should not raise ImportError or ModuleNotFoundError.

        This is the exact scenario that broke ``python main.py`` when croniter
        was missing — the import chain cascaded through jarvis → agents →
        factory → scheduler_agent → scheduler_service → croniter → boom.
        """
        try:
            importlib.import_module("main")
        except ModuleNotFoundError as exc:
            pytest.fail(
                f"main.py import chain broken — missing module: {exc.name}"
            )

    def test_jarvis_package_imports_without_error(self):
        """The jarvis package __init__ re-exports core symbols.  If any
        submodule in that chain has an unsatisfied dependency, this explodes."""
        try:
            importlib.import_module("jarvis")
        except ModuleNotFoundError as exc:
            pytest.fail(
                f"jarvis package import chain broken — missing module: {exc.name}"
            )

    def test_server_package_imports_without_error(self):
        """The server package powers the FastAPI layer.  Same principle."""
        try:
            importlib.import_module("server")
        except ModuleNotFoundError as exc:
            pytest.fail(
                f"server package import chain broken — missing module: {exc.name}"
            )


class TestCriticalThirdPartyDeps:
    """Verify that every third-party package in the import chain is
    actually installed.  Each of these has caused (or could cause) the
    exact startup crash we're guarding against."""

    @pytest.mark.parametrize(
        "module_name",
        [
            "croniter",
            "dotenv",
            "tzlocal",
            "colorama",
            "fastapi",
            "uvicorn",
            "httpx",
            "openai",
            "pydantic",
            "rich",
        ],
    )
    def test_third_party_module_importable(self, module_name):
        """Each critical dependency must be importable."""
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            pytest.fail(
                f"Required dependency '{module_name}' is not installed. "
                f"Run: pip install {module_name}"
            )


class TestEntrypointExecution:
    """Verify that ``python main.py --help`` exits cleanly — a true
    end-to-end smoke test that catches issues even importlib might miss
    (e.g. top-level side effects that only fire under __main__)."""

    def test_main_help_exits_zero(self):
        """``python main.py --help`` should succeed without traceback."""
        result = subprocess.run(
            [sys.executable, "main.py", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"main.py --help failed (rc={result.returncode}):\n{result.stderr}"
        )
