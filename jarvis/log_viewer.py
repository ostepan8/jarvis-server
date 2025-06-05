import argparse
import sqlite3
import time
from cmd import Cmd
from typing import Any


class LogViewer(Cmd):
    """Interactive viewer for Jarvis logs stored in SQLite."""

    prompt = "(logs) "
    intro = "Jarvis Log Viewer. Type 'help' or '?' for commands."

    def __init__(self, db_path: str = "jarvis_logs.db") -> None:
        super().__init__()
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def do_show(self, arg: str) -> None:
        """Show last N log entries. Usage: show [N]"""
        try:
            n = int(arg.strip()) if arg.strip() else 20
        except ValueError:
            print("Usage: show [N]")
            return
        rows = self.conn.execute(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        for row in reversed(rows):
            print(
                f"{row['id']}: {row['timestamp']} [{row['level']}] "
                f"{row['action']} {row['details']}"
            )

    def do_search(self, arg: str) -> None:
        """Search logs for a keyword in action or details. Usage: search KEYWORD"""
        keyword = arg.strip()
        if not keyword:
            print("Usage: search KEYWORD")
            return
        rows = self.conn.execute(
            "SELECT * FROM logs WHERE action LIKE ? OR details LIKE ? ORDER BY id",
            (f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()
        for row in rows:
            print(
                f"{row['id']}: {row['timestamp']} [{row['level']}] "
                f"{row['action']} {row['details']}"
            )

    def _get_last_id(self) -> int:
        cur = self.conn.execute("SELECT MAX(id) FROM logs")
        result = cur.fetchone()
        return result[0] or 0

    def do_follow(self, arg: str) -> None:
        """Continuously display new log entries until interrupted."""
        last_id = self._get_last_id()
        print("Press Ctrl+C to stop following logs.")
        try:
            while True:
                rows = self.conn.execute(
                    "SELECT * FROM logs WHERE id > ? ORDER BY id", (last_id,)
                ).fetchall()
                for row in rows:
                    last_id = row["id"]
                    print(
                        f"{row['id']}: {row['timestamp']} [{row['level']}] "
                        f"{row['action']} {row['details']}"
                    )
                time.sleep(1)
        except KeyboardInterrupt:
            print()

    def do_exit(self, arg: str) -> bool:
        """Exit the log viewer."""
        return True

    do_quit = do_exit


def main(args: Any | None = None) -> None:
    parser = argparse.ArgumentParser(description="Jarvis log viewer")
    parser.add_argument(
        "--db", default="jarvis_logs.db", help="Path to Jarvis SQLite log database"
    )
    parsed = parser.parse_args(args)
    viewer = LogViewer(parsed.db)
    viewer.cmdloop()


if __name__ == "__main__":
    main()
