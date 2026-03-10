"""Markdown-based memory vault with tiered storage.

Provides human-readable, file-based memory that requires no external
dependencies for basic operation.  Memories live in ``~/.jarvis/memory/``
as plain markdown files organised into short-term daily logs and long-term
categorised files, with lightweight indexes for fast lookup.
"""

from __future__ import annotations

import asyncio
import datetime
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_VAULT_DIR = os.path.join(str(Path.home()), ".jarvis", "memory")
SHORT_TERM_TTL_DAYS = 7

BUILTIN_CATEGORIES = [
    "personal",
    "preferences",
    "relationships",
    "work",
    "goals",
    "skills",
    "health",
]

CATEGORY_FILE_MAP = {
    "personal": "personal.md",
    "preferences": "preferences.md",
    "relationships": "relationships.md",
    "work": "work.md",
    "goals": "goals.md",
    "skills": "skills.md",
    "health": "health.md",
    # Legacy mappings (FactMemoryService categories -> vault files)
    "personal_info": "personal.md",
    "preference": "preferences.md",
    "relationship": "relationships.md",
    "memory": "personal.md",
    "skill": "skills.md",
    "goal": "goals.md",
    "general": "personal.md",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MemoryEntry:
    """A single memory record."""

    content: str
    timestamp: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now()
    )
    source: str = "conversation"  # conversation | explicit | extracted | inferred
    category: str = "personal"
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.8
    promoted: bool = False
    memory_id: str = field(default_factory=lambda: uuid4().hex[:12])
    section: Optional[str] = None  # sub-heading inside the long-term file


# ---------------------------------------------------------------------------
# Vault index (in-memory cache)
# ---------------------------------------------------------------------------


