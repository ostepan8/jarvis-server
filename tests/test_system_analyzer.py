"""Tests for SystemAnalyzer discovery engine."""

from __future__ import annotations

import ast
import asyncio
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jarvis.services.system_analyzer import (
    Discovery,
    DiscoveryType,
    SystemAnalyzer,
)
from jarvis.services.todo_service import TodoService


# ── Helpers ──────────────────────────────────────────────────────────


def _create_log_db(db_path: str) -> sqlite3.Connection:
    """Create a log database with the expected schema."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            level TEXT,
            action TEXT,
            details TEXT
        )
        """
    )
    conn.commit()
    return conn


def _insert_log(conn: sqlite3.Connection, level: str, action: str,
                details: str, timestamp: str | None = None) -> None:
    """Insert a log row with an optional custom timestamp."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO logs (timestamp, level, action, details) VALUES (?, ?, ?, ?)",
        (timestamp, level, action, details),
    )
    conn.commit()


def _make_analyzer(
    tmp_path,
    todo_service=None,
    project_root=None,
) -> SystemAnalyzer:
    db_path = str(tmp_path / "logs.db")
    _create_log_db(db_path)
    return SystemAnalyzer(
        project_root=project_root or str(tmp_path),
        log_db_path=db_path,
        todo_service=todo_service,
    )


# =====================================================================
# Log analysis
# =====================================================================


class TestLogAnalysis:
    """Test log database scanning."""

    @pytest.mark.asyncio
    async def test_finds_errors_in_last_24h(self, tmp_path):
        """Create a SQLite DB with recent ERROR entries, verify they're found."""
        db_path = str(tmp_path / "logs.db")
        conn = _create_log_db(db_path)
        _insert_log(conn, "ERROR", "agent_crash", "NullPointerException")
        _insert_log(conn, "ERROR", "timeout", "Request timed out after 30s")
        conn.close()

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=db_path,
        )
        results = await analyzer.analyze_logs()

        assert len(results) == 2
        assert all(d.discovery_type == DiscoveryType.LOG_ERROR for d in results)
        assert all(d.priority == "high" for d in results)
        titles = {d.title for d in results}
        assert "Log error: agent_crash" in titles
        assert "Log error: timeout" in titles

    @pytest.mark.asyncio
    async def test_finds_warnings(self, tmp_path):
        """Warnings should be detected with medium priority."""
        db_path = str(tmp_path / "logs.db")
        conn = _create_log_db(db_path)
        _insert_log(conn, "WARNING", "slow_response", "Took 5s")
        conn.close()

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=db_path,
        )
        results = await analyzer.analyze_logs()

        assert len(results) == 1
        assert results[0].priority == "medium"

    @pytest.mark.asyncio
    async def test_ignores_old_errors(self, tmp_path):
        """Errors older than lookback window should not be returned."""
        db_path = str(tmp_path / "logs.db")
        conn = _create_log_db(db_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        _insert_log(conn, "ERROR", "old_crash", "Ancient error", timestamp=old_ts)
        conn.close()

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=db_path,
        )
        results = await analyzer.analyze_logs(lookback_hours=24)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_deduplicates_by_action(self, tmp_path):
        """Multiple errors with same action should produce one Discovery."""
        db_path = str(tmp_path / "logs.db")
        conn = _create_log_db(db_path)
        _insert_log(conn, "ERROR", "repeated_error", "First occurrence")
        _insert_log(conn, "ERROR", "repeated_error", "Second occurrence")
        _insert_log(conn, "ERROR", "repeated_error", "Third occurrence")
        conn.close()

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=db_path,
        )
        results = await analyzer.analyze_logs()

        assert len(results) == 1
        assert results[0].title == "Log error: repeated_error"

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty(self, tmp_path):
        """No logs = no discoveries."""
        db_path = str(tmp_path / "logs.db")
        _create_log_db(db_path).close()

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=db_path,
        )
        results = await analyzer.analyze_logs()

        assert results == []

    @pytest.mark.asyncio
    async def test_missing_db_returns_empty(self, tmp_path):
        """Non-existent database should return empty, not crash."""
        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "nonexistent.db"),
        )
        results = await analyzer.analyze_logs()

        assert results == []


# =====================================================================
# Test analysis
# =====================================================================


