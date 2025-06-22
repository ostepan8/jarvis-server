from ...message import Message
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger


async def run_tests(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("run_tests is not implemented yet.")


async def check_test_coverage(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("check_test_coverage is not implemented yet.")


async def watch_logs(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("watch_logs is not implemented yet.")


async def simulate_input(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("simulate_input is not implemented yet.")


async def benchmark_code(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("benchmark_code is not implemented yet.")


async def profile_code(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("profile_code is not implemented yet.")


async def sandbox_eval(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("sandbox_eval is not implemented yet.")
