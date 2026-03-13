"""Tests for the MetricsStore SQLite time-series storage."""

from datetime import datetime, timedelta, timezone

from jarvis.services.metrics_store import MetricsStore


def _make_rows(component, metric_name, values, base_time=None, unit="%", severity="ok"):
    """Helper: generate metric row dicts with sequential timestamps."""
    base = base_time or datetime.now(timezone.utc)
    rows = []
    for i, v in enumerate(values):
        rows.append(
            {
                "timestamp": (base + timedelta(seconds=i)).isoformat(),
                "component": component,
                "metric_name": metric_name,
                "value": v,
                "unit": unit,
                "severity": severity,
                "metadata": {"index": i},
            }
        )
    return rows


# ------------------------------------------------------------------
# Core read/write
# ------------------------------------------------------------------


def test_record_batch_and_query(tmp_path):
    store = MetricsStore(db_path=str(tmp_path / "test.db"))
    try:
        rows = _make_rows("cpu", "cpu_overall", [10.0, 20.0, 30.0])
        inserted = store.record_batch(rows)
        assert inserted == 3

        results = store.query("cpu")
        assert len(results) == 3
        # Results are ordered DESC by timestamp, so newest first
        assert results[0]["value"] == 30.0
        assert results[2]["value"] == 10.0
        # Metadata should be parsed back to dict
        assert isinstance(results[0]["metadata"], dict)
        assert results[0]["metadata"]["index"] == 2
    finally:
        store.close()


def test_query_latest(tmp_path):
    store = MetricsStore(db_path=str(tmp_path / "test.db"))
    try:
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        rows = _make_rows("memory", "ram_percent", [40.0, 55.0, 72.0], base_time=base)
        store.record_batch(rows)

        latest = store.query_latest("memory")
        assert latest is not None
        assert latest["value"] == 72.0
        assert latest["metric_name"] == "ram_percent"

        # With metric_name filter
        latest_filtered = store.query_latest("memory", metric_name="ram_percent")
        assert latest_filtered is not None
        assert latest_filtered["value"] == 72.0

        # Non-existent component
        assert store.query_latest("nonexistent") is None
    finally:
        store.close()


def test_query_with_filters(tmp_path):
    store = MetricsStore(db_path=str(tmp_path / "test.db"))
    try:
        base = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
        cpu_rows = _make_rows("cpu", "cpu_overall", [10.0, 20.0, 30.0], base_time=base)
        mem_rows = _make_rows("cpu", "cpu_temp", [60.0, 65.0], base_time=base)
        store.record_batch(cpu_rows + mem_rows)

        # Filter by metric_name
        overall = store.query("cpu", metric_name="cpu_overall")
        assert len(overall) == 3

        temp = store.query("cpu", metric_name="cpu_temp")
        assert len(temp) == 2

        # Filter by time range — only the first 2 seconds
        start = base.isoformat()
        end = (base + timedelta(seconds=1)).isoformat()
        ranged = store.query("cpu", metric_name="cpu_overall", start=start, end=end)
        assert len(ranged) == 2

        # Limit
        limited = store.query("cpu", limit=2)
        assert len(limited) == 2
    finally:
        store.close()


def test_query_aggregated(tmp_path):
    store = MetricsStore(db_path=str(tmp_path / "test.db"))
    try:
        # Directly insert hourly rollup data
        with store._lock:
            store._conn.execute(
                """INSERT INTO metrics_hourly
                   (hour, component, metric_name, min_value, max_value, avg_value, sample_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("2026-03-10T10:00:00", "cpu", "cpu_overall", 5.0, 95.0, 50.0, 120),
            )
            store._conn.execute(
                """INSERT INTO metrics_hourly
                   (hour, component, metric_name, min_value, max_value, avg_value, sample_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("2026-03-10T11:00:00", "cpu", "cpu_overall", 10.0, 80.0, 45.0, 115),
            )
            store._conn.commit()

        results = store.query_aggregated("cpu")
        assert len(results) == 2
        assert results[0]["hour"] == "2026-03-10T11:00:00"
        assert results[0]["avg_value"] == 45.0
        assert results[0]["sample_count"] == 115

        # Filter by metric_name
        filtered = store.query_aggregated("cpu", metric_name="cpu_overall")
        assert len(filtered) == 2

        # Filter by time range
        ranged = store.query_aggregated(
            "cpu", start="2026-03-10T11:00:00", end="2026-03-10T11:00:00"
        )
        assert len(ranged) == 1
        assert ranged[0]["hour"] == "2026-03-10T11:00:00"

        # Non-existent component
        assert store.query_aggregated("nonexistent") == []
    finally:
        store.close()


def test_compact(tmp_path):
    store = MetricsStore(db_path=str(tmp_path / "test.db"))
    try:
        # Insert rows that are definitely older than 24h
        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        old_rows = _make_rows("cpu", "cpu_overall", [10.0, 20.0, 30.0], base_time=old_time)

        # And some fresh rows that should survive
        recent_rows = _make_rows("cpu", "cpu_overall", [50.0, 60.0])

        store.record_batch(old_rows + recent_rows)
        assert len(store.query("cpu", limit=10000)) == 5

        result = store.compact(retention_hours=24)
        assert result["aggregated"] == 1  # one (hour, component, metric_name) group
        assert result["deleted"] == 3     # the three old rows

        # Fresh rows remain
        remaining = store.query("cpu")
        assert len(remaining) == 2

        # Hourly rollup was created
        rollups = store.query_aggregated("cpu", metric_name="cpu_overall")
        assert len(rollups) >= 1
        rollup = rollups[0]
        assert rollup["min_value"] == 10.0
        assert rollup["max_value"] == 30.0
        assert rollup["sample_count"] == 3
    finally:
        store.close()


def test_cleanup(tmp_path):
    store = MetricsStore(db_path=str(tmp_path / "test.db"))
    try:
        # Insert old hourly rollup
        old_hour = (datetime.now(timezone.utc) - timedelta(days=60)).strftime(
            "%Y-%m-%dT%H:00:00"
        )
        recent_hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00:00")

        with store._lock:
            store._conn.execute(
                """INSERT INTO metrics_hourly
                   (hour, component, metric_name, min_value, max_value, avg_value, sample_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (old_hour, "memory", "ram_percent", 30.0, 90.0, 60.0, 60),
            )
            store._conn.execute(
                """INSERT INTO metrics_hourly
                   (hour, component, metric_name, min_value, max_value, avg_value, sample_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (recent_hour, "memory", "ram_percent", 40.0, 80.0, 55.0, 50),
            )
            store._conn.commit()

        deleted = store.cleanup(retention_days=30)
        assert deleted == 1

        # Recent rollup survives
        remaining = store.query_aggregated("memory")
        assert len(remaining) == 1
        assert remaining[0]["hour"] == recent_hour
    finally:
        store.close()


def test_record_batch_empty(tmp_path):
    store = MetricsStore(db_path=str(tmp_path / "test.db"))
    try:
        assert store.record_batch([]) == 0
    finally:
        store.close()


def test_close(tmp_path):
    store = MetricsStore(db_path=str(tmp_path / "test.db"))
    store.close()
    # Double close should not raise
    store.close()