class TestTestAnalysis:
    """Test pytest output parsing."""

    @pytest.mark.asyncio
    async def test_parses_failure_output(self, tmp_path, monkeypatch):
        """Mock subprocess to return failed test output, verify parsing."""

        async def mock_subprocess(*args, **kwargs):
            class FakeProcess:
                returncode = 1

                async def communicate(self):
                    stdout = (
                        b"FAILED tests/test_foo.py::TestFoo::test_bar"
                        b" - AssertionError\n"
                        b"FAILED tests/test_baz.py::TestBaz::test_qux"
                        b" - ValueError\n"
                        b"2 failed\n"
                    )
                    return stdout, b""

            return FakeProcess()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
        )
        results = await analyzer.analyze_tests()

        assert len(results) == 2
        assert all(d.discovery_type == DiscoveryType.TEST_FAILURE for d in results)
        assert all(d.priority == "urgent" for d in results)
        assert results[0].relevant_files == ["tests/test_foo.py"]
        assert results[1].relevant_files == ["tests/test_baz.py"]
        assert "AssertionError" in results[0].source_detail
        assert "ValueError" in results[1].source_detail

    @pytest.mark.asyncio
    async def test_all_passing_returns_empty(self, tmp_path, monkeypatch):
        """When all tests pass, no discoveries."""

        async def mock_subprocess(*args, **kwargs):
            class FakeProcess:
                returncode = 0

                async def communicate(self):
                    return b"42 passed\n", b""

            return FakeProcess()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
        )
        results = await analyzer.analyze_tests()

        assert results == []

    @pytest.mark.asyncio
    async def test_handles_pytest_error(self, tmp_path, monkeypatch):
        """When pytest itself errors, return empty list, don't crash."""

        async def mock_subprocess(*args, **kwargs):
            raise OSError("pytest not found")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
        )
        results = await analyzer.analyze_tests()

        assert results == []

    @pytest.mark.asyncio
    async def test_handles_timeout(self, tmp_path, monkeypatch):
        """When pytest times out, return empty list."""

        async def mock_subprocess(*args, **kwargs):
            class FakeProcess:
                returncode = None

                async def communicate(self):
                    await asyncio.sleep(999)
                    return b"", b""

            return FakeProcess()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
        )
        # Use a very short timeout to trigger the timeout path
        results = await analyzer.analyze_tests(timeout=0.01)

        assert results == []


# =====================================================================
# TODO analysis
# =====================================================================


class TestTodoAnalysis:
    """Test TodoService integration."""

    @pytest.mark.asyncio
    async def test_picks_up_tagged_todos(self, tmp_path):
        """Create TodoService with tagged items, verify they become discoveries."""
        svc = TodoService(db_path=str(tmp_path / "todos.db"))
        svc.create(title="Fix auth bug", tags=["night-agent"], priority="high")
        svc.create(title="Improve logging", tags=["system-improvement"], priority="medium")

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
            todo_service=svc,
        )
        results = await analyzer.analyze_todos()

        assert len(results) == 2
        assert all(d.discovery_type == DiscoveryType.MANUAL_TODO for d in results)
        titles = {d.title for d in results}
        assert "Todo: Fix auth bug" in titles
        assert "Todo: Improve logging" in titles

    @pytest.mark.asyncio
    async def test_respects_custom_tags(self, tmp_path):
        """Only items with requested tags should appear."""
        svc = TodoService(db_path=str(tmp_path / "todos.db"))
        svc.create(title="Tagged right", tags=["custom-tag"], priority="low")
        svc.create(title="Tagged wrong", tags=["other-tag"], priority="low")

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
            todo_service=svc,
        )
        results = await analyzer.analyze_todos(tags=["custom-tag"])

        assert len(results) == 1
        assert results[0].title == "Todo: Tagged right"

    @pytest.mark.asyncio
    async def test_ignores_done_todos(self, tmp_path):
        """Completed todos should not appear."""
        svc = TodoService(db_path=str(tmp_path / "todos.db"))
        item = svc.create(title="Already done", tags=["night-agent"])
        svc.complete(item.id)

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
            todo_service=svc,
        )
        results = await analyzer.analyze_todos()

        assert results == []

    @pytest.mark.asyncio
    async def test_no_todo_service_returns_empty(self, tmp_path):
        """When todo_service is None, return empty."""
        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
            todo_service=None,
        )
        results = await analyzer.analyze_todos()

        assert results == []

    @pytest.mark.asyncio
    async def test_preserves_todo_id(self, tmp_path):
        """Discovery should carry the original todo item ID."""
        svc = TodoService(db_path=str(tmp_path / "todos.db"))
        item = svc.create(title="Track me", tags=["night-agent"])

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
            todo_service=svc,
        )
        results = await analyzer.analyze_todos()

        assert len(results) == 1
        assert results[0].todo_id == item.id


