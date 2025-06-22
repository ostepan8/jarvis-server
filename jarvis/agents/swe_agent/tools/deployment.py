from ...message import Message
from ...ai_clients import BaseAIClient
from ...logger import JarvisLogger


async def docker_build(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("docker_build is not implemented yet.")


async def docker_run(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("docker_run is not implemented yet.")


async def deploy_to_server(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("deploy_to_server is not implemented yet.")


async def build_app(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("build_app is not implemented yet.")


async def run_pipeline(message: Message, ai_client: BaseAIClient, logger: JarvisLogger):
    raise NotImplementedError("run_pipeline is not implemented yet.")


async def check_pipeline_status(
    message: Message, ai_client: BaseAIClient, logger: JarvisLogger
):
    raise NotImplementedError("check_pipeline_status is not implemented yet.")
