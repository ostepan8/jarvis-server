class HelloWorld:
    """A comprehensive Hello World AI agent."""

    def __init__(self, name: str = "HelloWorldAgent", version: str = "1.0"):
        """Initialize the Hello World agent with a name and version."""
        self.name = name
        self.version = version

    def greet(self) -> str:
        """Return a greeting message."""
        return f"Hello, World! I am {self.name} version {self.version}."

    def process_command(self, command: str) -> str:
        """Process a simple command and return a response."""
        if command.lower() == "status":
            return self.status_report()
        else:
            return "Command not recognized."

    def status_report(self) -> str:
        """Provide a status report of the agent."""
        return f"{self.name} is operational and running version {self.version}."
