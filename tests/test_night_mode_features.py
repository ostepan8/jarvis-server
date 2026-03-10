"""Tests for resumable night mode: NightCycleState, NightModePrinter, cancellation, idle detection."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone, timedelta
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.services.self_improvement_service import (
    NightCycleState,
    SelfImprovementService,
)
from jarvis.io.night_display import NightModePrinter


# ---------------------------------------------------------------------------
# NightCycleState — persistence, resume, stale detection
# ---------------------------------------------------------------------------


class TestNightCycleState:
    """State file round-trips, staleness, corruption, and atomic writes."""

    def _make_state(
        self,
        cycle_id: str = "2026-03-10T03:00:00+00:00",
        started_at: str | None = None,
        status: str = "in_progress",
        discoveries: list[dict] | None = None,
        completed_results: list[dict] | None = None,
        current_task_index: int = 0,
        skipped_count: int = 0,
    ) -> NightCycleState:
        return NightCycleState(
            cycle_id=cycle_id,
            started_at=started_at or datetime.now(timezone.utc).isoformat(),
            status=status,
            discoveries=discoveries if discoveries is not None else [
                {"title": "fix test_add", "discovery_type": "test_failure",
                 "description": "test fails", "priority": "high",
                 "relevant_files": ["calc.py"], "todo_id": None,
                 "source_detail": None}
            ],
            completed_results=completed_results if completed_results is not None else [],
            current_task_index=current_task_index,
            skipped_count=skipped_count,
        )

    def test_save_and_load_round_trip(self, tmp_path):
        state = self._make_state()
        with patch.object(NightCycleState, "STATE_FILE", tmp_path / "night_state.json"):
            state.save()
            loaded = NightCycleState.load()
            assert loaded is not None
            assert loaded.cycle_id == state.cycle_id
            assert loaded.status == "in_progress"
            assert loaded.current_task_index == 0
            assert len(loaded.discoveries) == 1

    def test_load_returns_none_when_missing(self, tmp_path):
        with patch.object(NightCycleState, "STATE_FILE", tmp_path / "nope.json"):
            assert NightCycleState.load() is None

    def test_load_returns_none_on_corrupt_json(self, tmp_path):
        bad_file = tmp_path / "night_state.json"
        bad_file.write_text("not json{{{")
        with patch.object(NightCycleState, "STATE_FILE", bad_file):
            assert NightCycleState.load() is None

    def test_load_returns_none_on_missing_keys(self, tmp_path):
        bad_file = tmp_path / "night_state.json"
        bad_file.write_text(json.dumps({"cycle_id": "x"}))
        with patch.object(NightCycleState, "STATE_FILE", bad_file):
            assert NightCycleState.load() is None

    def test_stale_state_returns_none_and_cleans_up(self, tmp_path):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        state = self._make_state(started_at=old_time)
        state_file = tmp_path / "night_state.json"
        with patch.object(NightCycleState, "STATE_FILE", state_file):
            state.save()
            assert state_file.exists()
            loaded = NightCycleState.load()
            assert loaded is None
            assert not state_file.exists()  # clear() was called

    def test_clear_removes_file(self, tmp_path):
        state = self._make_state()
        state_file = tmp_path / "night_state.json"
        with patch.object(NightCycleState, "STATE_FILE", state_file):
            state.save()
            assert state_file.exists()
            NightCycleState.clear()
            assert not state_file.exists()

    def test_clear_noop_when_no_file(self, tmp_path):
        with patch.object(NightCycleState, "STATE_FILE", tmp_path / "nope.json"):
            NightCycleState.clear()  # Should not raise

    def test_is_stale_false_for_recent(self):
        state = self._make_state(started_at=datetime.now(timezone.utc).isoformat())
        assert not state.is_stale()

    def test_is_stale_true_for_old(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        state = self._make_state(started_at=old)
        assert state.is_stale()

    def test_is_stale_true_for_garbage_timestamp(self):
        state = self._make_state(started_at="not-a-date")
        assert state.is_stale()

    def test_atomic_write_leaves_no_tmp_on_success(self, tmp_path):
        state = self._make_state()
        with patch.object(NightCycleState, "STATE_FILE", tmp_path / "night_state.json"):
            state.save()
            assert not (tmp_path / "night_state.tmp").exists()
            assert (tmp_path / "night_state.json").exists()

    def test_paused_state_preserves_completed_results(self, tmp_path):
        state = self._make_state(
            status="paused",
            current_task_index=2,
            completed_results=[
                {"task_title": "fix A", "discovery_type": "test_failure",
                 "success": True, "files_changed": 1, "test_passed": True,
                 "merged": False, "error_message": "", "duration_seconds": 5.0,
                 "todo_id": None, "pr_url": "https://pr/1", "branch_name": "night-fix-a"},
            ],
        )
        with patch.object(NightCycleState, "STATE_FILE", tmp_path / "night_state.json"):
            state.save()
            loaded = NightCycleState.load()
            assert loaded is not None
            assert loaded.status == "paused"
            assert loaded.current_task_index == 2
            assert len(loaded.completed_results) == 1
            assert loaded.completed_results[0]["pr_url"] == "https://pr/1"


# ---------------------------------------------------------------------------
# NightModePrinter — terminal output formatting
# ---------------------------------------------------------------------------


class TestNightModePrinter:
    """Verify printer output is correct, terse, and exclamation-free."""

    def setup_method(self):
        self.printer = NightModePrinter()
        self.captured = StringIO()

    def _capture(self, method, *args, **kwargs):
        with patch("sys.stdout", self.captured):
            method(*args, **kwargs)
        return self.captured.getvalue()

    def test_print_entering_contains_night_prefix(self):
        output = self._capture(self.printer.print_entering)
        # Strip ANSI codes for content check
        plain = output.replace("\033[35m", "").replace("\033[0m", "").replace("\033[36m", "")
        assert "[night]" in plain
        assert "Entering night mode" in plain
        assert "!" not in plain  # Canary rule

    def test_print_waking_contains_back_online(self):
        output = self._capture(self.printer.print_waking)
        plain = output.replace("\033[35m", "").replace("\033[0m", "").replace("\033[36m", "")
        assert "Back online" in plain
        assert "!" not in plain

    def test_print_waiting_shows_instruction(self):
        output = self._capture(self.printer.print_waiting)
        plain = output.replace("\033[35m", "").replace("\033[0m", "").replace("\033[37m", "")
        assert "Press Enter" in plain or "wake" in plain.lower()

    def test_on_event_basic_message(self):
        output = self._capture(self.printer.on_event, "task_start", "Working on: fix test", {})
        plain = output.replace("\033[35m", "").replace("\033[0m", "").replace("\033[36m", "")
        assert "[night]" in plain
        assert "Working on: fix test" in plain

    def test_on_event_task_success_appends_pr_url(self):
        output = self._capture(
            self.printer.on_event, "task_success", "Done.",
            {"pr_url": "https://github.com/repo/pull/42"}
        )
        assert "https://github.com/repo/pull/42" in output

    def test_on_event_task_success_no_pr_url(self):
        output = self._capture(self.printer.on_event, "task_success", "Done.", {})
        assert "PR:" not in output

    def test_on_event_includes_timestamp(self):
        output = self._capture(self.printer.on_event, "cycle_start", "Scanning...", {})
        # Should contain HH:MM:SS pattern
        import re
        plain = output.replace("\033[35m", "").replace("\033[0m", "").replace("\033[36m", "")
        assert re.search(r"\d{2}:\d{2}:\d{2}", plain)

    def test_no_exclamation_marks_in_any_output(self):
        """The canary rule — zero exclamation marks in all output."""
        with patch("sys.stdout", self.captured):
            self.printer.print_entering()
            self.printer.print_waking()
            self.printer.print_waiting()
            self.printer.on_event("cycle_start", "Scanning...", {})
            self.printer.on_event("task_success", "Done.", {"pr_url": "https://x"})
            self.printer.on_event("cycle_complete", "Cycle complete: 3/5 succeeded", {})
        all_output = self.captured.getvalue()
        assert "!" not in all_output


# ---------------------------------------------------------------------------
# Cancellation — pause_cycle saves state
# ---------------------------------------------------------------------------


class TestCancellationHandling:
    """Verify CancelledError triggers state persistence."""

    def test_pause_cycle_marks_state_as_paused(self, tmp_path):
        state = NightCycleState(
            cycle_id="test",
            started_at=datetime.now(timezone.utc).isoformat(),
            status="in_progress",
            discoveries=[],
            completed_results=[],
            current_task_index=2,
            skipped_count=0,
        )
        state_file = tmp_path / "night_state.json"
        with patch.object(NightCycleState, "STATE_FILE", state_file):
            state.save()

            service = SelfImprovementService.__new__(SelfImprovementService)
            service._logger = MagicMock()
            service.pause_cycle()

            loaded = NightCycleState.load()
            assert loaded is not None
            assert loaded.status == "paused"

    def test_pause_cycle_emits_callback(self, tmp_path):
        state = NightCycleState(
            cycle_id="test",
            started_at=datetime.now(timezone.utc).isoformat(),
            status="in_progress",
            discoveries=[{"a": 1}, {"b": 2}, {"c": 3}],
            completed_results=[],
            current_task_index=1,
            skipped_count=0,
        )
        state_file = tmp_path / "night_state.json"
        with patch.object(NightCycleState, "STATE_FILE", state_file):
            state.save()

            callback = MagicMock()
            service = SelfImprovementService.__new__(SelfImprovementService)
            service._logger = MagicMock()
            service.pause_cycle(progress_callback=callback)

            callback.assert_called_once()
            args = callback.call_args[0]
            assert args[0] == "cycle_paused"
            assert "2 tasks remaining" in args[1]

    def test_pause_cycle_noop_when_no_state(self, tmp_path):
        with patch.object(NightCycleState, "STATE_FILE", tmp_path / "nope.json"):
            service = SelfImprovementService.__new__(SelfImprovementService)
            service._logger = MagicMock()
            service.pause_cycle()  # Should not raise

    def test_pause_cycle_noop_when_already_paused(self, tmp_path):
        state = NightCycleState(
            cycle_id="test",
            started_at=datetime.now(timezone.utc).isoformat(),
            status="paused",
            discoveries=[],
            completed_results=[],
            current_task_index=0,
            skipped_count=0,
        )
        state_file = tmp_path / "night_state.json"
        with patch.object(NightCycleState, "STATE_FILE", state_file):
            state.save()

            callback = MagicMock()
            service = SelfImprovementService.__new__(SelfImprovementService)
            service._logger = MagicMock()
            service.pause_cycle(progress_callback=callback)
            callback.assert_not_called()


# ---------------------------------------------------------------------------
# SelfImprovementAgent — CancelledError triggers pause
# ---------------------------------------------------------------------------


class TestAgentCancellation:
    """Verify the agent catches CancelledError and pauses."""

    @pytest.mark.asyncio
    async def test_cancelled_error_calls_pause_cycle(self):
        from jarvis.night_agents.self_improvement_agent import SelfImprovementAgent

        agent = SelfImprovementAgent.__new__(SelfImprovementAgent)
        agent.logger = MagicMock()
        agent._run_interval = 1
        agent._progress_callback = None

        mock_service = MagicMock()
        mock_service.pause_cycle = MagicMock()
        mock_service.run_improvement_cycle = AsyncMock(side_effect=asyncio.CancelledError)
        agent._service = mock_service

        with pytest.raises(asyncio.CancelledError):
            await agent._run_cycle()

        # The CancelledError propagates from run_improvement_cycle,
        # but the agent catches it in _periodic_improvement.
        # Let's test that layer directly.
        mock_service.run_improvement_cycle.side_effect = asyncio.CancelledError

        async def run_one_iteration():
            try:
                await agent._periodic_improvement()
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(run_one_iteration())
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.01)

        mock_service.pause_cycle.assert_called()


# ---------------------------------------------------------------------------
# Progress callback event sequence
# ---------------------------------------------------------------------------


class TestProgressCallbackSequence:
    """Verify the service emits the right events in the right order."""

    @pytest.mark.asyncio
    async def test_fresh_cycle_emits_expected_events(self, tmp_path):
        events = []

        def callback(event_type, message, _data):
            events.append((event_type, message))

        service = SelfImprovementService.__new__(SelfImprovementService)
        service._logger = MagicMock()
        service._todo_service = None
        service._use_prs = False

        # Mock the runner and analyzer
        service._runner = MagicMock()
        service._runner.check_available = AsyncMock(return_value=True)
        service._runner.create_worktree = AsyncMock(return_value=("/tmp/wt", "branch"))
        service._runner.execute_task = AsyncMock(return_value=MagicMock(
            success=True, files_changed=1, stderr=""
        ))
        service._runner.run_tests = AsyncMock(return_value=MagicMock(success=True, stderr=""))
        service._runner.merge_to_main = AsyncMock(return_value=True)
        service._runner.cleanup_worktree = AsyncMock()

        service._analyzer = MagicMock()

        from jarvis.services.system_analyzer import Discovery, DiscoveryType
        mock_discovery = Discovery(
            discovery_type=DiscoveryType.TEST_FAILURE,
            title="fix test_add",
            description="test fails",
            priority="high",
            relevant_files=["calc.py"],
        )
        service._analyzer.run_full_analysis = AsyncMock(return_value=[mock_discovery])

        with patch.object(NightCycleState, "STATE_FILE", tmp_path / "night_state.json"):
            await service.run_improvement_cycle(progress_callback=callback)

        event_types = [e[0] for e in events]
        assert "cycle_start" in event_types
        assert "discovery_complete" in event_types
        assert "task_start" in event_types
        assert "task_success" in event_types
        assert "cycle_complete" in event_types

        # Order: start before discovery before task before complete
        assert event_types.index("cycle_start") < event_types.index("discovery_complete")
        assert event_types.index("discovery_complete") < event_types.index("task_start")
        assert event_types.index("task_start") < event_types.index("cycle_complete")

    @pytest.mark.asyncio
    async def test_resume_cycle_emits_cycle_resumed(self, tmp_path):
        events = []

        def callback(event_type, message, _data):
            events.append((event_type, message))

        from jarvis.services.system_analyzer import Discovery, DiscoveryType

        discovery = Discovery(
            discovery_type=DiscoveryType.TEST_FAILURE,
            title="fix test_add",
            description="test fails",
            priority="high",
            relevant_files=["calc.py"],
        )

        state = NightCycleState(
            cycle_id="test-resume",
            started_at=datetime.now(timezone.utc).isoformat(),
            status="paused",
            discoveries=[discovery.to_dict()],
            completed_results=[],
            current_task_index=0,
            skipped_count=0,
        )

        state_file = tmp_path / "night_state.json"
        with patch.object(NightCycleState, "STATE_FILE", state_file):
            state.save()

            service = SelfImprovementService.__new__(SelfImprovementService)
            service._logger = MagicMock()
            service._todo_service = None
            service._use_prs = False
            service._runner = MagicMock()
            service._runner.create_worktree = AsyncMock(return_value=("/tmp/wt", "branch"))
            service._runner.execute_task = AsyncMock(return_value=MagicMock(
                success=True, files_changed=1, stderr=""
            ))
            service._runner.run_tests = AsyncMock(return_value=MagicMock(success=True, stderr=""))
            service._runner.merge_to_main = AsyncMock(return_value=True)
            service._runner.cleanup_worktree = AsyncMock()

            service.REPORT_DIR = tmp_path / "reports"

            await service.run_improvement_cycle(progress_callback=callback)

        event_types = [e[0] for e in events]
        assert "cycle_resumed" in event_types
        assert "cycle_start" not in event_types  # Should NOT re-discover
