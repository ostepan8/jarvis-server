from ...message import Message
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger


async def generate_function_in_file(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("generate_function_in_file is not implemented yet.")


async def explain_code(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("explain_code is not implemented yet.")


async def refactor_code(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("refactor_code is not implemented yet.")


async def write_tests(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("write_tests is not implemented yet.")


async def document_code(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("document_code is not implemented yet.")
