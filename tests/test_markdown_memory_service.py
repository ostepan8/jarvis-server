"""Tests for MarkdownMemoryService — the markdown-based memory vault."""

import asyncio
import datetime

import pytest

from jarvis.services.markdown_memory import (
    BUILTIN_CATEGORIES,
    MarkdownMemoryService,
    MemoryEntry,
    VaultIndex,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vault(tmp_path):
    """Create a MarkdownMemoryService backed by a temporary directory."""
    return MarkdownMemoryService(vault_dir=str(tmp_path), auto_promote=False)


@pytest.fixture
def vault_auto_promote(tmp_path):
    """Vault with auto-promotion enabled."""
    return MarkdownMemoryService(vault_dir=str(tmp_path), auto_promote=True)


# ---------------------------------------------------------------------------
# Vault initialisation
# ---------------------------------------------------------------------------


class TestVaultInit:
    def test_directory_structure_created(self, tmp_path):
        svc = MarkdownMemoryService(vault_dir=str(tmp_path))
        assert (tmp_path / "short_term").is_dir()
        assert (tmp_path / "long_term").is_dir()
        assert (tmp_path / "long_term" / "custom").is_dir()
        assert (tmp_path / "indexes").is_dir()
        assert (tmp_path / "meta").is_dir()

    def test_default_long_term_files_seeded(self, tmp_path):
        svc = MarkdownMemoryService(vault_dir=str(tmp_path))
        for cat in BUILTIN_CATEGORIES:
            fp = tmp_path / "long_term" / f"{cat}.md"
            assert fp.exists(), f"Missing long-term file: {cat}.md"
            content = fp.read_text()
            assert content.startswith("# ")

    def test_index_files_seeded(self, tmp_path):
        svc = MarkdownMemoryService(vault_dir=str(tmp_path))
        for name in ["topic_index.md", "entity_index.md", "timeline.md"]:
            fp = tmp_path / "indexes" / name
            assert fp.exists(), f"Missing index file: {name}"

    def test_meta_files_seeded(self, tmp_path):
        svc = MarkdownMemoryService(vault_dir=str(tmp_path))
        for name in ["consolidation_log.md", "stats.md"]:
            fp = tmp_path / "meta" / name
            assert fp.exists(), f"Missing meta file: {name}"

    def test_idempotent_init(self, tmp_path):
        """Re-initialising the vault does not overwrite existing files."""
        svc1 = MarkdownMemoryService(vault_dir=str(tmp_path))
        fp = tmp_path / "long_term" / "personal.md"
        fp.write_text("# Personal\n\n## Food\n- Loves pizza [2026-01-01]\n")

        svc2 = MarkdownMemoryService(vault_dir=str(tmp_path))
        assert "pizza" in fp.read_text()


# ---------------------------------------------------------------------------
# Store operations
# ---------------------------------------------------------------------------


class TestStore:
    @pytest.mark.asyncio
    async def test_store_creates_daily_log(self, vault):
        entry = await vault.store("User likes jazz", category="preferences", tags=["music"])
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{today}.md"
        assert fp.exists()
        content = fp.read_text()
        assert "User likes jazz" in content
        assert "### " in content

    @pytest.mark.asyncio
    async def test_store_returns_entry_with_id(self, vault):
        entry = await vault.store("Test memory")
        assert isinstance(entry, MemoryEntry)
        assert len(entry.memory_id) == 12
        assert entry.content == "Test memory"

    @pytest.mark.asyncio
    async def test_store_appends_multiple_entries(self, vault):
        await vault.store("First entry")
        await vault.store("Second entry")
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{today}.md"
        content = fp.read_text()
        assert "First entry" in content
        assert "Second entry" in content
        assert content.count("### ") == 2

    @pytest.mark.asyncio
    async def test_store_records_tags(self, vault):
        await vault.store("Pizza is great", tags=["food", "pizza"])
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{today}.md"
        content = fp.read_text()
        assert "#food" in content
        assert "#pizza" in content

    @pytest.mark.asyncio
    async def test_store_records_category(self, vault):
        await vault.store("My cat", category="personal")
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{today}.md"
        content = fp.read_text()
        assert "**Category:** personal" in content

    @pytest.mark.asyncio
    async def test_store_records_source_and_confidence(self, vault):
        await vault.store("Explicit note", source="explicit", confidence=1.0)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{today}.md"
        content = fp.read_text()
        assert "explicit" in content
        assert "1.0" in content

    @pytest.mark.asyncio
    async def test_store_unique_ids(self, vault):
        e1 = await vault.store("Entry one")
        e2 = await vault.store("Entry two")
        assert e1.memory_id != e2.memory_id

    @pytest.mark.asyncio
    async def test_store_footer_updates(self, vault):
        await vault.store("One")
        await vault.store("Two")
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{today}.md"
        content = fp.read_text()
        assert "2 entries" in content


# ---------------------------------------------------------------------------
# Auto-promotion
# ---------------------------------------------------------------------------


class TestAutoPromotion:
    @pytest.mark.asyncio
    async def test_explicit_source_promotes(self, vault_auto_promote):
        entry = await vault_auto_promote.store(
            "My birthday is March 5th",
            category="personal",
            source="explicit",
            confidence=1.0,
        )
        assert entry.promoted is True
        fp = vault_auto_promote.long_term_dir / "personal.md"
        content = fp.read_text()
        assert "My birthday is March 5th" in content

    @pytest.mark.asyncio
    async def test_high_confidence_builtin_category_promotes(self, vault_auto_promote):
        entry = await vault_auto_promote.store(
            "Favourite colour is blue",
            category="preferences",
            confidence=0.95,
        )
        assert entry.promoted is True

    @pytest.mark.asyncio
    async def test_low_confidence_does_not_promote(self, vault_auto_promote):
        entry = await vault_auto_promote.store(
            "Maybe likes red",
            category="preferences",
            confidence=0.5,
        )
        assert entry.promoted is False

    @pytest.mark.asyncio
    async def test_promotion_marks_daily_log(self, vault_auto_promote):
        entry = await vault_auto_promote.store(
            "Dentist on Friday",
            category="health",
            source="explicit",
            confidence=1.0,
        )
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fp = vault_auto_promote.short_term_dir / f"{today}.md"
        content = fp.read_text()
        assert "**Promoted**" in content


# ---------------------------------------------------------------------------
# Recall / search
# ---------------------------------------------------------------------------


class TestRecall:
    @pytest.mark.asyncio
    async def test_exact_match_scores_highest(self, vault):
        await vault.store("Favourite pizza place is Lou Malnatis")
        await vault.store("I bought pizza yesterday")
        results = await vault.recall("Lou Malnatis")
        assert len(results) >= 1
        assert "Lou Malnatis" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_keyword_match(self, vault):
        await vault.store("Loves Italian food", tags=["food"])
        results = await vault.recall("food")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_category_filter(self, vault):
        await vault.store("Java developer", category="skills")
        await vault.store("Favourite pizza", category="preferences")
        results = await vault.recall("favourite", categories=["preferences"])
        # Should not include the skills entry in the long-term search
        # but short-term has both
        for r in results:
            if "long_term" in r.get("file_path", ""):
                assert "skills" not in r.get("file_path", "")

    @pytest.mark.asyncio
    async def test_empty_vault_returns_empty(self, vault):
        results = await vault.recall("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_top_k_limit(self, vault):
        for i in range(10):
            await vault.store(f"Memory about pizza number {i}", tags=["pizza"])
        results = await vault.recall("pizza", top_k=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_search_long_term(self, vault):
        """Directly promoted content should be searchable."""
        entry = await vault.store(
            "Best coffee at Blue Bottle",
            category="preferences",
            source="explicit",
            confidence=1.0,
        )
        # Manually promote since auto_promote is off
        await vault.promote(entry.memory_id, "preferences", "Coffee", _entry=entry)
        results = await vault.recall("Blue Bottle")
        assert len(results) >= 1


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


class TestPromotion:
    @pytest.mark.asyncio
    async def test_promote_adds_to_long_term(self, vault):
        entry = await vault.store("Loves jazz", category="preferences", tags=["music"])
        success = await vault.promote(
            entry.memory_id, "preferences", "Music", _entry=entry
        )
        assert success is True
        fp = vault.long_term_dir / "preferences.md"
        content = fp.read_text()
        assert "Loves jazz" in content

    @pytest.mark.asyncio
    async def test_promote_creates_section(self, vault):
        entry = await vault.store("Sushi fan", category="preferences")
        await vault.promote(entry.memory_id, "preferences", "Food", _entry=entry)
        fp = vault.long_term_dir / "preferences.md"
        content = fp.read_text()
        assert "## Food" in content
        assert "Sushi fan" in content

    @pytest.mark.asyncio
    async def test_promote_updates_index(self, vault):
        entry = await vault.store("Jazz lover", tags=["music", "jazz"])
        await vault.promote(entry.memory_id, "preferences", _entry=entry)
        hits = vault._index.search_topics("jazz")
        assert len(hits) >= 1

    @pytest.mark.asyncio
    async def test_promote_nonexistent_id_returns_false(self, vault):
        result = await vault.promote("nonexistent123")
        assert result is False

    @pytest.mark.asyncio
    async def test_promote_creates_custom_category(self, vault):
        entry = await vault.store("Drives a Tesla", category="vehicles")
        await vault.promote(entry.memory_id, "vehicles", "Cars", _entry=entry)
        fp = vault.custom_dir / "vehicles.md"
        assert fp.exists()
        content = fp.read_text()
        assert "Drives a Tesla" in content

    @pytest.mark.asyncio
    async def test_promote_marks_daily_log(self, vault):
        entry = await vault.store("Test entry", category="personal")
        await vault.promote(entry.memory_id, "personal", _entry=entry)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{today}.md"
        content = fp.read_text()
        assert "**Promoted**" in content


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------


class TestConsolidation:
    @pytest.mark.asyncio
    async def test_dedup_without_ai(self, vault):
        # Write duplicates directly
        fp = vault.long_term_dir / "preferences.md"
        fp.write_text(
            "# Preferences\n\n"
            "## Food\n"
            "- Loves pizza [2026-03-01]\n"
            "- Loves pizza [2026-03-05]\n"
            "- Hates broccoli [2026-03-02]\n"
            "\n---\n_Last updated: 2026-03-05. 3 entries._\n"
        )
        result = await vault.consolidate("preferences")
        assert result["removed_duplicates"] == 1
        assert result["consolidated"] == 2

    @pytest.mark.asyncio
    async def test_consolidation_logged(self, vault):
        fp = vault.long_term_dir / "preferences.md"
        fp.write_text(
            "# Preferences\n\n"
            "- Duplicate [2026-03-01]\n"
            "- Duplicate [2026-03-02]\n"
            "\n---\n_Last updated: 2026-03-02. 2 entries._\n"
        )
        await vault.consolidate("preferences")
        log_fp = vault.meta_dir / "consolidation_log.md"
        content = log_fp.read_text()
        assert "preferences" in content

    @pytest.mark.asyncio
    async def test_consolidate_nonexistent_category(self, vault):
        result = await vault.consolidate("nonexistent_xyz")
        assert result["consolidated"] == 0


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------


class TestPruning:
    @pytest.mark.asyncio
    async def test_prune_removes_old_logs(self, vault):
        old_date = (
            datetime.datetime.now()
            - datetime.timedelta(days=vault.short_term_ttl_days + 1)
        ).strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{old_date}.md"
        fp.write_text(
            f"# Daily Memory Log: {old_date}\n\n"
            f"### 10:00 | conversation | 0.5\n"
            f"- **Category:** personal\n"
            f"Old entry\n"
            f"`aabbccddee11`\n"
        )
        result = await vault.prune_short_term()
        assert result["pruned_files"] == 1
        assert not fp.exists()

    @pytest.mark.asyncio
    async def test_prune_promotes_high_confidence_before_deleting(self, vault):
        old_date = (
            datetime.datetime.now()
            - datetime.timedelta(days=vault.short_term_ttl_days + 1)
        ).strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{old_date}.md"
        fp.write_text(
            f"# Daily Memory Log: {old_date}\n\n"
            f"### 10:00 | explicit | 0.95\n"
            f"- **Category:** personal\n"
            f"High confidence memory\n"
            f"`aabbccddee22`\n"
        )
        result = await vault.prune_short_term()
        assert result["promoted_before_prune"] == 1
        # Verify it was promoted to long-term
        lt_content = (vault.long_term_dir / "personal.md").read_text()
        assert "High confidence memory" in lt_content

    @pytest.mark.asyncio
    async def test_prune_keeps_recent_logs(self, vault):
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{today}.md"
        fp.write_text(f"# Daily Memory Log: {today}\n\n### 10:00 | conversation | 0.5\nRecent\n`aabb11223344`\n")
        result = await vault.prune_short_term()
        assert result["pruned_files"] == 0
        assert fp.exists()

    @pytest.mark.asyncio
    async def test_prune_respects_ttl(self, tmp_path):
        svc = MarkdownMemoryService(
            vault_dir=str(tmp_path), short_term_ttl_days=3
        )
        # 2 days ago — within TTL
        recent_date = (
            datetime.datetime.now() - datetime.timedelta(days=2)
        ).strftime("%Y-%m-%d")
        fp_recent = svc.short_term_dir / f"{recent_date}.md"
        fp_recent.write_text(f"# Daily Memory Log: {recent_date}\n\n")

        # 5 days ago — outside TTL
        old_date = (
            datetime.datetime.now() - datetime.timedelta(days=5)
        ).strftime("%Y-%m-%d")
        fp_old = svc.short_term_dir / f"{old_date}.md"
        fp_old.write_text(f"# Daily Memory Log: {old_date}\n\n")

        result = await svc.prune_short_term()
        assert result["pruned_files"] == 1
        assert fp_recent.exists()
        assert not fp_old.exists()


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------


class TestIndexes:
    @pytest.mark.asyncio
    async def test_rebuild_indexes(self, vault):
        # Store some entries
        await vault.store("Loves jazz", tags=["music", "jazz"])
        entry = await vault.store("Coffee addict", tags=["coffee", "food"])
        await vault.promote(entry.memory_id, "preferences", "Drinks", _entry=entry)

        await vault.rebuild_indexes()

        topic_fp = vault.index_dir / "topic_index.md"
        content = topic_fp.read_text()
        assert "jazz" in content or "music" in content

    @pytest.mark.asyncio
    async def test_incremental_index_update(self, vault):
        await vault.store("Tag test", tags=["testtag"])
        topic_fp = vault.index_dir / "topic_index.md"
        # Indexes are updated on promote, but topic_map is in-memory
        hits = vault._index.search_topics("testtag")
        assert len(hits) >= 1

    @pytest.mark.asyncio
    async def test_index_cache_cleared_on_rebuild(self, vault):
        await vault.store("Old data", tags=["stale"])
        old_hits = vault._index.search_topics("stale")
        assert len(old_hits) >= 1

        # Clear the vault content but keep structure
        for fp in vault.short_term_dir.glob("*.md"):
            fp.unlink()

        await vault.rebuild_indexes()
        new_hits = vault._index.search_topics("stale")
        assert len(new_hits) == 0


# ---------------------------------------------------------------------------
# Browse & stats
# ---------------------------------------------------------------------------


class TestBrowseAndStats:
    @pytest.mark.asyncio
    async def test_browse_vault_structure(self, vault):
        await vault.store("Entry one")
        await vault.store("Entry two")
        overview = await vault.browse_vault()
        assert "short_term" in overview
        assert "long_term" in overview
        assert "custom" in overview
        # Should have at least one short-term file
        assert len(overview["short_term"]) >= 1

    @pytest.mark.asyncio
    async def test_get_stats(self, vault):
        await vault.store("Stat test")
        stats = await vault.get_stats()
        assert stats["short_term_entries"] >= 1
        assert "total_entries" in stats
        assert "vault_dir" in stats
        assert stats["categories"] == BUILTIN_CATEGORIES

    @pytest.mark.asyncio
    async def test_stats_empty_vault(self, vault):
        stats = await vault.get_stats()
        assert stats["short_term_entries"] == 0
        assert stats["long_term_entries"] == 0


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestParsing:
    def test_parse_daily_log(self, vault):
        content = (
            "# Daily Memory Log: 2026-03-10\n\n"
            "### 10:32 | conversation | 0.95\n"
            "- **Tags:** #food #pizza\n"
            "- **Category:** preferences\n"
            "Favourite pizza place is Lou Malnatis\n"
            "`abc123def456`\n"
            "\n---\n_1 entries. Last updated 10:32._\n"
        )
        entries = vault._parse_daily_log(content, "test.md")
        assert len(entries) == 1
        e = entries[0]
        assert "Lou Malnatis" in e["content"]
        assert e["date"] == "2026-03-10"
        assert e["source"] == "conversation"
        assert e["confidence"] == 0.95
        assert "food" in e["tags"]
        assert e["category"] == "preferences"
        assert e["memory_id"] == "abc123def456"

    def test_parse_long_term_file(self, vault):
        content = (
            "# Preferences\n\n"
            "## Food\n"
            "- Loves pizza [2026-03-10]\n"
            "- Hates broccoli [2026-02-28]\n"
            "\n## Music\n"
            "- Listens to jazz [2026-03-05]\n"
            "\n---\n_Last updated: 2026-03-10. 3 entries._\n"
        )
        entries = vault._parse_long_term_file(content, "preferences.md")
        assert len(entries) == 3
        assert entries[0]["content"] == "Loves pizza"
        assert entries[0]["date"] == "2026-03-10"
        assert entries[0]["section"] == "Food"
        assert entries[2]["section"] == "Music"

    def test_parse_daily_log_multiple_entries(self, vault):
        content = (
            "# Daily Memory Log: 2026-03-10\n\n"
            "### 10:00 | explicit | 1.0\n"
            "- **Category:** personal\n"
            "First entry\n"
            "`aaa111bbb222`\n"
            "\n"
            "### 14:30 | conversation | 0.8\n"
            "- **Tags:** #work\n"
            "- **Category:** work\n"
            "Second entry\n"
            "`ccc333ddd444`\n"
            "\n---\n_2 entries. Last updated 14:30._\n"
        )
        entries = vault._parse_daily_log(content, "test.md")
        assert len(entries) == 2
        assert entries[0]["memory_id"] == "aaa111bbb222"
        assert entries[1]["memory_id"] == "ccc333ddd444"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_content_stored(self, vault):
        entry = await vault.store("")
        assert entry.content == ""

    @pytest.mark.asyncio
    async def test_special_characters_in_content(self, vault):
        entry = await vault.store("User said: 'hello [world]' & <stuff>")
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fp = vault.short_term_dir / f"{today}.md"
        content = fp.read_text()
        assert "'hello [world]'" in content

    @pytest.mark.asyncio
    async def test_concurrent_writes(self, vault):
        """Multiple concurrent stores should not corrupt the file."""
        tasks = [vault.store(f"Concurrent entry {i}") for i in range(5)]
        entries = await asyncio.gather(*tasks)
        assert len(entries) == 5
        # All IDs unique
        ids = [e.memory_id for e in entries]
        assert len(set(ids)) == 5

    @pytest.mark.asyncio
    async def test_vault_index_persists_across_instances(self, tmp_path):
        """Indexes written by one instance should be loadable by another."""
        svc1 = MarkdownMemoryService(vault_dir=str(tmp_path))
        entry = await svc1.store("Jazz fan", tags=["jazz", "music"])
        await svc1.promote(entry.memory_id, "preferences", "Music", _entry=entry)
        await svc1.rebuild_indexes()

        svc2 = MarkdownMemoryService(vault_dir=str(tmp_path))
        hits = svc2._index.search_topics("jazz")
        assert len(hits) >= 1


# ---------------------------------------------------------------------------
# VaultIndex unit tests
# ---------------------------------------------------------------------------


class TestVaultIndex:
    def test_add_and_search_topics(self):
        idx = VaultIndex()
        idx.add_entry("id1", "file1.md", ["music", "jazz"])
        idx.add_entry("id2", "file2.md", ["food", "pizza"])
        hits = idx.search_topics("jazz")
        assert len(hits) == 1
        assert hits[0] == ("file1.md", "id1")

    def test_add_and_search_entities(self):
        idx = VaultIndex()
        idx.add_entry("id1", "file1.md", [], entities=["Alice", "Bob"])
        hits = idx.search_entities("alice")
        assert len(hits) == 1
        assert hits[0] == ("file1.md", "id1")

    def test_search_returns_empty_for_no_match(self):
        idx = VaultIndex()
        idx.add_entry("id1", "file1.md", ["music"])
        assert idx.search_topics("sports") == []
        assert idx.search_entities("nobody") == []

    def test_deduplicates_results(self):
        idx = VaultIndex()
        idx.add_entry("id1", "file1.md", ["jazz", "music"])
        # Both tags partial-match "jazz music" query tokens
        hits = idx.search_topics("jazz music")
        # Should contain id1 only once (deduplicated)
        file_id_pairs = [(h[0], h[1]) for h in hits]
        assert file_id_pairs.count(("file1.md", "id1")) == 1