class VaultIndex:
    """Lightweight in-memory cache of tag/entity cross-references."""

    def __init__(self) -> None:
        # tag -> list of (file_path, memory_id)
        self.topic_map: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        # entity -> list of (file_path, memory_id)
        self.entity_map: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        # chronological list of (timestamp_str, file_path, memory_id, summary)
        self.timeline: List[Tuple[str, str, str, str]] = []

    def add_entry(
        self,
        memory_id: str,
        file_path: str,
        tags: List[str],
        entities: Optional[List[str]] = None,
        timestamp_str: str = "",
        summary: str = "",
    ) -> None:
        for tag in tags:
            tag_lower = tag.lower().strip("#")
            self.topic_map[tag_lower].append((file_path, memory_id))
        for entity in entities or []:
            self.entity_map[entity.lower()].append((file_path, memory_id))
        if timestamp_str:
            self.timeline.append((timestamp_str, file_path, memory_id, summary))

    def search_topics(self, query: str) -> List[Tuple[str, str]]:
        """Return (file_path, memory_id) pairs matching query tokens in topics."""
        tokens = [t.lower().strip("#") for t in query.split()]
        hits: List[Tuple[str, str]] = []
        for token in tokens:
            for tag, refs in self.topic_map.items():
                if token in tag or tag in token:
                    hits.extend(refs)
        return list(dict.fromkeys(hits))  # deduplicate, preserve order

    def search_entities(self, query: str) -> List[Tuple[str, str]]:
        tokens = [t.lower() for t in query.split()]
        hits: List[Tuple[str, str]] = []
        for token in tokens:
            for entity, refs in self.entity_map.items():
                if token in entity or entity in token:
                    hits.extend(refs)
        return list(dict.fromkeys(hits))


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class MarkdownMemoryService:
    """Markdown-file-based memory vault with short-term and long-term tiers."""

    def __init__(
        self,
        vault_dir: Optional[str] = None,
        short_term_ttl_days: int = SHORT_TERM_TTL_DAYS,
        auto_promote: bool = True,
        ai_client: Optional[Any] = None,
    ) -> None:
        self.vault_dir = Path(vault_dir or DEFAULT_VAULT_DIR)
        self.short_term_dir = self.vault_dir / "short_term"
        self.long_term_dir = self.vault_dir / "long_term"
        self.custom_dir = self.long_term_dir / "custom"
        self.index_dir = self.vault_dir / "indexes"
        self.meta_dir = self.vault_dir / "meta"

        self.short_term_ttl_days = short_term_ttl_days
        self.auto_promote = auto_promote
        self.ai_client = ai_client

        # In-memory index cache
        self._index = VaultIndex()
        # Per-file async locks
        self._locks: Dict[str, asyncio.Lock] = {}

        self._ensure_vault_structure()
        self._load_indexes()

    # ------------------------------------------------------------------
    # Vault structure
    # ------------------------------------------------------------------

    def _ensure_vault_structure(self) -> None:
        """Create the vault directory tree if it does not exist."""
        for d in [
            self.short_term_dir,
            self.long_term_dir,
            self.custom_dir,
            self.index_dir,
            self.meta_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Seed long-term files
        for cat in BUILTIN_CATEGORIES:
            fp = self.long_term_dir / f"{cat}.md"
            if not fp.exists():
                title = cat.replace("_", " ").title()
                fp.write_text(
                    f"# {title}\n\n---\n_Last updated: never. 0 entries._\n"
                )

        # Seed index files
        for name in ["topic_index.md", "entity_index.md", "timeline.md"]:
            fp = self.index_dir / name
            if not fp.exists():
                title = name.replace("_", " ").replace(".md", "").title()
                fp.write_text(f"# {title}\n\n")

        # Seed meta files
        for name in ["consolidation_log.md", "stats.md"]:
            fp = self.meta_dir / name
            if not fp.exists():
                title = name.replace("_", " ").replace(".md", "").title()
                fp.write_text(f"# {title}\n\n")

    def _get_lock(self, path: str) -> asyncio.Lock:
        if path not in self._locks:
            self._locks[path] = asyncio.Lock()
        return self._locks[path]

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    async def store(
        self,
        content: str,
        category: str = "personal",
        tags: Optional[List[str]] = None,
        source: str = "conversation",
        confidence: float = 0.8,
        section: Optional[str] = None,
    ) -> MemoryEntry:
        """Write a memory to today's daily log and optionally promote it."""
        entry = MemoryEntry(
            content=content,
            category=category,
            tags=tags or [],
            source=source,
            confidence=confidence,
            section=section,
        )

        await self._append_to_daily_log(entry)

        # Update in-memory index
        today_file = str(
            self.short_term_dir / f"{entry.timestamp.strftime('%Y-%m-%d')}.md"
        )
        self._index.add_entry(
            memory_id=entry.memory_id,
            file_path=today_file,
            tags=entry.tags,
            timestamp_str=entry.timestamp.strftime("%Y-%m-%d %H:%M"),
            summary=content[:80],
        )

        # Auto-promotion logic
        if self.auto_promote and self._should_promote(entry):
            await self.promote(entry.memory_id, category, section, _entry=entry)

        return entry

    def _should_promote(self, entry: MemoryEntry) -> bool:
        """Decide whether a memory should be promoted without AI."""
        if entry.source == "explicit":
            return True
        if entry.confidence >= 0.9 and entry.category in BUILTIN_CATEGORIES:
            return True
        mapped = CATEGORY_FILE_MAP.get(entry.category)
        if mapped and entry.confidence >= 0.9:
            return True
        return False

    # ------------------------------------------------------------------
    # Recall / search
    # ------------------------------------------------------------------

    async def recall(
        self,
        query: str,
        top_k: int = 5,
        categories: Optional[List[str]] = None,
        date_range: Optional[Tuple[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Multi-stage search: index lookup -> tag match -> keyword search -> scoring."""
        results: List[Dict[str, Any]] = []

        # Stage 1: index lookup
        index_hits = self._index.search_topics(query)
        entity_hits = self._index.search_entities(query)
        all_index_hits = list(dict.fromkeys(index_hits + entity_hits))

        # Gather files to search
        files_to_search: List[Path] = []

        if categories:
            for cat in categories:
                fname = CATEGORY_FILE_MAP.get(cat, f"{cat}.md")
                fp = self.long_term_dir / fname
                if fp.exists():
                    files_to_search.append(fp)
        else:
            # Search all long-term files
            for fp in self.long_term_dir.glob("*.md"):
                files_to_search.append(fp)
            # Plus custom
            for fp in self.custom_dir.glob("*.md"):
                files_to_search.append(fp)

        # Short-term files
        if date_range:
            start, end = date_range
            for fp in self.short_term_dir.glob("*.md"):
                date_str = fp.stem
                if start <= date_str <= end:
                    files_to_search.append(fp)
        else:
            for fp in self.short_term_dir.glob("*.md"):
                files_to_search.append(fp)

        # Deduplicate
        files_to_search = list(dict.fromkeys(files_to_search))

        # Stage 2: text search across all candidate files
        text_results = await self._text_search(query, files_to_search)
        results.extend(text_results)

        # Stage 3: boost results that appeared in index
        index_ids = {mid for _, mid in all_index_hits}
        for r in results:
            if r.get("memory_id") in index_ids:
                r["score"] = r.get("score", 0.5) + 0.2

        # Sort by score descending
        results.sort(key=lambda r: r.get("score", 0), reverse=True)

        return results[:top_k]

    async def _text_search(
        self, query: str, files: List[Path]
    ) -> List[Dict[str, Any]]:
        """Full-text search with scoring."""
        results: List[Dict[str, Any]] = []
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        for fp in files:
            if not fp.exists():
                continue
            async with self._get_lock(str(fp)):
                content = fp.read_text()

            if fp.parent == self.short_term_dir:
                entries = self._parse_daily_log(content, str(fp))
            else:
                entries = self._parse_long_term_file(content, str(fp))

            for entry_dict in entries:
                text = entry_dict.get("content", "").lower()
                if not text:
                    continue

                # Scoring
                score = 0.0

                # Exact match
                if query_lower in text:
                    score = 1.0
                else:
                    # Keyword coverage
                    text_tokens = set(text.split())
                    overlap = query_tokens & text_tokens
                    if overlap:
                        score = len(overlap) / len(query_tokens) * 0.7

                if score > 0:
                    # Recency bonus
                    date_str = entry_dict.get("date", "")
                    if date_str:
                        try:
                            entry_date = datetime.datetime.strptime(
                                date_str, "%Y-%m-%d"
                            )
                            days_ago = (
                                datetime.datetime.now() - entry_date
                            ).days
                            recency = max(0, 0.2 - (days_ago * 0.01))
                            score += recency
                        except ValueError:
                            pass

                    entry_dict["score"] = round(score, 3)
                    results.append(entry_dict)

        return results

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    async def promote(
        self,
        memory_id: str,
        target_category: Optional[str] = None,
        section: Optional[str] = None,
        _entry: Optional[MemoryEntry] = None,
    ) -> bool:
        """Move a short-term entry to its long-term file."""
        entry = _entry
        if entry is None:
            entry = await self._find_entry_by_id(memory_id)
        if entry is None:
            return False

        category = target_category or entry.category
        fname = CATEGORY_FILE_MAP.get(category, f"{category}.md")
        target_file = self.long_term_dir / fname

        if not target_file.exists():
            # Custom category
            target_file = self.custom_dir / fname
            if not target_file.exists():
                title = category.replace("_", " ").title()
                target_file.write_text(
                    f"# {title}\n\n---\n_Last updated: never. 0 entries._\n"
                )

        await self._append_to_long_term(entry, target_file, section)

        # Mark as promoted in the daily log
        await self._mark_promoted_in_daily_log(entry)

        entry.promoted = True

        # Update indexes
        self._index.add_entry(
            memory_id=entry.memory_id,
            file_path=str(target_file),
            tags=entry.tags,
            timestamp_str=entry.timestamp.strftime("%Y-%m-%d %H:%M"),
            summary=entry.content[:80],
        )
        await self._update_index_files(entry, str(target_file))

        return True

    # ------------------------------------------------------------------
    # Consolidation
    # ------------------------------------------------------------------

    async def consolidate(
        self,
        category: str,
        ai_client: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Merge duplicates and tidy a long-term file."""
        client = ai_client or self.ai_client
        fname = CATEGORY_FILE_MAP.get(category, f"{category}.md")
        target_file = self.long_term_dir / fname
        if not target_file.exists():
            target_file = self.custom_dir / fname
        if not target_file.exists():
            return {"consolidated": 0, "removed_duplicates": 0}

        async with self._get_lock(str(target_file)):
            content = target_file.read_text()

        entries = self._parse_long_term_file(content, str(target_file))
        if not entries:
            return {"consolidated": 0, "removed_duplicates": 0}

        # Simple dedup: remove entries with identical content
        seen: Dict[str, Dict[str, Any]] = {}
        duplicates = 0
        for e in entries:
            key = e["content"].strip().lower()
            if key in seen:
                duplicates += 1
            else:
                seen[key] = e

        unique_entries = list(seen.values())

        # If AI client available, ask it to consolidate further
        if client and len(unique_entries) > 1:
            try:
                consolidated = await self._ai_consolidate(
                    client, category, unique_entries
                )
                if consolidated:
                    unique_entries = consolidated
            except Exception:
                pass  # fall back to simple dedup

        # Rewrite the file
        await self._rewrite_long_term_file(target_file, category, unique_entries)

        # Log consolidation
        await self._log_consolidation(category, len(entries), len(unique_entries))

        return {
            "consolidated": len(unique_entries),
            "removed_duplicates": duplicates,
            "original_count": len(entries),
        }

    async def _ai_consolidate(
        self, client: Any, category: str, entries: List[Dict[str, Any]]
    ) -> Optional[List[Dict[str, Any]]]:
        """Use AI to merge similar entries."""
        entries_text = "\n".join(
            f"- {e['content']} [{e.get('date', '')}]" for e in entries
        )
        prompt = (
            f"These are memory entries in the '{category}' category. "
            f"Merge any duplicates or near-duplicates, keeping the most recent date. "
            f"Return one entry per line in the format: CONTENT [DATE]\n\n"
            f"{entries_text}\n\n"
            f"Return only the merged list, one per line:"
        )
        response, _ = await client.weak_chat(
            [{"role": "user", "content": prompt}], []
        )
        text = response.content.strip()
        result = []
        for line in text.split("\n"):
            line = line.strip().lstrip("- ")
            if not line:
                continue
            # Parse "CONTENT [DATE]"
            date_match = re.search(r"\[(\d{4}-\d{2}-\d{2})\]", line)
            date_str = date_match.group(1) if date_match else ""
            content_part = re.sub(r"\s*\[\d{4}-\d{2}-\d{2}\]\s*$", "", line)
            result.append({"content": content_part, "date": date_str})
        return result if result else None

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    async def prune_short_term(self) -> Dict[str, Any]:
        """Remove daily logs older than TTL, promoting high-confidence stragglers."""
        cutoff = datetime.datetime.now() - datetime.timedelta(
            days=self.short_term_ttl_days
        )
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        pruned_files = 0
        promoted_count = 0

        for fp in sorted(self.short_term_dir.glob("*.md")):
            date_str = fp.stem
            if date_str >= cutoff_str:
                continue
            # Parse and promote stragglers
            async with self._get_lock(str(fp)):
                content = fp.read_text()
            entries = self._parse_daily_log(content, str(fp))
            for e in entries:
                if not e.get("promoted") and e.get("confidence", 0) >= 0.9:
                    entry = MemoryEntry(
                        content=e["content"],
                        category=e.get("category", "personal"),
                        tags=e.get("tags", []),
                        confidence=e.get("confidence", 0.8),
                        memory_id=e.get("memory_id", uuid4().hex[:12]),
                    )
                    await self.promote(entry.memory_id, _entry=entry)
                    promoted_count += 1

            # Remove the file
            fp.unlink()
            pruned_files += 1

        return {"pruned_files": pruned_files, "promoted_before_prune": promoted_count}

    # ------------------------------------------------------------------
    # Browse & stats
    # ------------------------------------------------------------------

    async def browse_vault(self) -> Dict[str, Any]:
        """Return structural overview of the vault."""
        overview: Dict[str, Any] = {
            "short_term": {},
            "long_term": {},
            "custom": {},
        }

        for fp in sorted(self.short_term_dir.glob("*.md")):
            content = fp.read_text()
            entry_count = content.count("### ")
            overview["short_term"][fp.name] = {
                "entries": entry_count,
                "size_bytes": fp.stat().st_size,
            }

        for fp in sorted(self.long_term_dir.glob("*.md")):
            content = fp.read_text()
            entry_count = len(
                [l for l in content.split("\n") if l.startswith("- ") and "[" in l]
            )
            overview["long_term"][fp.name] = {
                "entries": entry_count,
                "size_bytes": fp.stat().st_size,
            }

        for fp in sorted(self.custom_dir.glob("*.md")):
            content = fp.read_text()
            entry_count = len(
                [l for l in content.split("\n") if l.startswith("- ") and "[" in l]
            )
            overview["custom"][fp.name] = {
                "entries": entry_count,
                "size_bytes": fp.stat().st_size,
            }

        return overview

    async def get_stats(self) -> Dict[str, Any]:
        """Return vault statistics."""
        short_term_count = 0
        long_term_count = 0
        total_files = 0

        for fp in self.short_term_dir.glob("*.md"):
            content = fp.read_text()
            short_term_count += content.count("### ")
            total_files += 1

        for fp in self.long_term_dir.glob("*.md"):
            content = fp.read_text()
            long_term_count += len(
                [l for l in content.split("\n") if l.startswith("- ") and "[" in l]
            )
            total_files += 1

        for fp in self.custom_dir.glob("*.md"):
            content = fp.read_text()
            long_term_count += len(
                [l for l in content.split("\n") if l.startswith("- ") and "[" in l]
            )
            total_files += 1

        return {
            "short_term_entries": short_term_count,
            "long_term_entries": long_term_count,
            "total_entries": short_term_count + long_term_count,
            "total_files": total_files,
            "vault_dir": str(self.vault_dir),
            "categories": BUILTIN_CATEGORIES,
            "topic_count": len(self._index.topic_map),
            "entity_count": len(self._index.entity_map),
        }

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _load_indexes(self) -> None:
        """Load index files into the in-memory cache on startup."""
        topic_file = self.index_dir / "topic_index.md"
        if topic_file.exists():
            self._parse_index_file(topic_file.read_text(), self._index.topic_map)

        entity_file = self.index_dir / "entity_index.md"
        if entity_file.exists():
            self._parse_index_file(entity_file.read_text(), self._index.entity_map)

    def _parse_index_file(
        self, content: str, target_map: Dict[str, List[Tuple[str, str]]]
    ) -> None:
        """Parse an index markdown file into the target map."""
        for line in content.split("\n"):
            # Format: - **tag**: file_path#memory_id, file_path#memory_id
            match = re.match(r"^- \*\*(.+?)\*\*:\s*(.+)$", line)
            if match:
                key = match.group(1).lower()
                refs_str = match.group(2)
                refs: List[Tuple[str, str]] = []
                for ref in refs_str.split(","):
                    ref = ref.strip()
                    if "#" in ref:
                        parts = ref.split("#", 1)
                        refs.append((parts[0].strip(), parts[1].strip()))
                if refs:
                    target_map[key] = refs

    async def rebuild_indexes(self) -> None:
        """Full rebuild of all index files from vault contents."""
        self._index = VaultIndex()

        # Parse all long-term files
        for fp in self.long_term_dir.glob("*.md"):
            content = fp.read_text()
            entries = self._parse_long_term_file(content, str(fp))
            for e in entries:
                self._index.add_entry(
                    memory_id=e.get("memory_id", ""),
                    file_path=str(fp),
                    tags=e.get("tags", []),
                    timestamp_str=e.get("date", ""),
                    summary=e.get("content", "")[:80],
                )

        # Parse all short-term files
        for fp in self.short_term_dir.glob("*.md"):
            content = fp.read_text()
            entries = self._parse_daily_log(content, str(fp))
            for e in entries:
                self._index.add_entry(
                    memory_id=e.get("memory_id", ""),
                    file_path=str(fp),
                    tags=e.get("tags", []),
                    timestamp_str=e.get("date", ""),
                    summary=e.get("content", "")[:80],
                )

        # Write index files
        await self._write_topic_index()
        await self._write_entity_index()
        await self._write_timeline_index()

    async def _write_topic_index(self) -> None:
        fp = self.index_dir / "topic_index.md"
        lines = ["# Topic Index\n"]
        for tag in sorted(self._index.topic_map.keys()):
            refs = self._index.topic_map[tag]
            ref_strs = [f"{path}#{mid}" for path, mid in refs]
            lines.append(f"- **{tag}**: {', '.join(ref_strs)}")
        lines.append("")
        async with self._get_lock(str(fp)):
            fp.write_text("\n".join(lines))

    async def _write_entity_index(self) -> None:
        fp = self.index_dir / "entity_index.md"
        lines = ["# Entity Index\n"]
        for entity in sorted(self._index.entity_map.keys()):
            refs = self._index.entity_map[entity]
            ref_strs = [f"{path}#{mid}" for path, mid in refs]
            lines.append(f"- **{entity}**: {', '.join(ref_strs)}")
        lines.append("")
        async with self._get_lock(str(fp)):
            fp.write_text("\n".join(lines))

    async def _write_timeline_index(self) -> None:
        fp = self.index_dir / "timeline.md"
        lines = ["# Timeline\n"]
        for ts, _path, mid, summary in sorted(self._index.timeline, reverse=True):
            lines.append(f"- **{ts}** | {summary} | `{mid}`")
        lines.append("")
        async with self._get_lock(str(fp)):
            fp.write_text("\n".join(lines))

    async def _update_index_files(self, entry: MemoryEntry, file_path: str) -> None:
        """Incrementally update index files with a new entry."""
        # Topic index
        if entry.tags:
            topic_fp = self.index_dir / "topic_index.md"
            async with self._get_lock(str(topic_fp)):
                content = topic_fp.read_text() if topic_fp.exists() else "# Topic Index\n"
                for tag in entry.tags:
                    tag_clean = tag.lower().strip("#")
                    ref = f"{file_path}#{entry.memory_id}"
                    pattern = rf"^(- \*\*{re.escape(tag_clean)}\*\*:\s*)(.+)$"
                    match = re.search(pattern, content, re.MULTILINE)
                    if match:
                        content = content.replace(
                            match.group(0),
                            f"{match.group(1)}{match.group(2)}, {ref}",
                        )
                    else:
                        content = content.rstrip("\n") + f"\n- **{tag_clean}**: {ref}\n"
                topic_fp.write_text(content)

        # Timeline
        timeline_fp = self.index_dir / "timeline.md"
        async with self._get_lock(str(timeline_fp)):
            content = (
                timeline_fp.read_text() if timeline_fp.exists() else "# Timeline\n"
            )
            ts = entry.timestamp.strftime("%Y-%m-%d %H:%M")
            line = f"- **{ts}** | {entry.content[:80]} | `{entry.memory_id}`"
            # Insert after header
            parts = content.split("\n", 2)
            if len(parts) >= 2:
                content = parts[0] + "\n" + line + "\n" + "\n".join(parts[1:])
            else:
                content += "\n" + line + "\n"
            timeline_fp.write_text(content)

    # ------------------------------------------------------------------
    # Markdown parsing
    # ------------------------------------------------------------------

    def _parse_daily_log(
        self, content: str, file_path: str = ""
    ) -> List[Dict[str, Any]]:
        """Parse a daily log markdown file into entry dicts."""
        entries: List[Dict[str, Any]] = []
        # Extract date from header or filename
        date_str = ""
        header_match = re.search(r"# Daily Memory Log:\s*(\d{4}-\d{2}-\d{2})", content)
        if header_match:
            date_str = header_match.group(1)
        elif file_path:
            stem = Path(file_path).stem
            if re.match(r"\d{4}-\d{2}-\d{2}", stem):
                date_str = stem

        # Split by entry headers: ### HH:MM | source | confidence
        entry_pattern = re.compile(
            r"^### (\d{2}:\d{2})\s*\|\s*(\w+)\s*\|\s*([\d.]+)\s*$",
            re.MULTILINE,
        )
        matches = list(entry_pattern.finditer(content))

        for i, m in enumerate(matches):
            time_str = m.group(1)
            source = m.group(2)
            confidence = float(m.group(3))

            # Extract body until next entry or end
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[start:end].strip()

            # Parse tags
            tags: List[str] = []
            tags_match = re.search(r"\*\*Tags:\*\*\s*(.+)", body)
            if tags_match:
                tags = [
                    t.strip().strip("#")
                    for t in tags_match.group(1).split("#")
                    if t.strip()
                ]

            # Parse category
            category = "personal"
            cat_match = re.search(r"\*\*Category:\*\*\s*(\w+)", body)
            if cat_match:
                category = cat_match.group(1)

            # Parse promoted status
            promoted = "**Promoted**" in body

            # Parse memory_id
            memory_id = ""
            id_match = re.search(r"`([a-f0-9]{12})`", body)
            if id_match:
                memory_id = id_match.group(1)

            # Extract the actual content (lines that aren't metadata)
            content_lines = []
            for line in body.split("\n"):
                line_stripped = line.strip()
                if line_stripped.startswith("- **Tags:"):
                    continue
                if line_stripped.startswith("- **Category:"):
                    continue
                if line_stripped.startswith("> **Promoted**"):
                    continue
                if line_stripped.startswith("`") and line_stripped.endswith("`"):
                    continue
                if line_stripped.startswith("---"):
                    continue
                if line_stripped.startswith("_") and line_stripped.endswith("_"):
                    continue
                if line_stripped:
                    content_lines.append(line_stripped)

            entry_content = " ".join(content_lines)

            entries.append(
                {
                    "content": entry_content,
                    "time": time_str,
                    "date": date_str,
                    "source": source,
                    "confidence": confidence,
                    "tags": tags,
                    "category": category,
                    "promoted": promoted,
                    "memory_id": memory_id,
                    "file_path": file_path,
                }
            )

        return entries

    def _parse_long_term_file(
        self, content: str, file_path: str = ""
    ) -> List[Dict[str, Any]]:
        """Parse a long-term category markdown file into entry dicts."""
        entries: List[Dict[str, Any]] = []
        current_section = ""

        for line in content.split("\n"):
            # Track sections (## headings)
            section_match = re.match(r"^## (.+)$", line)
            if section_match:
                current_section = section_match.group(1).strip()
                continue

            # Parse entry lines: - Content text [2026-03-10]
            entry_match = re.match(r"^- (.+?)\s*\[(\d{4}-\d{2}-\d{2})\]\s*$", line)
            if entry_match:
                entry_content = entry_match.group(1).strip()
                entry_date = entry_match.group(2)

                # Extract memory_id if present
                memory_id = ""
                id_match = re.search(r"`([a-f0-9]{12})`", entry_content)
                if id_match:
                    memory_id = id_match.group(1)
                    entry_content = entry_content.replace(
                        f" `{memory_id}`", ""
                    ).strip()

                # Extract tags if present
                tags: List[str] = []
                tag_matches = re.findall(r"#(\w+)", entry_content)
                if tag_matches:
                    tags = tag_matches

                entries.append(
                    {
                        "content": entry_content,
                        "date": entry_date,
                        "section": current_section,
                        "memory_id": memory_id,
                        "tags": tags,
                        "file_path": file_path,
                    }
                )

        return entries

    # ------------------------------------------------------------------
    # Markdown writing
    # ------------------------------------------------------------------

    async def _append_to_daily_log(self, entry: MemoryEntry) -> None:
        """Append a formatted entry to today's daily log file."""
        date_str = entry.timestamp.strftime("%Y-%m-%d")
        fp = self.short_term_dir / f"{date_str}.md"

        async with self._get_lock(str(fp)):
            if not fp.exists():
                fp.write_text(f"# Daily Memory Log: {date_str}\n\n")

            content = fp.read_text()

            time_str = entry.timestamp.strftime("%H:%M")
            tags_str = " ".join(f"#{t}" for t in entry.tags) if entry.tags else ""

            block = f"\n### {time_str} | {entry.source} | {entry.confidence}\n"
            if tags_str:
                block += f"- **Tags:** {tags_str}\n"
            block += f"- **Category:** {entry.category}\n"
            block += f"{entry.content}\n"
            block += f"`{entry.memory_id}`\n"

            # Remove old footer if present
            content = re.sub(
                r"\n---\n_\d+ entries?\. Last updated [\d:]+\._\n?$",
                "",
                content,
            )

            content += block

            # Count entries and add footer
            entry_count = content.count("### ")
            content += (
                f"\n---\n_{entry_count} entries. Last updated {time_str}._\n"
            )

            fp.write_text(content)

    async def _append_to_long_term(
        self,
        entry: MemoryEntry,
        target_file: Path,
        section: Optional[str] = None,
    ) -> None:
        """Append an entry under the correct heading in a long-term file."""
        date_str = entry.timestamp.strftime("%Y-%m-%d")
        line = f"- {entry.content} [{date_str}]\n"

        async with self._get_lock(str(target_file)):
            content = target_file.read_text()

            # Update footer
            old_footer_match = re.search(
                r"\n---\n_Last updated: .+?\. (\d+) entries?\._\n?$",
                content,
            )
            old_count = 0
            if old_footer_match:
                old_count = int(old_footer_match.group(1))
                content = re.sub(
                    r"\n---\n_Last updated: .+?\. \d+ entries?\._\n?$",
                    "",
                    content,
                )

            target_section = section or entry.section
            if target_section:
                # Find or create the section
                section_header = f"## {target_section}"
                if section_header in content:
                    # Insert after section header
                    idx = content.index(section_header) + len(section_header)
                    # Find end of line
                    newline_idx = content.index("\n", idx)
                    content = (
                        content[: newline_idx + 1]
                        + line
                        + content[newline_idx + 1 :]
                    )
                else:
                    # Create new section before footer area
                    content = content.rstrip("\n") + f"\n\n{section_header}\n{line}"
            else:
                # Append before footer
                content = content.rstrip("\n") + f"\n{line}"

            new_count = old_count + 1
            content += (
                f"\n---\n_Last updated: {date_str}. {new_count} entries._\n"
            )

            target_file.write_text(content)

    async def _mark_promoted_in_daily_log(self, entry: MemoryEntry) -> None:
        """Add a promotion marker to the entry in its daily log."""
        date_str = entry.timestamp.strftime("%Y-%m-%d")
        fp = self.short_term_dir / f"{date_str}.md"
        if not fp.exists():
            return

        category = entry.category
        fname = CATEGORY_FILE_MAP.get(category, f"{category}.md")

        async with self._get_lock(str(fp)):
            content = fp.read_text()
            marker = f"> **Promoted** -> long_term/{fname}\n"
            target = f"`{entry.memory_id}`\n"
            if target in content and marker not in content:
                content = content.replace(target, target + marker)
                fp.write_text(content)

    async def _rewrite_long_term_file(
        self,
        target_file: Path,
        category: str,
        entries: List[Dict[str, Any]],
    ) -> None:
        """Completely rewrite a long-term file with the given entries."""
        title = category.replace("_", " ").title()
        lines = [f"# {title}\n"]

        # Group by section
        by_section: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for e in entries:
            sec = e.get("section", "General")
            by_section[sec].append(e)

        for sec in sorted(by_section.keys()):
            lines.append(f"\n## {sec}")
            for e in by_section[sec]:
                date_str = e.get("date", datetime.datetime.now().strftime("%Y-%m-%d"))
                lines.append(f"- {e['content']} [{date_str}]")

        date_now = datetime.datetime.now().strftime("%Y-%m-%d")
        lines.append(f"\n---\n_Last updated: {date_now}. {len(entries)} entries._\n")

        async with self._get_lock(str(target_file)):
            target_file.write_text("\n".join(lines))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _find_entry_by_id(self, memory_id: str) -> Optional[MemoryEntry]:
        """Search all daily logs for an entry with the given ID."""
        for fp in self.short_term_dir.glob("*.md"):
            async with self._get_lock(str(fp)):
                content = fp.read_text()
            entries = self._parse_daily_log(content, str(fp))
            for e in entries:
                if e.get("memory_id") == memory_id:
                    return MemoryEntry(
                        content=e["content"],
                        timestamp=datetime.datetime.strptime(
                            f"{e['date']} {e.get('time', '00:00')}",
                            "%Y-%m-%d %H:%M",
                        ),
                        source=e.get("source", "conversation"),
                        category=e.get("category", "personal"),
                        tags=e.get("tags", []),
                        confidence=e.get("confidence", 0.8),
                        promoted=e.get("promoted", False),
                        memory_id=memory_id,
                    )
        return None

    async def _log_consolidation(
        self, category: str, original_count: int, final_count: int
    ) -> None:
        """Append to the consolidation log."""
        fp = self.meta_dir / "consolidation_log.md"
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        line = (
            f"- **{now}** | {category} | "
            f"{original_count} -> {final_count} entries\n"
        )
        async with self._get_lock(str(fp)):
            content = fp.read_text() if fp.exists() else "# Consolidation Log\n\n"
            content += line
            fp.write_text(content)
