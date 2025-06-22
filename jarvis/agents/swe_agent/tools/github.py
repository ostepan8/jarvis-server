from ...message import Message
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger


async def github_create_pr(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("github_create_pr is not implemented yet.")


async def github_merge_pr(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("github_merge_pr is not implemented yet.")
