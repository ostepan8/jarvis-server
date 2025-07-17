import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
from datetime import datetime
import threading
import time
import re
from typing import List, Optional, Tuple
import argparse


class LogViewerGUI:
    """Enhanced GUI-based log viewer for Jarvis logs."""

    def __init__(self, db_path: str = "jarvis_logs.db"):
        self.db_path = db_path
        self.conn = None
        self.following = False
        self.follow_thread = None
        self.last_id = 0

        # Create main window
        self.root = tk.Tk()
        self.root.title(f"Jarvis Log Viewer - {db_path}")
        self.root.geometry("1200x800")

        # Configure styles
        self.setup_styles()

        # Create GUI elements
        self.setup_gui()

        # Connect to database
        self.connect_database()

        # Load initial logs
        self.load_logs()

    def setup_styles(self):
        """Configure ttk styles."""
        style = ttk.Style()

        # Configure treeview colors for different log levels
        style.configure("INFO.Treeview", background="#f0f8ff")
        style.configure("WARNING.Treeview", background="#fff8dc")
        style.configure("ERROR.Treeview", background="#ffe4e1")
        style.configure("DEBUG.Treeview", background="#f5f5f5")

    def setup_gui(self):
        """Create the main GUI layout."""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Top control panel
        self.setup_control_panel(main_frame)

        # Log display area
        self.setup_log_display(main_frame)

        # Bottom status bar
        self.setup_status_bar(main_frame)

    def setup_control_panel(self, parent):
        """Create the control panel with search and filters."""
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        # Search section
        search_frame = ttk.LabelFrame(control_frame, text="Search & Filter", padding=10)
        search_frame.pack(fill=tk.X, pady=(0, 5))

        # Search entry
        ttk.Label(search_frame, text="Search:").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 5)
        )
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(
            search_frame, textvariable=self.search_var, width=30
        )
        self.search_entry.grid(row=0, column=1, padx=(0, 5))
        self.search_entry.bind("<Return>", lambda e: self.search_logs())

        # Search button
        ttk.Button(search_frame, text="Search", command=self.search_logs).grid(
            row=0, column=2, padx=(0, 10)
        )

        # Clear search button
        ttk.Button(search_frame, text="Clear", command=self.clear_search).grid(
            row=0, column=3, padx=(0, 10)
        )

        # Log level filter
        ttk.Label(search_frame, text="Level:").grid(
            row=0, column=4, sticky=tk.W, padx=(10, 5)
        )
        self.level_var = tk.StringVar(value="ALL")
        level_combo = ttk.Combobox(
            search_frame,
            textvariable=self.level_var,
            values=["ALL", "INFO", "WARNING", "ERROR", "DEBUG"],
            state="readonly",
            width=10,
        )
        level_combo.grid(row=0, column=5, padx=(0, 10))
        level_combo.bind("<<ComboboxSelected>>", lambda e: self.filter_logs())

        # Date range
        ttk.Label(search_frame, text="From:").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0)
        )
        self.date_from_var = tk.StringVar()
        self.date_from_entry = ttk.Entry(
            search_frame, textvariable=self.date_from_var, width=20
        )
        self.date_from_entry.grid(row=1, column=1, padx=(0, 5), pady=(5, 0))

        ttk.Label(search_frame, text="To:").grid(
            row=1, column=2, sticky=tk.W, padx=(5, 5), pady=(5, 0)
        )
        self.date_to_var = tk.StringVar()
        self.date_to_entry = ttk.Entry(
            search_frame, textvariable=self.date_to_var, width=20
        )
        self.date_to_entry.grid(row=1, column=3, padx=(0, 5), pady=(5, 0))

        # Control buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X, pady=(5, 0))

        # Left side buttons
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side=tk.LEFT)

        ttk.Button(left_buttons, text="Refresh", command=self.load_logs).pack(
            side=tk.LEFT, padx=(0, 5)
        )

        self.follow_button = ttk.Button(
            left_buttons, text="Follow", command=self.toggle_follow
        )
        self.follow_button.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(left_buttons, text="Export", command=self.export_logs).pack(
            side=tk.LEFT, padx=(0, 5)
        )

        # Right side buttons
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side=tk.RIGHT)

        ttk.Button(
            right_buttons, text="Clear Display", command=self.clear_display
        ).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(right_buttons, text="Change DB", command=self.change_database).pack(
            side=tk.LEFT, padx=(5, 0)
        )

    def setup_log_display(self, parent):
        """Create the log display treeview."""
        # Create frame for treeview and scrollbars
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        # Create treeview
        columns = ("ID", "Timestamp", "Level", "Action", "Details")
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=20
        )

        # Configure columns
        self.tree.heading("ID", text="ID")
        self.tree.heading("Timestamp", text="Timestamp")
        self.tree.heading("Level", text="Level")
        self.tree.heading("Action", text="Action")
        self.tree.heading("Details", text="Details")

        # Configure column widths
        self.tree.column("ID", width=80, minwidth=50)
        self.tree.column("Timestamp", width=180, minwidth=150)
        self.tree.column("Level", width=80, minwidth=60)
        self.tree.column("Action", width=200, minwidth=150)
        self.tree.column("Details", width=600, minwidth=300)

        # Add scrollbars
        v_scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        h_scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview
        )
        self.tree.configure(
            yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set
        )

        # Pack treeview and scrollbars
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        # Bind double-click event
        self.tree.bind("<Double-1>", self.on_item_double_click)

        # Bind right-click for context menu
        self.tree.bind("<Button-3>", self.show_context_menu)

        # Create context menu
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copy Row", command=self.copy_selected_row)
        self.context_menu.add_command(
            label="Copy Details", command=self.copy_selected_details
        )
        self.context_menu.add_separator()
        self.context_menu.add_command(label="View Details", command=self.view_details)

    def setup_status_bar(self, parent):
        """Create the status bar."""
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, pady=(5, 0))

        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)

        # Row count label
        self.row_count_var = tk.StringVar(value="0 rows")
        self.row_count_label = ttk.Label(status_frame, textvariable=self.row_count_var)
        self.row_count_label.pack(side=tk.RIGHT)

    def connect_database(self):
        """Connect to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.update_status(f"Connected to {self.db_path}")
        except sqlite3.Error as e:
            messagebox.showerror(
                "Database Error", f"Failed to connect to database: {e}"
            )
            self.update_status("Database connection failed")

    def load_logs(self, limit: int = 1000):
        """Load logs from the database."""
        if not self.conn:
            return

        try:
            # Clear existing items
            for item in self.tree.get_children():
                self.tree.delete(item)

            # Query database
            query = "SELECT * FROM logs ORDER BY id DESC LIMIT ?"
            rows = self.conn.execute(query, (limit,)).fetchall()

            # Insert rows into treeview
            for row in reversed(rows):
                self.insert_log_row(row)

            self.update_row_count(len(rows))
            self.update_status(f"Loaded {len(rows)} log entries")

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", f"Failed to load logs: {e}")
            self.update_status("Failed to load logs")

    def insert_log_row(self, row):
        """Insert a single log row into the treeview."""
        # Format timestamp
        timestamp = row["timestamp"]

        # Determine row color based on level
        tags = (row["level"].lower(),)

        item = self.tree.insert(
            "",
            "end",
            values=(row["id"], timestamp, row["level"], row["action"], row["details"]),
            tags=tags,
        )

        # Configure row colors
        if row["level"] == "ERROR":
            self.tree.set(item, "Level", "🔴 ERROR")
        elif row["level"] == "WARNING":
            self.tree.set(item, "Level", "🟡 WARNING")
        elif row["level"] == "INFO":
            self.tree.set(item, "Level", "🟢 INFO")
        elif row["level"] == "DEBUG":
            self.tree.set(item, "Level", "🔵 DEBUG")

    def search_logs(self):
        """Search logs based on current filters."""
        if not self.conn:
            return

        search_term = self.search_var.get().strip()
        level_filter = self.level_var.get()
        date_from = self.date_from_var.get().strip()
        date_to = self.date_to_var.get().strip()

        # Build query
        query = "SELECT * FROM logs WHERE 1=1"
        params = []

        # Add search term
        if search_term:
            query += " AND (action LIKE ? OR details LIKE ?)"
            params.extend([f"%{search_term}%", f"%{search_term}%"])

        # Add level filter
        if level_filter != "ALL":
            query += " AND level = ?"
            params.append(level_filter)

        # Add date filters
        if date_from:
            query += " AND timestamp >= ?"
            params.append(date_from)

        if date_to:
            query += " AND timestamp <= ?"
            params.append(date_to)

        query += " ORDER BY id DESC LIMIT 5000"

        try:
            # Clear existing items
            for item in self.tree.get_children():
                self.tree.delete(item)

            # Execute search
            rows = self.conn.execute(query, params).fetchall()

            # Insert results
            for row in reversed(rows):
                self.insert_log_row(row)

            self.update_row_count(len(rows))
            self.update_status(f"Search found {len(rows)} results")

        except sqlite3.Error as e:
            messagebox.showerror("Search Error", f"Search failed: {e}")
            self.update_status("Search failed")

    def clear_search(self):
        """Clear search filters and reload all logs."""
        self.search_var.set("")
        self.level_var.set("ALL")
        self.date_from_var.set("")
        self.date_to_var.set("")
        self.load_logs()

    def filter_logs(self):
        """Apply current filters."""
        self.search_logs()

    def toggle_follow(self):
        """Toggle following new log entries."""
        if self.following:
            self.stop_following()
        else:
            self.start_following()

    def start_following(self):
        """Start following new log entries."""
        if not self.conn:
            return

        self.following = True
        self.follow_button.config(text="Stop Following")
        self.last_id = self.get_last_id()

        # Start follow thread
        self.follow_thread = threading.Thread(target=self.follow_logs, daemon=True)
        self.follow_thread.start()

        self.update_status("Following new log entries...")

    def stop_following(self):
        """Stop following new log entries."""
        self.following = False
        self.follow_button.config(text="Follow")
        self.update_status("Stopped following logs")

    def follow_logs(self):
        """Follow new log entries in a separate thread."""
        while self.following:
            try:
                new_rows = self.conn.execute(
                    "SELECT * FROM logs WHERE id > ? ORDER BY id", (self.last_id,)
                ).fetchall()

                for row in new_rows:
                    self.last_id = row["id"]
                    # Insert at the beginning
                    self.root.after(0, lambda r=row: self.insert_log_row_at_top(r))

                time.sleep(1)
            except sqlite3.Error:
                break

    def insert_log_row_at_top(self, row):
        """Insert a log row at the top of the treeview."""
        # Format timestamp
        timestamp = row["timestamp"]

        # Determine row color based on level
        tags = (row["level"].lower(),)

        item = self.tree.insert(
            "",
            0,
            values=(row["id"], timestamp, row["level"], row["action"], row["details"]),
            tags=tags,
        )

        # Configure row colors
        if row["level"] == "ERROR":
            self.tree.set(item, "Level", "🔴 ERROR")
        elif row["level"] == "WARNING":
            self.tree.set(item, "Level", "🟡 WARNING")
        elif row["level"] == "INFO":
            self.tree.set(item, "Level", "🟢 INFO")
        elif row["level"] == "DEBUG":
            self.tree.set(item, "Level", "🔵 DEBUG")

        # Auto-scroll to top
        self.tree.see(item)

    def get_last_id(self):
        """Get the last log ID from the database."""
        if not self.conn:
            return 0

        try:
            cur = self.conn.execute("SELECT MAX(id) FROM logs")
            result = cur.fetchone()
            return result[0] or 0
        except sqlite3.Error:
            return 0

    def export_logs(self):
        """Export current logs to a file."""
        if not self.tree.get_children():
            messagebox.showwarning("Export", "No logs to export")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )

        if filename:
            try:
                with open(filename, "w", newline="") as f:
                    # Write header
                    f.write("ID,Timestamp,Level,Action,Details\n")

                    # Write data
                    for item in self.tree.get_children():
                        values = self.tree.item(item)["values"]
                        # Escape commas and quotes in CSV
                        escaped_values = [
                            f'"{str(v).replace('"', '""')}"' for v in values
                        ]
                        f.write(",".join(escaped_values) + "\n")

                messagebox.showinfo("Export", f"Logs exported to {filename}")
                self.update_status(f"Exported logs to {filename}")

            except IOError as e:
                messagebox.showerror("Export Error", f"Failed to export logs: {e}")

    def clear_display(self):
        """Clear the log display."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.update_row_count(0)
        self.update_status("Display cleared")

    def change_database(self):
        """Change the database file."""
        filename = filedialog.askopenfilename(
            title="Select Jarvis Log Database",
            filetypes=[("Database files", "*.db"), ("All files", "*.*")],
        )

        if filename:
            if self.conn:
                self.conn.close()

            self.db_path = filename
            self.root.title(f"Jarvis Log Viewer - {filename}")
            self.connect_database()
            self.load_logs()

    def on_item_double_click(self, event):
        """Handle double-click on a log entry."""
        self.view_details()

    def view_details(self):
        """View details of the selected log entry."""
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        values = self.tree.item(item)["values"]

        # Create detail window
        detail_window = tk.Toplevel(self.root)
        detail_window.title("Log Entry Details")
        detail_window.geometry("600x400")

        # Create text widget with scrollbar
        text_frame = ttk.Frame(detail_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(
            text_frame, orient=tk.VERTICAL, command=text_widget.yview
        )
        text_widget.configure(yscrollcommand=scrollbar.set)

        # Insert details
        details = f"""ID: {values[0]}
Timestamp: {values[1]}
Level: {values[2]}
Action: {values[3]}

Details:
{values[4]}"""

        text_widget.insert(tk.END, details)
        text_widget.config(state=tk.DISABLED)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def show_context_menu(self, event):
        """Show context menu on right-click."""
        # Select the item under cursor
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def copy_selected_row(self):
        """Copy the selected row to clipboard."""
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        values = self.tree.item(item)["values"]
        row_text = "\t".join(str(v) for v in values)

        self.root.clipboard_clear()
        self.root.clipboard_append(row_text)
        self.update_status("Row copied to clipboard")

    def copy_selected_details(self):
        """Copy the details of the selected row to clipboard."""
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        values = self.tree.item(item)["values"]
        details = str(values[4])  # Details column

        self.root.clipboard_clear()
        self.root.clipboard_append(details)
        self.update_status("Details copied to clipboard")

    def update_status(self, message: str):
        """Update the status bar."""
        self.status_var.set(message)
        self.root.update_idletasks()

    def update_row_count(self, count: int):
        """Update the row count display."""
        self.row_count_var.set(f"{count} rows")

    def run(self):
        """Start the GUI application."""
        self.root.mainloop()

    def __del__(self):
        """Cleanup when the object is destroyed."""
        if hasattr(self, "following"):
            self.following = False
        if hasattr(self, "conn") and self.conn:
            self.conn.close()


def main():
    """Main function to run the log viewer."""
    parser = argparse.ArgumentParser(description="Jarvis GUI Log Viewer")
    parser.add_argument(
        "--db", default="jarvis_logs.db", help="Path to Jarvis SQLite log database"
    )
    args = parser.parse_args()

    app = LogViewerGUI(args.db)
    app.run()


if __name__ == "__main__":
    main()
