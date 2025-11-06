#!/usr/bin/env python3
"""Script to clear all Jarvis log files without affecting other data."""

import os
import sqlite3
import sys
from pathlib import Path


def clear_log_database(db_path: str) -> bool:
    """Clear all logs from a specific database file."""
    if not os.path.exists(db_path):
        print(f"  Database not found: {db_path} (skipping)")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get count before deletion
        cursor.execute("SELECT COUNT(*) FROM logs")
        count = cursor.fetchone()[0]

        # Clear all logs
        cursor.execute("DELETE FROM logs")
        conn.commit()

        # Vacuum to reclaim disk space
        conn.execute("VACUUM")
        conn.close()

        print(f"  Cleared {count} log entries from {db_path}")
        return True
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            print(f"  No logs table found in {db_path} (skipping)")
            return False
        else:
            print(f"  Error clearing {db_path}: {e}")
            return False
    except Exception as e:
        print(f"  Error clearing {db_path}: {e}")
        return False


def main():
    """Clear all Jarvis log files."""
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent

    print("Clearing Jarvis log files...")
    print()

    # List of log database files to clear
    log_dbs = [
        str(root_dir / "jarvis_logs.db"),
        str(root_dir / "server" / "jarvis_logs.db"),
    ]

    cleared_count = 0
    for db_path in log_dbs:
        if clear_log_database(db_path):
            cleared_count += 1

    # Also remove SQLite WAL and SHM files (SQLite auxiliary files)
    # These will be recreated automatically if needed
    auxiliary_files = [
        root_dir / "jarvis_logs.db-shm",
        root_dir / "jarvis_logs.db-wal",
        root_dir / "server" / "jarvis_logs.db-shm",
        root_dir / "server" / "jarvis_logs.db-wal",
    ]

    print()
    print("Cleaning up SQLite auxiliary files...")
    for aux_file in auxiliary_files:
        if aux_file.exists():
            try:
                aux_file.unlink()
                print(f"  Removed {aux_file}")
            except Exception as e:
                print(f"  Warning: Could not remove {aux_file}: {e}")

    print()
    if cleared_count > 0:
        print(f"✓ Successfully cleared logs from {cleared_count} database(s)")
    else:
        print("No log databases were found or cleared")

    print()
    print("Note: Memory databases (vector memory, fact memory) were NOT touched.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError: {e}", file=sys.stderr)
        sys.exit(1)
