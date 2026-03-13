"""Tests for DiscoveryIntelligence — LLM-powered triage, clustering, and verification."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from jarvis.ai_clients.base import BaseAIClient
from jarvis.services.discovery_intelligence import (
    DiscoveryCluster,
    DiscoveryIntelligence,
    EnrichedDiscovery,
    TriageResult,
    VerificationResult,
)
from jarvis.services.outcome_store import FixAttempt, OutcomeStore
from jarvis.services.system_analyzer import Discovery, DiscoveryType


# ---------------------------------------------------------------------------
# Mock AI client
# ---------------------------------------------------------------------------


class MockAIClient(BaseAIClient):
    """AI client that returns scripted responses for testing."""

    def __init__(self, responses: list[str] | None = None):
        self._responses = list(responses or [])
        self._call_index = 0
        self.call_log: list[str] = []  # record prompts for assertion

    def set_responses(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_index = 0

    async def strong_chat(self, messages: List[Dict[str, Any]], tools=None) -> Tuple[Any, Any]:
        return await self.weak_chat(messages, tools)

    async def weak_chat(self, messages: List[Dict[str, Any]], tools=None) -> Tuple[Any, Any]:
        # Record the user prompt
        for msg in messages:
            if msg.get("role") == "user":
                self.call_log.append(msg["content"])

        if self._call_index < len(self._responses):
            text = self._responses[self._call_index]
            self._call_index += 1
        else:
            text = "{}"

        response = type("Response", (), {"content": text})()
        return response, None


class ErrorAIClient(BaseAIClient):
    """AI client that always raises."""

    async def strong_chat(self, messages, tools=None):
        raise RuntimeError("LLM unavailable")

    async def weak_chat(self, messages, tools=None):
        raise RuntimeError("LLM unavailable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_discovery(**overrides) -> Discovery:
    defaults = dict(
        discovery_type=DiscoveryType.UNUSED_IMPORT,
        title="Unused imports in jarvis/services/foo.py",
        description="Found 1 unused import: os (line 1)",
        priority="medium",
        relevant_files=["jarvis/services/foo.py"],
        source_detail="os (line 1)",
        code_context=">>>    1 | import os\n       2 | import sys",
        function_scope="",
    )
    defaults.update(overrides)
    return Discovery(**defaults)


def _make_store(tmp_path) -> OutcomeStore:
    return OutcomeStore(db_path=str(tmp_path / "test_outcomes.db"))


# =====================================================================
# Triage tests
# =====================================================================


class TestTriage:
    @pytest.mark.asyncio
    async def test_accepts_real_issue(self, tmp_path):
        """LLM says issue is real — triage should pass it through."""
        client = MockAIClient([
            json.dumps({
                "is_real": True,
                "confidence": 8,
                "fix_approach": "Remove the unused import",
                "complexity": "trivial",
                "reasoning": "os is clearly unused",
            })
        ])
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        result = await intel.triage(_make_discovery())

        assert result.is_real is True
        assert result.confidence_score == 8
        assert result.confidence_label == "high"
        assert result.complexity == "trivial"
        assert "unused" in result.reasoning.lower()
        store.close()

    @pytest.mark.asyncio
    async def test_rejects_false_positive(self, tmp_path):
        """LLM identifies a false positive — triage should reject."""
        client = MockAIClient([
            json.dumps({
                "is_real": False,
                "confidence": 2,
                "fix_approach": "",
                "complexity": "trivial",
                "reasoning": "This import is used via __all__",
            })
        ])
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        result = await intel.triage(_make_discovery())

        assert result.is_real is False
        assert result.confidence_score == 2
        assert result.confidence_label == "low"
        store.close()

    @pytest.mark.asyncio
    async def test_confidence_label_computation(self, tmp_path):
        """Verify label boundaries: 1-3=low, 4-7=medium, 8-10=high."""
        assert TriageResult.compute_label(1) == "low"
        assert TriageResult.compute_label(3) == "low"
        assert TriageResult.compute_label(4) == "medium"
        assert TriageResult.compute_label(7) == "medium"
        assert TriageResult.compute_label(8) == "high"
        assert TriageResult.compute_label(10) == "high"

    @pytest.mark.asyncio
    async def test_garbage_json_fallback(self, tmp_path):
        """Unparseable LLM response falls back to conservative defaults."""
        client = MockAIClient(["this is not json at all"])
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        result = await intel.triage(_make_discovery())

        assert result.is_real is True  # conservative
        assert result.confidence_score == 5
        assert result.confidence_label == "medium"
        store.close()

    @pytest.mark.asyncio
    async def test_llm_error_fallback(self, tmp_path):
        """LLM call fails entirely — should fall back gracefully."""
        client = ErrorAIClient()
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        result = await intel.triage(_make_discovery())

        assert result.is_real is True
        assert result.confidence_score == 5
        store.close()

    @pytest.mark.asyncio
    async def test_prompt_includes_history(self, tmp_path):
        """Triage prompt should include success rate and past attempts."""
        store = _make_store(tmp_path)
        store.record(FixAttempt(
            timestamp="2026-03-01T00:00:00",
            discovery_type="unused_import",
            title="Old fix",
            file_pattern="jarvis/services/foo.py",
            diff_summary="- import os",
            success=False,
            error_message="Merge conflict",
            confidence_score=7,
        ))

        client = MockAIClient([
            json.dumps({"is_real": True, "confidence": 6, "fix_approach": "remove", "complexity": "trivial", "reasoning": "ok"})
        ])
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        await intel.triage(_make_discovery())

        # Check that the prompt sent to the LLM includes history info
        assert len(client.call_log) == 1
        prompt = client.call_log[0]
        assert "HISTORICAL SUCCESS RATE" in prompt
        assert "PAST ATTEMPTS" in prompt
        assert "Merge conflict" in prompt
        store.close()


# =====================================================================
# Cluster tests
# =====================================================================


class TestCluster:
    @pytest.mark.asyncio
    async def test_groups_related_discoveries(self, tmp_path):
        """LLM groups two related discoveries into one cluster."""
        d1 = _make_discovery(title="Unused import os in foo.py")
        d2 = _make_discovery(title="Unused import sys in foo.py")

        client = MockAIClient([
            json.dumps([
                {"title": "Clean up foo.py imports", "indices": [0, 1], "rationale": "Same file"}
            ])
        ])
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        clusters = await intel.cluster([d1, d2])

        assert len(clusters) == 1
        assert len(clusters[0].discoveries) == 2
        assert clusters[0].title == "Clean up foo.py imports"
        store.close()

    @pytest.mark.asyncio
    async def test_single_discovery_no_llm_call(self, tmp_path):
        """Single discovery should become a single-item cluster without LLM."""
        client = MockAIClient()
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        clusters = await intel.cluster([_make_discovery()])

        assert len(clusters) == 1
        assert len(clusters[0].discoveries) == 1
        assert len(client.call_log) == 0  # no LLM call
        store.close()

    @pytest.mark.asyncio
    async def test_garbage_json_returns_individual_clusters(self, tmp_path):
        """Unparseable response falls back to one cluster per discovery."""
        d1 = _make_discovery(title="A")
        d2 = _make_discovery(title="B")

        client = MockAIClient(["not json"])
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        clusters = await intel.cluster([d1, d2])

        assert len(clusters) == 2
        store.close()

    @pytest.mark.asyncio
    async def test_ungrouped_discoveries_become_singletons(self, tmp_path):
        """Discoveries not mentioned in LLM response become single clusters."""
        d1 = _make_discovery(title="A")
        d2 = _make_discovery(title="B")
        d3 = _make_discovery(title="C")

        client = MockAIClient([
            json.dumps([
                {"title": "AB cluster", "indices": [0, 1], "rationale": "related"}
            ])
        ])
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        clusters = await intel.cluster([d1, d2, d3])

        assert len(clusters) == 2  # one cluster of 2 + one singleton
        singleton = [c for c in clusters if len(c.discoveries) == 1]
        assert len(singleton) == 1
        assert singleton[0].discoveries[0].title == "C"
        store.close()


# =====================================================================
# Verification tests
# =====================================================================


class TestVerification:
    @pytest.mark.asyncio
    async def test_confirms_fix(self, tmp_path):
        """LLM confirms the fix addresses the issue."""
        client = MockAIClient([
            json.dumps({
                "issue_fixed": True,
                "unrelated_changes": False,
                "new_issues": [],
                "reasoning": "Import removed correctly",
            })
        ])
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        result = await intel.verify_fix(_make_discovery(), "- import os\n")

        assert result.issue_fixed is True
        assert result.unrelated_changes is False
        assert result.new_issues == []
        store.close()

    @pytest.mark.asyncio
    async def test_rejects_bad_fix(self, tmp_path):
        """LLM identifies that the fix didn't address the issue."""
        client = MockAIClient([
            json.dumps({
                "issue_fixed": False,
                "unrelated_changes": True,
                "new_issues": ["Removed a used import"],
                "reasoning": "os is actually used via os.path",
            })
        ])
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        result = await intel.verify_fix(_make_discovery(), "- import os\n")

        assert result.issue_fixed is False
        assert result.unrelated_changes is True
        assert "used import" in result.new_issues[0]
        store.close()

    @pytest.mark.asyncio
    async def test_garbage_json_fallback(self, tmp_path):
        """Unparseable response defaults to optimistic pass."""
        client = MockAIClient(["garbage"])
        store = _make_store(tmp_path)
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        result = await intel.verify_fix(_make_discovery(), "some diff")

        assert result.issue_fixed is True
        assert result.unrelated_changes is False
        store.close()


