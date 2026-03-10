"""Discovery engine that scans the Jarvis system for improvement opportunities.

Analyzes logs, test results, TODO items, and code quality to surface
actionable discoveries. No agent or network dependency — purely a service.
"""

from __future__ import annotations

import ast
import asyncio
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from ..logging import JarvisLogger
from ..services.todo_service import TodoService, TodoItem, TaskStatus


class DiscoveryType(str, Enum):
    """Categories of discoverable issues."""

    LOG_ERROR = "log_error"
    TEST_FAILURE = "test_failure"
    MANUAL_TODO = "manual_todo"
    CODE_QUALITY = "code_quality"


@dataclass
class Discovery:
    """A single improvement opportunity found by the analyzer."""

    discovery_type: DiscoveryType
    title: str
    description: str
    priority: str  # urgent / high / medium / low
    relevant_files: list[str] = field(default_factory=list)
    source_detail: str = ""
    todo_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize all fields to a plain dict (enum stored as string value)."""
        return {
            "discovery_type": self.discovery_type.value,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "relevant_files": list(self.relevant_files),
            "source_detail": self.source_detail,
            "todo_id": self.todo_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Discovery":
        """Deserialize from a plain dict, converting the type string back to enum."""
        return cls(
            discovery_type=DiscoveryType(data["discovery_type"]),
            title=data["title"],
            description=data["description"],
            priority=data["priority"],
            relevant_files=data.get("relevant_files", []),
            source_detail=data.get("source_detail", ""),
            todo_id=data.get("todo_id"),
        )


class SystemAnalyzer:
    """Scans the Jarvis project for issues and improvement opportunities."""

    def __init__(
        self,
        project_root: str,
        log_db_path: str,
        todo_service: Optional[TodoService] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self.project_root = project_root
        self.log_db_path = log_db_path
        self.todo_service = todo_service
        self.logger = logger or JarvisLogger()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_full_analysis(self) -> list[Discovery]:
        """Run all analyzers and return deduplicated results."""
        all_discoveries: list[Discovery] = []

        analyzers = [
            ("logs", self.analyze_logs),
            ("tests", self.analyze_tests),
            ("todos", self.analyze_todos),
            ("code_quality", self.analyze_code_quality),
        ]

        for name, analyzer in analyzers:
            try:
                results = await analyzer()
                all_discoveries.extend(results)
            except Exception as exc:
                self.logger.log(
                    "ERROR",
                    f"SystemAnalyzer.{name} failed",
                    str(exc),
                )

        # Deduplicate by title — keep first occurrence
        seen_titles: set[str] = set()
        deduplicated: list[Discovery] = []
        for d in all_discoveries:
            if d.title not in seen_titles:
                seen_titles.add(d.title)
                deduplicated.append(d)

        return deduplicated

    # ------------------------------------------------------------------
    # Log analysis
    # ------------------------------------------------------------------

    async def analyze_logs(self, lookback_hours: int = 24) -> list[Discovery]:
        """Scan the SQLite log database for recent errors and warnings."""
        return await asyncio.to_thread(self._analyze_logs_sync, lookback_hours)

    def _analyze_logs_sync(self, lookback_hours: int) -> list[Discovery]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        ).isoformat()

        try:
            conn = sqlite3.connect(self.log_db_path)
            conn.row_factory = sqlite3.Row
        except Exception:
            return []

        try:
            rows = conn.execute(
                """
                SELECT level, action, details, MAX(timestamp) AS latest_ts
                FROM logs
                WHERE (level = 'ERROR' OR level = 'WARNING')
                  AND timestamp >= ?
                GROUP BY action
                ORDER BY latest_ts DESC
                """,
                (cutoff,),
            ).fetchall()
        except Exception:
            conn.close()
            return []

        discoveries: list[Discovery] = []
        for row in rows:
            level = row["level"]
            action = row["action"]
            details = row["details"] or ""
            priority = "high" if level == "ERROR" else "medium"

            discoveries.append(
                Discovery(
                    discovery_type=DiscoveryType.LOG_ERROR,
                    title=f"Log {level.lower()}: {action}",
                    description=f"Detected {level} in logs for action '{action}'.",
                    priority=priority,
                    relevant_files=[],
                    source_detail=details,
                )
            )

        conn.close()
        return discoveries

    # ------------------------------------------------------------------
    # Test analysis
    # ------------------------------------------------------------------

    async def analyze_tests(self, timeout: int = 120) -> list[Discovery]:
        """Run pytest and parse failures into discoveries."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "pytest",
                "--tb=short",
                "-q",
                "--timeout=30",
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except Exception:
            return []

        output = stdout.decode(errors="replace")
        discoveries: list[Discovery] = []

        for line in output.splitlines():
            if "FAILED" not in line:
                continue

            # Format: "FAILED tests/test_foo.py::TestClass::test_method - reason"
            stripped = line.strip()
            if stripped.startswith("FAILED "):
                stripped = stripped[len("FAILED "):]

            # Split on " - " to separate test path from reason
            parts = stripped.split(" - ", 1)
            test_id = parts[0].strip()
            reason = parts[1].strip() if len(parts) > 1 else "Unknown"

            # Extract file path from test_id (before "::")
            file_path = test_id.split("::")[0] if "::" in test_id else test_id

            discoveries.append(
                Discovery(
                    discovery_type=DiscoveryType.TEST_FAILURE,
                    title=f"Test failure: {test_id}",
                    description=f"Test {test_id} failed: {reason}",
                    priority="urgent",
                    relevant_files=[file_path],
                    source_detail=reason,
                )
            )

        return discoveries

    # ------------------------------------------------------------------
    # TODO analysis
    # ------------------------------------------------------------------

    async def analyze_todos(
        self, tags: list[str] | None = None,
    ) -> list[Discovery]:
        """Convert tagged TodoService items into discoveries."""
        if self.todo_service is None:
            return []

        if tags is None:
            tags = ["night-agent", "system-improvement"]

        tag_set = set(tags)

        # Call synchronously — TodoService uses sqlite3 with
        # check_same_thread=True, so it must run on the creating thread.
        # The call is fast (in-process SQLite) so no need for to_thread.
        all_items: list[TodoItem] = self.todo_service.list()

        discoveries: list[Discovery] = []
        for item in all_items:
            if item.status == TaskStatus.DONE:
                continue
            if not tag_set.intersection(item.tags):
                continue

            discoveries.append(
                Discovery(
                    discovery_type=DiscoveryType.MANUAL_TODO,
                    title=f"Todo: {item.title}",
                    description=item.description or item.title,
                    priority=item.priority.value,
                    relevant_files=[],
                    source_detail=f"tags={item.tags}, status={item.status.value}",
                    todo_id=item.id,
                )
            )

        return discoveries

    # ------------------------------------------------------------------
    # Code quality analysis
    # ------------------------------------------------------------------

    async def analyze_code_quality(self) -> list[Discovery]:
        """Use AST inspection to find files with undocumented public methods."""
        return await asyncio.to_thread(self._analyze_code_quality_sync)

    def _analyze_code_quality_sync(self) -> list[Discovery]:
        root = Path(self.project_root)
        scan_dirs = [
            root / "jarvis" / "agents",
            root / "jarvis" / "services",
        ]

        discoveries: list[Discovery] = []

        for scan_dir in scan_dirs:
            if not scan_dir.is_dir():
                continue
            for py_file in scan_dir.rglob("*.py"):
                try:
                    source = py_file.read_text(encoding="utf-8")
                    tree = ast.parse(source, filename=str(py_file))
                except Exception:
                    continue

                for node in ast.walk(tree):
                    if not isinstance(node, ast.ClassDef):
                        continue

                    undocumented: list[str] = []
                    for item in node.body:
                        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            continue
                        if item.name.startswith("_"):
                            continue
                        if not ast.get_docstring(item):
                            undocumented.append(item.name)

                    if len(undocumented) >= 3:
                        rel_path = str(py_file.relative_to(root))
                        methods_str = ", ".join(undocumented)
                        discoveries.append(
                            Discovery(
                                discovery_type=DiscoveryType.CODE_QUALITY,
                                title=f"Undocumented methods in {rel_path}::{node.name}",
                                description=(
                                    f"Class {node.name} in {rel_path} has "
                                    f"{len(undocumented)} undocumented public "
                                    f"methods: {methods_str}"
                                ),
                                priority="low",
                                relevant_files=[rel_path],
                                source_detail=methods_str,
                            )
                        )

        return discoveries
