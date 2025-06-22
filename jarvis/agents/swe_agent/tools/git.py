from ...message import Message
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger


async def git_diff(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("git_diff is not implemented yet.")


async def git_commit(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("git_commit is not implemented yet.")


async def git_push(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("git_push is not implemented yet.")
