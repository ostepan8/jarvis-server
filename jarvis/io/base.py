import asyncio

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
    def __init__(self):
        # Initialize readline history if available
        self.history_file = None
        if READLINE_AVAILABLE:
            try:
                # Try to load history from a file (optional)
                import os
                history_path = os.path.expanduser("~/.jarvis_history")
                if os.path.exists(history_path):
                    readline.read_history_file(history_path)
                self.history_file = history_path
            except Exception:
                # If history file doesn't exist or can't be loaded, continue without it
                pass
    
    async def get_input(self, prompt: str) -> str:
        # Run blocking input in a thread so the event loop isn't blocked
        # readline works with input() to provide history navigation
        def _get_input_with_history():
            try:
                result = input(prompt)
                # Add to history if readline is available
                if READLINE_AVAILABLE and result.strip():
                    try:
                        readline.add_history(result)
                        # Save history to file if available
                        if self.history_file:
                            try:
                                readline.write_history_file(self.history_file)
                            except Exception:
                                pass
                    except Exception:
                        # If readline operations fail, continue without history
                        pass
                return result
            except (EOFError, KeyboardInterrupt):
                return ""
        
        return await asyncio.to_thread(_get_input_with_history)

class ConsoleOutput(OutputHandler):
    async def send_output(self, message: str) -> None:
        # Console output is intentional for user-facing messages
        import sys
        sys.stdout.write(message + "\n")
        sys.stdout.flush()