# =====================================================================
# Enrich context tests
# =====================================================================


class TestEnrichContext:
    @pytest.mark.asyncio
    async def test_assembles_enriched_discovery(self, tmp_path):
        """Enrichment should combine context, triage, and history."""
        store = _make_store(tmp_path)
        store.record(FixAttempt(
            timestamp="2026-03-01T00:00:00",
            discovery_type="unused_import",
            title="Past fix",
            file_pattern="jarvis/services/foo.py",
            diff_summary="diff",
            success=True,
            confidence_score=7,
        ))

        client = MockAIClient()
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        triage = TriageResult(
            is_real=True, confidence_score=8, confidence_label="high",
            fix_approach="Remove import", complexity="trivial",
            reasoning="Clearly unused",
        )

        enriched = await intel.enrich_context(_make_discovery(), triage)

        assert isinstance(enriched, EnrichedDiscovery)
        assert enriched.triage.confidence_score == 8
        assert len(enriched.similar_attempts) == 1
        assert "Remove import" in enriched.suggested_approach
        store.close()

    @pytest.mark.asyncio
    async def test_cluster_enrichment(self, tmp_path):
        """Enriching a cluster should use combined context."""
        store = _make_store(tmp_path)
        client = MockAIClient()
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        cluster = DiscoveryCluster(
            title="Import cleanup",
            discoveries=[_make_discovery(), _make_discovery(title="Second")],
            rationale="Same file",
            combined_files=["jarvis/services/foo.py"],
            combined_context="combined code here",
        )
        triage = TriageResult(
            is_real=True, confidence_score=7, confidence_label="medium",
            fix_approach="Clean imports", complexity="small", reasoning="ok",
        )

        enriched = await intel.enrich_context(cluster, triage)

        assert enriched.code_context == "combined code here"
        store.close()

    @pytest.mark.asyncio
    async def test_notes_past_failures(self, tmp_path):
        """Suggested approach should mention past failures."""
        store = _make_store(tmp_path)
        store.record(FixAttempt(
            timestamp="2026-03-01T00:00:00",
            discovery_type="unused_import",
            title="Failed fix",
            file_pattern="jarvis/services/foo.py",
            diff_summary="diff",
            success=False,
            error_message="Merge conflict on line 42",
            confidence_score=5,
        ))

        client = MockAIClient()
        intel = DiscoveryIntelligence(client, store, str(tmp_path))

        triage = TriageResult(
            is_real=True, confidence_score=7, confidence_label="medium",
            fix_approach="Remove import", complexity="trivial", reasoning="ok",
        )

        enriched = await intel.enrich_context(_make_discovery(), triage)

        assert "failed" in enriched.suggested_approach.lower()
        assert "Merge conflict" in enriched.suggested_approach
        store.close()
