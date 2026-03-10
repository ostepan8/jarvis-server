import asyncio
import atexit
import os
import sys

# Try to import readline for history support (not available on Windows)
try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False


class InputHandler:
    async def get_input(self, prompt: str) -> str:
        """Return user input for the given prompt."""
        raise NotImplementedError


class OutputHandler:
    async def send_output(self, message: str) -> None:
        """Send a message to the user."""
        raise NotImplementedError


class ConsoleInput(InputHandler):
    MAX_HISTORY_LINES = 1000

    def __init__(self):
        self.history_file = None
        if READLINE_AVAILABLE:
            try:
                readline.set_history_length(self.MAX_HISTORY_LINES)
                history_path = os.path.expanduser("~/.jarvis_history")
                if os.path.exists(history_path):
                    # Skip loading if the file is unreasonably large
                    if os.path.getsize(history_path) < 1_000_000:
                        readline.read_history_file(history_path)
                self.history_file = history_path
                atexit.register(self._save_history)
            except Exception:
                pass

    def _save_history(self):
        """Write history file on process exit."""
        if self.history_file and READLINE_AVAILABLE:
            try:
                readline.write_history_file(self.history_file)
            except Exception:
                pass

    async def get_input(self, prompt: str) -> str:
        # Run blocking input in a thread so the event loop isn't blocked
        return await asyncio.to_thread(self._read_input, prompt)

    @staticmethod
    def _read_input(prompt: str) -> str:
        try:
            return input(prompt)
        except (EOFError, KeyboardInterrupt):
            return ""


class ConsoleOutput(OutputHandler):
    async def send_output(self, message: str) -> None:
        sys.stdout.write(message + "\n")
        sys.stdout.flush()
