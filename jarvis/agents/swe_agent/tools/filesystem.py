from ...message import Message
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger


async def read_file(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("read_file is not implemented yet.")


async def write_file(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("write_file is not implemented yet.")


async def list_directory(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("list_directory is not implemented yet.")
