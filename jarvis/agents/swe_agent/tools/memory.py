from ...message import Message
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger


async def generate_todo_list(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("generate_todo_list is not implemented yet.")


async def create_memory_snapshot(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("create_memory_snapshot is not implemented yet.")
