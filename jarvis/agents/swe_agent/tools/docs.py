from ...message import Message
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger


async def search_stackoverflow(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("search_stackoverflow is not implemented yet.")


async def search_docs(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("search_docs is not implemented yet.")


async def retrieve_snippets(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("retrieve_snippets is not implemented yet.")


async def retrieve_protocols(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("retrieve_protocols is not implemented yet.")
