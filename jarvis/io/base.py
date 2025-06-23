import asyncio

class InputHandler:
    async def get_input(self, prompt: str) -> str:
        """Return user input for the given prompt."""
        raise NotImplementedError

class OutputHandler:
    async def send_output(self, message: str) -> None:
        """Send a message to the user."""
        raise NotImplementedError

class ConsoleInput(InputHandler):
    async def get_input(self, prompt: str) -> str:
        # Run blocking input in a thread so the event loop isn't blocked
        return await asyncio.to_thread(input, prompt)

class ConsoleOutput(OutputHandler):
    async def send_output(self, message: str) -> None:
        print(message)
