from .backlog_task import BacklogTask

class TaskBacklog:
    """Manages a list of tasks for the NightAgent."""

    def __init__(self):
        self.tasks = []

    def add_task(self, task: BacklogTask) -> None:
        """Add a task to the backlog."""
        self.tasks.append(task)

    def get_tasks(self) -> list[BacklogTask]:
        """Retrieve all tasks."""
        return self.tasks

    def clear_tasks(self) -> None:
        """Clear all tasks from the backlog."""
        self.tasks.clear()