# =====================================================================
# Code quality analysis
# =====================================================================


class TestCodeQualityAnalysis:
    """Test AST-based code quality checks."""

    @pytest.mark.asyncio
    async def test_detects_undocumented_public_methods(self, tmp_path):
        """Create a .py file with undocumented public methods, verify detection."""
        agents_dir = tmp_path / "jarvis" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "__init__.py").touch()

        bad_file = agents_dir / "bad_agent.py"
        bad_file.write_text(
            'class BadAgent:\n'
            '    def do_thing(self): pass\n'
            '    def do_other(self): pass\n'
            '    def do_more(self): pass\n'
        )

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
        )
        results = await analyzer.analyze_code_quality()

        assert len(results) == 1
        assert results[0].discovery_type == DiscoveryType.CODE_QUALITY
        assert results[0].priority == "low"
        assert "bad_agent.py" in results[0].relevant_files[0]
        assert "do_thing" in results[0].source_detail
        assert "do_other" in results[0].source_detail
        assert "do_more" in results[0].source_detail

    @pytest.mark.asyncio
    async def test_ignores_private_methods(self, tmp_path):
        """Private methods (starting with _) should not be flagged."""
        services_dir = tmp_path / "jarvis" / "services"
        services_dir.mkdir(parents=True)

        ok_file = services_dir / "ok_service.py"
        ok_file.write_text(
            'class OkService:\n'
            '    def _private_one(self): pass\n'
            '    def _private_two(self): pass\n'
            '    def _private_three(self): pass\n'
            '    def public_one(self):\n'
            '        """Documented."""\n'
        )

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
        )
        results = await analyzer.analyze_code_quality()

        assert results == []

    @pytest.mark.asyncio
    async def test_threshold_requires_three(self, tmp_path):
        """Fewer than 3 undocumented public methods should not trigger."""
        agents_dir = tmp_path / "jarvis" / "agents"
        agents_dir.mkdir(parents=True)

        ok_file = agents_dir / "ok_agent.py"
        ok_file.write_text(
            'class OkAgent:\n'
            '    def method_one(self): pass\n'
            '    def method_two(self): pass\n'
        )

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
        )
        results = await analyzer.analyze_code_quality()

        assert results == []

    @pytest.mark.asyncio
    async def test_documented_methods_excluded(self, tmp_path):
        """Methods with docstrings should not count as undocumented."""
        agents_dir = tmp_path / "jarvis" / "agents"
        agents_dir.mkdir(parents=True)

        good_file = agents_dir / "good_agent.py"
        good_file.write_text(
            'class GoodAgent:\n'
            '    def alpha(self):\n'
            '        """Has a docstring."""\n'
            '    def beta(self):\n'
            '        """Also documented."""\n'
            '    def gamma(self):\n'
            '        """Documented too."""\n'
        )

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
        )
        results = await analyzer.analyze_code_quality()

        assert results == []

    @pytest.mark.asyncio
    async def test_scans_both_agents_and_services(self, tmp_path):
        """Should scan both jarvis/agents and jarvis/services."""
        for subdir in ("agents", "services"):
            d = tmp_path / "jarvis" / subdir
            d.mkdir(parents=True)
            (d / "undoc.py").write_text(
                f'class Undoc{subdir.title()}:\n'
                '    def a(self): pass\n'
                '    def b(self): pass\n'
                '    def c(self): pass\n'
            )

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
        )
        results = await analyzer.analyze_code_quality()

        assert len(results) == 2


# =====================================================================
# Full analysis (combined)
# =====================================================================


