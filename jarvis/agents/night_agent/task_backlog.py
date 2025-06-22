# This file will manage the task backlog for the NightAgent

class TaskBacklog:
    """Manages a list of tasks for the NightAgent."""

    def __init__(self):
        self.tasks = []

    def add_task(self, task: str) -> None:
        """Add a task to the backlog."""
        self.tasks.append(task)

    def get_tasks(self) -> list:
        """Retrieve all tasks."""
        return self.tasks

    def clear_tasks(self) -> None:
        """Clear all tasks from the backlog."""
        self.tasks.clear()
