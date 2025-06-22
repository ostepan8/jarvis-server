from ..base import NetworkAgent

class NightAgent(NetworkAgent):
    """Agent responsible for running background processes during off-hours."""

    def __init__(self, name: str, logger: Optional[JarvisLogger] = None) -> None:
        super().__init__(name, logger)
        self.task_backlog = []

    def add_task(self, task: str) -> None:
        """Add a task to the backlog."""
        self.task_backlog.append(task)

    async def run_tasks(self) -> None:
        """Execute all tasks in the backlog."""
        while self.task_backlog:
            task = self.task_backlog.pop(0)
            # Implement task execution logic here
            print(f"Executing task: {task}")