class TestFullAnalysis:
    """Test the combined run_full_analysis."""

    @pytest.mark.asyncio
    async def test_combines_all_analyzers(self, tmp_path, monkeypatch):
        """Verify run_full_analysis merges results from all analyzers."""
        # Set up log db with an error
        db_path = str(tmp_path / "logs.db")
        conn = _create_log_db(db_path)
        _insert_log(conn, "ERROR", "some_error", "details")
        conn.close()

        # Set up todo service with a tagged item
        svc = TodoService(db_path=str(tmp_path / "todos.db"))
        svc.create(title="Fix thing", tags=["night-agent"])

        # Mock pytest to return a failure
        async def mock_subprocess(*args, **kwargs):
            class FakeProcess:
                returncode = 1

                async def communicate(self):
                    stdout = (
                        b"FAILED tests/test_x.py::TestX::test_y"
                        b" - AssertionError\n1 failed\n"
                    )
                    return stdout, b""

            return FakeProcess()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        # Set up code quality target
        agents_dir = tmp_path / "jarvis" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "ugly.py").write_text(
            'class Ugly:\n'
            '    def a(self): pass\n'
            '    def b(self): pass\n'
            '    def c(self): pass\n'
        )

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=db_path,
            todo_service=svc,
        )
        results = await analyzer.run_full_analysis()

        types_found = {d.discovery_type for d in results}
        assert DiscoveryType.LOG_ERROR in types_found
        assert DiscoveryType.TEST_FAILURE in types_found
        assert DiscoveryType.MANUAL_TODO in types_found
        assert DiscoveryType.CODE_QUALITY in types_found

    @pytest.mark.asyncio
    async def test_deduplicates_by_title(self, tmp_path, monkeypatch):
        """Same title from different analyzers should be deduplicated."""
        # Create an analyzer with custom methods that produce duplicates
        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=str(tmp_path / "logs.db"),
        )

        dup = Discovery(
            discovery_type=DiscoveryType.LOG_ERROR,
            title="Duplicate title",
            description="First",
            priority="high",
        )
        dup2 = Discovery(
            discovery_type=DiscoveryType.CODE_QUALITY,
            title="Duplicate title",
            description="Second",
            priority="low",
        )

        # Patch individual analyzers to return overlapping titles
        async def fake_logs(*a, **kw):
            return [dup]

        async def fake_tests(*a, **kw):
            return []

        async def fake_todos(*a, **kw):
            return [dup2]

        async def fake_code(*a, **kw):
            return []

        monkeypatch.setattr(analyzer, "analyze_logs", fake_logs)
        monkeypatch.setattr(analyzer, "analyze_tests", fake_tests)
        monkeypatch.setattr(analyzer, "analyze_todos", fake_todos)
        monkeypatch.setattr(analyzer, "analyze_code_quality", fake_code)

        results = await analyzer.run_full_analysis()

        assert len(results) == 1
        assert results[0].title == "Duplicate title"
        # First occurrence wins
        assert results[0].discovery_type == DiscoveryType.LOG_ERROR

    @pytest.mark.asyncio
    async def test_resilient_to_analyzer_failure(self, tmp_path, monkeypatch):
        """If one analyzer raises, others still run."""
        db_path = str(tmp_path / "logs.db")
        conn = _create_log_db(db_path)
        _insert_log(conn, "ERROR", "still_found", "should appear")
        conn.close()

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=db_path,
        )

        # Make test analyzer blow up
        async def broken_tests(*a, **kw):
            raise RuntimeError("Boom")

        monkeypatch.setattr(analyzer, "analyze_tests", broken_tests)

        # Mock subprocess so code quality doesn't actually run pytest
        async def mock_subprocess(*args, **kwargs):
            class FakeProcess:
                returncode = 0

                async def communicate(self):
                    return b"0 passed\n", b""

            return FakeProcess()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        results = await analyzer.run_full_analysis()

        # Log analysis should still produce results
        assert any(d.title == "Log error: still_found" for d in results)


# =====================================================================
# Context enrichment
# =====================================================================


