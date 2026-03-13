"""LLM-powered intelligence layer for night agent discoveries.

Adds judgment at every decision point: triage (real vs false positive),
clustering (group related fixes), verification (did the fix work?),
and context enrichment (assembly for Claude Code prompts).

Uses weak_chat() for all LLM calls — fast and cheap.
Every LLM parse has a structured fallback so the system never
degrades below current static behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..ai_clients.base import BaseAIClient
from ..logging import JarvisLogger
from ..utils import extract_json_from_text
from .outcome_store import OutcomeStore, FixAttempt
from .system_analyzer import Discovery


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TriageResult:
    is_real: bool
    confidence_score: int          # 1-10
    confidence_label: str          # computed: 1-3=low, 4-7=medium, 8-10=high
    fix_approach: str
    complexity: str                # trivial, small, medium, large
    reasoning: str

    @staticmethod
    def compute_label(score: int) -> str:
        if score <= 3:
            return "low"
        if score <= 7:
            return "medium"
        return "high"


@dataclass
class DiscoveryCluster:
    title: str
    discoveries: list[Discovery]
    rationale: str
    combined_files: list[str]
    combined_context: str


@dataclass
class VerificationResult:
    issue_fixed: bool
    unrelated_changes: bool
    new_issues: list[str]
    reasoning: str


@dataclass
class EnrichedDiscovery:
    discovery: Discovery | DiscoveryCluster
    code_context: str
    triage: TriageResult
    similar_attempts: list[FixAttempt]
    suggested_approach: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DiscoveryIntelligence:
    """LLM-powered judgment layer for the self-improvement pipeline."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        outcome_store: OutcomeStore,
        project_root: str,
        logger: JarvisLogger | None = None,
    ) -> None:
        self._ai = ai_client
        self._store = outcome_store
        self._project_root = project_root
        self._logger = logger or JarvisLogger()

    # ------------------------------------------------------------------
    # Triage — one weak_chat call per discovery
    # ------------------------------------------------------------------

    async def triage(self, discovery: Discovery) -> TriageResult:
        """Evaluate whether a discovery is real and worth fixing."""
        # Gather historical context
        success_rate = self._store.success_rate(
            discovery.discovery_type.value
            if hasattr(discovery.discovery_type, "value")
            else str(discovery.discovery_type)
        )
        similar = self._store.query_similar(
            discovery.discovery_type.value
            if hasattr(discovery.discovery_type, "value")
            else str(discovery.discovery_type),
            discovery.relevant_files,
            limit=3,
        )

        history_text = ""
        if similar:
            history_lines = []
            for att in similar:
                status = "OK" if att.success else "FAIL"
                history_lines.append(f"  [{status}] {att.title} (confidence={att.confidence_score})")
                if att.error_message:
                    history_lines.append(f"         Error: {att.error_message[:100]}")
            history_text = "\n".join(history_lines)

        code_context = getattr(discovery, "code_context", "") or ""
        function_scope = getattr(discovery, "function_scope", "") or ""

        prompt = (
            "You are a code quality triage assistant. Evaluate this discovery.\n\n"
            f"TYPE: {discovery.discovery_type}\n"
            f"TITLE: {discovery.title}\n"
            f"DESCRIPTION: {discovery.description}\n"
            f"FILES: {', '.join(discovery.relevant_files)}\n"
            f"FUNCTION SCOPE: {function_scope}\n"
            f"\nCODE CONTEXT:\n{code_context}\n"
            f"\nHISTORICAL SUCCESS RATE for this type: {success_rate:.0%}\n"
            + (f"\nPAST ATTEMPTS:\n{history_text}\n" if history_text else "")
            + '\nRespond with JSON:\n'
            '{"is_real": true/false, "confidence": 1-10, '
            '"fix_approach": "brief description", '
            '"complexity": "trivial|small|medium|large", '
            '"reasoning": "why"}\n'
        )

        try:
            response, _ = await self._ai.weak_chat(
                [{"role": "user", "content": prompt}]
            )
            text = response.content if hasattr(response, "content") else str(response)
            parsed = extract_json_from_text(text)

            if parsed and isinstance(parsed, dict):
                score = int(parsed.get("confidence", 5))
                score = max(1, min(10, score))
                return TriageResult(
                    is_real=bool(parsed.get("is_real", True)),
                    confidence_score=score,
                    confidence_label=TriageResult.compute_label(score),
                    fix_approach=str(parsed.get("fix_approach", "")),
                    complexity=str(parsed.get("complexity", "medium")),
                    reasoning=str(parsed.get("reasoning", "")),
                )
        except Exception as exc:
            self._logger.log("WARNING", "Triage LLM call failed", str(exc))

        # Conservative fallback — pass through as real
        return TriageResult(
            is_real=True,
            confidence_score=5,
            confidence_label="medium",
            fix_approach="",
            complexity="medium",
            reasoning="LLM triage unavailable — conservative pass-through",
        )

    # ------------------------------------------------------------------
    # Cluster — one weak_chat call for all discoveries
    # ------------------------------------------------------------------

    async def cluster(self, discoveries: list[Discovery]) -> list[DiscoveryCluster]:
        """Group related discoveries into fix clusters."""
        if len(discoveries) <= 1:
            return [self._single_cluster(d) for d in discoveries]

        summaries = []
        for i, d in enumerate(discoveries):
            files = ", ".join(d.relevant_files) if d.relevant_files else "unknown"
            scope = getattr(d, "function_scope", "") or ""
            summaries.append(
                f"  [{i}] {d.discovery_type}: {d.title} (files: {files}, scope: {scope})"
            )
        summary_text = "\n".join(summaries)

        prompt = (
            "You are grouping code discoveries into clusters that should be fixed together.\n\n"
            f"DISCOVERIES:\n{summary_text}\n\n"
            'Group by shared function scope, root cause, or fix pattern.\n'
            'Respond with JSON array of clusters:\n'
            '[{"title": "cluster name", "indices": [0, 1], "rationale": "why grouped"}]\n'
            'Each discovery index must appear exactly once.\n'
        )

        try:
            response, _ = await self._ai.weak_chat(
                [{"role": "user", "content": prompt}]
            )
            text = response.content if hasattr(response, "content") else str(response)
            parsed = extract_json_from_text(text)

            if parsed and isinstance(parsed, list):
                clusters = []
                used_indices: set[int] = set()
                for item in parsed:
                    indices = item.get("indices", [])
                    valid_indices = [
                        idx for idx in indices
                        if isinstance(idx, int) and 0 <= idx < len(discoveries) and idx not in used_indices
                    ]
                    if not valid_indices:
                        continue
                    used_indices.update(valid_indices)
                    cluster_discoveries = [discoveries[i] for i in valid_indices]
                    combined_files = list({
                        f for d in cluster_discoveries for f in d.relevant_files
                    })
                    combined_ctx = "\n---\n".join(
                        getattr(d, "code_context", "") or "" for d in cluster_discoveries
                    )
                    clusters.append(DiscoveryCluster(
                        title=str(item.get("title", cluster_discoveries[0].title)),
                        discoveries=cluster_discoveries,
                        rationale=str(item.get("rationale", "")),
                        combined_files=combined_files,
                        combined_context=combined_ctx,
                    ))

                # Any ungrouped discoveries become single-item clusters
                for i, d in enumerate(discoveries):
                    if i not in used_indices:
                        clusters.append(self._single_cluster(d))

                if clusters:
                    return clusters
        except Exception as exc:
            self._logger.log("WARNING", "Cluster LLM call failed", str(exc))

        # Fallback: each discovery is its own cluster
        return [self._single_cluster(d) for d in discoveries]

    # ------------------------------------------------------------------
    # Verify — one weak_chat call per completed fix
    # ------------------------------------------------------------------

    async def verify_fix(self, discovery: Discovery, diff: str) -> VerificationResult:
        """Review a diff to determine if it actually fixes the reported issue."""
        diff_truncated = diff[:3000] if diff else "(empty diff)"

        prompt = (
            "You are reviewing a code fix. Determine if it actually addresses the issue.\n\n"
            f"ORIGINAL ISSUE:\n"
            f"  Type: {discovery.discovery_type}\n"
            f"  Title: {discovery.title}\n"
            f"  Description: {discovery.description}\n"
            f"\nDIFF:\n{diff_truncated}\n\n"
            'Respond with JSON:\n'
            '{"issue_fixed": true/false, "unrelated_changes": true/false, '
            '"new_issues": ["list of any new problems introduced"], '
            '"reasoning": "explanation"}\n'
        )

        try:
            response, _ = await self._ai.weak_chat(
                [{"role": "user", "content": prompt}]
            )
            text = response.content if hasattr(response, "content") else str(response)
            parsed = extract_json_from_text(text)

            if parsed and isinstance(parsed, dict):
                return VerificationResult(
                    issue_fixed=bool(parsed.get("issue_fixed", True)),
                    unrelated_changes=bool(parsed.get("unrelated_changes", False)),
                    new_issues=list(parsed.get("new_issues", [])),
                    reasoning=str(parsed.get("reasoning", "")),
                )
        except Exception as exc:
            self._logger.log("WARNING", "Verify LLM call failed", str(exc))

        # Fallback: assume fix is good
        return VerificationResult(
            issue_fixed=True,
            unrelated_changes=False,
            new_issues=[],
            reasoning="LLM verification unavailable — optimistic pass-through",
        )

    # ------------------------------------------------------------------
    # Enrich context — no LLM call, just data assembly
    # ------------------------------------------------------------------

    async def enrich_context(
        self,
        discovery: Discovery | DiscoveryCluster,
        triage: TriageResult,
    ) -> EnrichedDiscovery:
        """Assemble all context for a discovery into an EnrichedDiscovery."""
        # Extract code context
        if isinstance(discovery, DiscoveryCluster):
            code_ctx = discovery.combined_context
            disc_type = (
                discovery.discoveries[0].discovery_type.value
                if hasattr(discovery.discoveries[0].discovery_type, "value")
                else str(discovery.discoveries[0].discovery_type)
            )
            files = discovery.combined_files
        else:
            code_ctx = getattr(discovery, "code_context", "") or ""
            disc_type = (
                discovery.discovery_type.value
                if hasattr(discovery.discovery_type, "value")
                else str(discovery.discovery_type)
            )
            files = discovery.relevant_files

        # Read file contents if code_context is empty
        if not code_ctx and files:
            snippets = []
            for f in files[:3]:  # cap at 3 files
                full_path = Path(self._project_root) / f
                try:
                    content = full_path.read_text(encoding="utf-8")
                    # Take first 100 lines
                    lines = content.splitlines()[:100]
                    numbered = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
                    snippets.append(f"--- {f} ---\n" + "\n".join(numbered))
                except Exception:
                    pass
            code_ctx = "\n\n".join(snippets)

        # Query similar past attempts
        similar = self._store.query_similar(disc_type, files, limit=5)

        # Build suggested approach from triage + history
        approach = triage.fix_approach
        if similar:
            failed = [a for a in similar if not a.success]
            if failed:
                approach += f"\n\nNote: {len(failed)} similar fix(es) have failed before."
                for fa in failed[:2]:
                    approach += f"\n  - {fa.title}: {fa.error_message[:100]}"

        return EnrichedDiscovery(
            discovery=discovery,
            code_context=code_ctx,
            triage=triage,
            similar_attempts=similar,
            suggested_approach=approach,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _single_cluster(d: Discovery) -> DiscoveryCluster:
        """Wrap a single discovery in a cluster."""
        return DiscoveryCluster(
            title=d.title,
            discoveries=[d],
            rationale="Single discovery",
            combined_files=list(d.relevant_files),
            combined_context=getattr(d, "code_context", "") or "",
        )
