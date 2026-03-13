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
    UNUSED_IMPORT = "unused_import"
    EXCEPTION_ANTIPATTERN = "exception_antipattern"
    COMPLEXITY_HOTSPOT = "complexity_hotspot"
    DEAD_CODE = "dead_code"
    STALE_COMMENT = "stale_comment"


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
    confidence: str = "medium"
    code_context: str = ""       # 10-15 numbered lines around the finding
    function_scope: str = ""     # enclosing function/class name

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
            "confidence": self.confidence,
            "code_context": self.code_context,
            "function_scope": self.function_scope,
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
            confidence=data.get("confidence", "medium"),
            code_context=data.get("code_context", ""),
            function_scope=data.get("function_scope", ""),
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

    # ------------------------------------------------------------------
    # Context enrichment helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_context(source: str, lineno: int, radius: int = 7) -> str:
        """Return numbered source lines [lineno-radius .. lineno+radius]."""
        lines = source.splitlines()
        start = max(0, lineno - 1 - radius)
        end = min(len(lines), lineno + radius)
        numbered = []
        for i, line in enumerate(lines[start:end], start=start + 1):
            marker = ">>>" if i == lineno else "   "
            numbered.append(f"{marker} {i:4d} | {line}")
        return "\n".join(numbered)

    @staticmethod
    def _find_enclosing_scope(tree: ast.Module, lineno: int) -> str:
        """Return name of innermost function/class containing lineno."""
        best_name = ""
        best_start = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                end_line = getattr(node, "end_lineno", None) or 9999
                if node.lineno <= lineno <= end_line:
                    if node.lineno >= best_start:
                        best_start = node.lineno
                        best_name = node.name
        return best_name

    # ------------------------------------------------------------------
    # Unused imports analysis
    # ------------------------------------------------------------------

    async def analyze_unused_imports(self) -> list[Discovery]:
        """Find imports that are never referenced in the rest of the file."""
        return await asyncio.to_thread(self._analyze_unused_imports_sync)

    def _analyze_unused_imports_sync(self) -> list[Discovery]:
        import re

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

                # Collect imported names with their line numbers
                imported: list[tuple[str, int]] = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.asname or alias.name.split(".")[0]
                            imported.append((name, node.lineno))
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            name = alias.asname or alias.name
                            imported.append((name, node.lineno))

                if not imported:
                    continue

                # Check which names are never referenced outside import lines
                import_lines = {ln for _, ln in imported}
                non_import_source = "\n".join(
                    line for i, line in enumerate(source.splitlines(), 1)
                    if i not in import_lines
                )

                unused: list[tuple[str, int]] = []
                for name, ln in imported:
                    if name == "*":
                        continue
                    # Simple word-boundary check in non-import lines
                    if not re.search(rf"\b{re.escape(name)}\b", non_import_source):
                        unused.append((name, ln))

                if unused:
                    rel_path = str(py_file.relative_to(root))
                    names_str = ", ".join(f"{n} (line {ln})" for n, ln in unused)
                    # Extract context around first unused import
                    first_lineno = unused[0][1]
                    ctx = self._extract_context(source, first_lineno)
                    scope = self._find_enclosing_scope(tree, first_lineno)
                    discoveries.append(
                        Discovery(
                            discovery_type=DiscoveryType.UNUSED_IMPORT,
                            title=f"Unused imports in {rel_path}",
                            description=f"Unused imports in {rel_path}: {names_str}",
                            priority="low",
                            relevant_files=[rel_path],
                            source_detail=names_str,
                            code_context=ctx,
                            function_scope=scope,
                        )
                    )

        return discoveries

    # ------------------------------------------------------------------
    # Exception antipatterns analysis
    # ------------------------------------------------------------------

    async def analyze_exception_antipatterns(self) -> list[Discovery]:
        """Find bare excepts and swallowed exceptions."""
        return await asyncio.to_thread(self._analyze_exception_antipatterns_sync)

    def _analyze_exception_antipatterns_sync(self) -> list[Discovery]:
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

                antipatterns: list[tuple[str, int]] = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.ExceptHandler):
                        if node.type is None:
                            antipatterns.append(
                                (f"Bare except: at line {node.lineno}", node.lineno)
                            )
                        # Check for swallowed exceptions (except with only pass)
                        elif (
                            len(node.body) == 1
                            and isinstance(node.body[0], ast.Pass)
                        ):
                            antipatterns.append(
                                (f"Swallowed exception at line {node.lineno}", node.lineno)
                            )

                if antipatterns:
                    rel_path = str(py_file.relative_to(root))
                    details_str = "; ".join(desc for desc, _ in antipatterns)
                    first_lineno = antipatterns[0][1]
                    ctx = self._extract_context(source, first_lineno)
                    scope = self._find_enclosing_scope(tree, first_lineno)
                    discoveries.append(
                        Discovery(
                            discovery_type=DiscoveryType.EXCEPTION_ANTIPATTERN,
                            title=f"Exception antipatterns in {rel_path}",
                            description=f"Found {len(antipatterns)} antipattern(s) in {rel_path}: {details_str}",
                            priority="medium",
                            relevant_files=[rel_path],
                            source_detail=details_str,
                            code_context=ctx,
                            function_scope=scope,
                        )
                    )

        return discoveries

    # ------------------------------------------------------------------
    # Complexity hotspots analysis
    # ------------------------------------------------------------------

    async def analyze_complexity_hotspots(self) -> list[Discovery]:
        """Find overly long functions."""
        return await asyncio.to_thread(self._analyze_complexity_hotspots_sync)

    def _analyze_complexity_hotspots_sync(self, threshold: int = 50) -> list[Discovery]:
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

                hotspots: list[tuple[str, int]] = []
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        end_line = getattr(node, "end_lineno", None)
                        if end_line is None:
                            continue
                        func_lines = end_line - node.lineno + 1
                        if func_lines >= threshold:
                            hotspots.append(
                                (f"{node.name} ({func_lines} lines, line {node.lineno})", node.lineno)
                            )

                if hotspots:
                    rel_path = str(py_file.relative_to(root))
                    details_str = "; ".join(desc for desc, _ in hotspots)
                    first_lineno = hotspots[0][1]
                    ctx = self._extract_context(source, first_lineno)
                    scope = self._find_enclosing_scope(tree, first_lineno)
                    discoveries.append(
                        Discovery(
                            discovery_type=DiscoveryType.COMPLEXITY_HOTSPOT,
                            title=f"Complexity hotspots in {rel_path}",
                            description=f"Long functions in {rel_path}: {details_str}",
                            priority="medium",
                            relevant_files=[rel_path],
                            source_detail=details_str,
                            code_context=ctx,
                            function_scope=scope,
                        )
                    )

        return discoveries

    # ------------------------------------------------------------------
    # Dead code analysis
    # ------------------------------------------------------------------

    async def analyze_dead_code(self) -> list[Discovery]:
        """Find functions/methods defined but never referenced elsewhere."""
        return await asyncio.to_thread(self._analyze_dead_code_sync)

    def _analyze_dead_code_sync(self) -> list[Discovery]:
        import re

        root = Path(self.project_root)
        scan_dirs = [
            root / "jarvis" / "agents",
            root / "jarvis" / "services",
        ]

        # Phase 1: collect all function/method definitions
        all_defs: list[tuple[str, str, int]] = []  # (name, file_path, lineno)
        all_sources: list[tuple[str, str]] = []     # (file_path, source)

        for scan_dir in scan_dirs:
            if not scan_dir.is_dir():
                continue
            for py_file in scan_dir.rglob("*.py"):
                try:
                    source = py_file.read_text(encoding="utf-8")
                    tree = ast.parse(source, filename=str(py_file))
                except Exception:
                    continue

                rel_path = str(py_file.relative_to(root))
                all_sources.append((rel_path, source))

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Skip private/dunder methods and common framework hooks
                        if node.name.startswith("_"):
                            continue
                        all_defs.append((node.name, rel_path, node.lineno))

        # Phase 2: count references across all sources
        discoveries: list[Discovery] = []
        combined_source = "\n".join(src for _, src in all_sources)

        for name, def_path, lineno in all_defs:
            # Count occurrences — at least 2 means definition + usage
            ref_count = len(re.findall(rf"\b{re.escape(name)}\b", combined_source))
            if ref_count <= 1:
                # Find the source text for this file
                file_source = ""
                for src_path, src_text in all_sources:
                    if src_path == def_path:
                        file_source = src_text
                        break
                ctx = self._extract_context(file_source, lineno) if file_source else ""
                discoveries.append(
                    Discovery(
                        discovery_type=DiscoveryType.DEAD_CODE,
                        title=f"Potentially dead: {name} in {def_path}",
                        description=f"Function '{name}' at line {lineno} in {def_path} appears unreferenced.",
                        priority="low",
                        relevant_files=[def_path],
                        source_detail=f"{name} (line {lineno})",
                        code_context=ctx,
                        function_scope=name,
                    )
                )

        return discoveries

    # ------------------------------------------------------------------
    # Stale comments analysis
    # ------------------------------------------------------------------

    async def analyze_stale_comments(self) -> list[Discovery]:
        """Find TODO/FIXME/HACK/XXX comments."""
        return await asyncio.to_thread(self._analyze_stale_comments_sync)

    def _analyze_stale_comments_sync(self) -> list[Discovery]:
        import re

        root = Path(self.project_root)
        scan_dirs = [
            root / "jarvis" / "agents",
            root / "jarvis" / "services",
        ]

        pattern = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)
        discoveries: list[Discovery] = []

        for scan_dir in scan_dirs:
            if not scan_dir.is_dir():
                continue
            for py_file in scan_dir.rglob("*.py"):
                try:
                    source = py_file.read_text(encoding="utf-8")
                except Exception:
                    continue

                matches: list[tuple[str, int]] = []
                for i, line in enumerate(source.splitlines(), 1):
                    m = pattern.search(line)
                    if m:
                        marker = m.group(1).upper()
                        matches.append((f"{marker} at line {i}", i))

                if matches:
                    rel_path = str(py_file.relative_to(root))
                    details_str = "; ".join(desc for desc, _ in matches)
                    first_lineno = matches[0][1]
                    ctx = self._extract_context(source, first_lineno)
                    # Parse source to get enclosing scope
                    try:
                        tree_for_scope = ast.parse(source)
                        scope = self._find_enclosing_scope(tree_for_scope, first_lineno)
                    except Exception:
                        scope = ""
                    discoveries.append(
                        Discovery(
                            discovery_type=DiscoveryType.STALE_COMMENT,
                            title=f"Stale comments in {rel_path}",
                            description=f"Found {len(matches)} marker comment(s) in {rel_path}: {details_str}",
                            priority="low",
                            relevant_files=[rel_path],
                            source_detail=details_str,
                            code_context=ctx,
                            function_scope=scope,
                        )
                    )

        return discoveries