class TestContextEnrichment:
    """Test code_context and function_scope population."""

    @pytest.mark.asyncio
    async def test_unused_import_has_code_context(self, tmp_path):
        """Unused import discoveries should include surrounding code."""
        services_dir = tmp_path / "jarvis" / "services"
        services_dir.mkdir(parents=True)

        bad_file = services_dir / "ctx_service.py"
        bad_file.write_text(
            'import os\n'
            'import sys\n'
            '\n'
            'def hello():\n'
            '    return sys.platform\n'
        )

        analyzer = _make_analyzer(tmp_path)
        results = await analyzer.analyze_unused_imports()

        assert len(results) == 1
        assert results[0].code_context != ""
        assert "import os" in results[0].code_context

    @pytest.mark.asyncio
    async def test_exception_antipattern_has_function_scope(self, tmp_path):
        """Exception antipattern in a function should report enclosing scope."""
        services_dir = tmp_path / "jarvis" / "services"
        services_dir.mkdir(parents=True)

        bad_file = services_dir / "scoped.py"
        bad_file.write_text(
            'class MyService:\n'
            '    def risky_method(self):\n'
            '        try:\n'
            '            do_thing()\n'
            '        except:\n'
            '            pass\n'
        )

        analyzer = _make_analyzer(tmp_path)
        results = await analyzer.analyze_exception_antipatterns()

        assert len(results) == 1
        assert results[0].function_scope == "risky_method"
        assert results[0].code_context != ""

    @pytest.mark.asyncio
    async def test_to_dict_from_dict_roundtrip_new_fields(self):
        """New fields should survive serialization round-trip."""
        d = Discovery(
            discovery_type=DiscoveryType.UNUSED_IMPORT,
            title="Test",
            description="Test desc",
            priority="medium",
            code_context=">>> 1 | import os",
            function_scope="my_func",
        )
        data = d.to_dict()
        assert data["code_context"] == ">>> 1 | import os"
        assert data["function_scope"] == "my_func"

        restored = Discovery.from_dict(data)
        assert restored.code_context == ">>> 1 | import os"
        assert restored.function_scope == "my_func"

    @pytest.mark.asyncio
    async def test_from_dict_backward_compatible(self):
        """from_dict should handle missing new fields (old data)."""
        old_data = {
            "discovery_type": "unused_import",
            "title": "Old discovery",
            "description": "From before the upgrade",
            "priority": "medium",
        }
        d = Discovery.from_dict(old_data)
        assert d.code_context == ""
        assert d.function_scope == ""

    @pytest.mark.asyncio
    async def test_log_analyzer_leaves_context_empty(self, tmp_path):
        """Non-code analyzers should leave code_context and function_scope empty."""
        db_path = str(tmp_path / "logs.db")
        conn = _create_log_db(db_path)
        _insert_log(conn, "ERROR", "test_action", "details")
        conn.close()

        analyzer = SystemAnalyzer(
            project_root=str(tmp_path),
            log_db_path=db_path,
        )
        results = await analyzer.analyze_logs()

        assert len(results) == 1
        assert results[0].code_context == ""
        assert results[0].function_scope == ""


class TestExtractContext:
    """Test the _extract_context static helper."""

    def test_basic_context(self):
        source = "\n".join(f"line {i}" for i in range(1, 21))
        ctx = SystemAnalyzer._extract_context(source, 10, radius=3)
        assert ">>> " in ctx  # marker on target line
        assert "line 10" in ctx
        assert "line 7" in ctx
        assert "line 13" in ctx

    def test_near_start(self):
        source = "\n".join(f"line {i}" for i in range(1, 6))
        ctx = SystemAnalyzer._extract_context(source, 1, radius=3)
        assert "line 1" in ctx

    def test_near_end(self):
        source = "\n".join(f"line {i}" for i in range(1, 6))
        ctx = SystemAnalyzer._extract_context(source, 5, radius=3)
        assert "line 5" in ctx


class TestFindEnclosingScope:
    """Test the _find_enclosing_scope static helper."""

    def test_finds_function(self):
        source = "def foo():\n    x = 1\n    y = 2\n"
        tree = ast.parse(source)
        assert SystemAnalyzer._find_enclosing_scope(tree, 2) == "foo"

    def test_finds_class(self):
        source = "class Bar:\n    x = 1\n"
        tree = ast.parse(source)
        assert SystemAnalyzer._find_enclosing_scope(tree, 2) == "Bar"

    def test_finds_inner_function(self):
        source = "class Bar:\n    def baz(self):\n        x = 1\n"
        tree = ast.parse(source)
        assert SystemAnalyzer._find_enclosing_scope(tree, 3) == "baz"

    def test_top_level_returns_empty(self):
        source = "x = 1\ny = 2\n"
        tree = ast.parse(source)
        assert SystemAnalyzer._find_enclosing_scope(tree, 1) == ""
