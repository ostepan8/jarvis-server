import datetime


class MemoDocument:
    """
    Represents a memo document in the internal memo system.

    Attributes:
        id (str): Unique identifier for the memo document.
        content (str): The content of the memo document.
        created_at (datetime): Timestamp when the memo document was created.
        updated_at (datetime): Timestamp when the memo document was last updated.
    """

    def __init__(
        self,
        id: str,
        todo_item: str,
        todo_item_answer: str,
        created_at: datetime,
        agent_name: str,
        additional_context: str = "",
    ):
        self.id = id
        self.todo_item = todo_item
        self.todo_item_answer = todo_item_answer
        self.agent_name = agent_name
        self.created_at = created_at
        self.updated_at = datetime.now()
        self.additional_context = additional_context

    def __repr__(self):
        return (
            f"MemoDocument(id={self.id}, todo_item={self.todo_item}, "
            f"todo_item_answer={self.todo_item_answer}, agent_name={self.agent_name}, "
            f"created_at={self.created_at}, updated_at={self.updated_at}, "
            f"additional_context={self.additional_context})"
        )

    def to_string_for_ai(self) -> str:
        """
        Convert the memo document to a string representation.
        This is useful for passing the document content to AI models.
        """
        return (
            f"ID: {self.id}\n"
            f"Todo Item: {self.todo_item}\n"
            f"Answer: {self.todo_item_answer}\n"
            f"Agent: {self.agent_name}\n"
            f"Created At: {self.created_at.isoformat()}\n"
            f"Updated At: {self.updated_at.isoformat()}\n"
            f"Context: {self.additional_context}"
        )
