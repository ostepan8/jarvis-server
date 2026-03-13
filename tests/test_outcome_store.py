"""Tests for OutcomeStore — fix attempt history."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from jarvis.services.outcome_store import FixAttempt, OutcomeStore


def _make_attempt(**overrides) -> FixAttempt:
    defaults = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "discovery_type": "unused_import",
        "title": "Unused imports in foo.py",
        "file_pattern": "jarvis/services/foo.py",
        "diff_summary": "- import os",
        "success": True,
        "error_message": "",
        "triage_notes": "",
        "confidence_score": 7,
        "duration_seconds": 12.5,
    }
    defaults.update(overrides)
    return FixAttempt(**defaults)


class TestOutcomeStoreRecord:
    def test_record_and_retrieve(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        attempt = _make_attempt()
        row_id = store.record(attempt)
        assert row_id >= 1

        results = store.query_similar("unused_import", ["foo.py"])
        assert len(results) == 1
        assert results[0].title == "Unused imports in foo.py"
        assert results[0].success is True
        assert results[0].confidence_score == 7
        assert results[0].duration_seconds == 12.5
        assert results[0].id == row_id
        store.close()

    def test_multiple_records(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        for i in range(5):
            store.record(_make_attempt(title=f"Fix #{i}"))
        results = store.query_similar("unused_import", [], limit=10)
        assert len(results) == 5
        store.close()


class TestQuerySimilar:
    def test_filters_by_type(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        store.record(_make_attempt(discovery_type="unused_import"))
        store.record(_make_attempt(discovery_type="exception_antipattern"))

        results = store.query_similar("unused_import", [])
        assert len(results) == 1
        assert results[0].discovery_type == "unused_import"
        store.close()

    def test_filters_by_file_pattern(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        store.record(_make_attempt(file_pattern="jarvis/services/foo.py"))
        store.record(_make_attempt(file_pattern="jarvis/services/bar.py"))

        results = store.query_similar("unused_import", ["foo.py"])
        assert len(results) == 1
        assert "foo.py" in results[0].file_pattern
        store.close()

    def test_respects_limit(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        for i in range(10):
            store.record(_make_attempt(title=f"Fix #{i}"))

        results = store.query_similar("unused_import", [], limit=3)
        assert len(results) == 3
        store.close()


class TestSuccessRate:
    def test_mixed_results(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        store.record(_make_attempt(success=True))
        store.record(_make_attempt(success=True))
        store.record(_make_attempt(success=False))

        rate = store.success_rate("unused_import")
        assert abs(rate - 2/3) < 0.01
        store.close()

    def test_empty_returns_zero(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        rate = store.success_rate("unused_import")
        assert rate == 0.0
        store.close()

    def test_all_failures(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        store.record(_make_attempt(success=False))
        store.record(_make_attempt(success=False))

        rate = store.success_rate("unused_import")
        assert rate == 0.0
        store.close()

    def test_all_successes(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        store.record(_make_attempt(success=True))
        store.record(_make_attempt(success=True))

        rate = store.success_rate("unused_import")
        assert rate == 1.0
        store.close()


class TestRecentFailures:
    def test_returns_only_failures(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        store.record(_make_attempt(success=True, title="Win"))
        store.record(_make_attempt(success=False, title="Loss"))

        failures = store.recent_failures()
        assert len(failures) == 1
        assert failures[0].title == "Loss"
        store.close()

    def test_ordering_most_recent_first(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        store.record(_make_attempt(success=False, title="Old", timestamp="2026-01-01T00:00:00"))
        store.record(_make_attempt(success=False, title="New", timestamp="2026-03-01T00:00:00"))

        failures = store.recent_failures()
        assert failures[0].title == "New"
        assert failures[1].title == "Old"
        store.close()

    def test_respects_limit(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        for i in range(10):
            store.record(_make_attempt(success=False, title=f"Fail #{i}"))

        failures = store.recent_failures(n=3)
        assert len(failures) == 3
        store.close()


class TestCloseIdempotent:
    def test_double_close(self, tmp_path):
        store = OutcomeStore(db_path=str(tmp_path / "test.db"))
        store.close()
        store.close()  # should not raise
