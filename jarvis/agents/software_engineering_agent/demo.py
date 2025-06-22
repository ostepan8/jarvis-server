import asyncio

from ...ai_clients.dummy_client import DummyAIClient
from ...services.aider_service.aider_service import create_aider_service
from . import SoftwareEngineeringAgent


async def run_demo() -> None:
    """Simple demonstration of the SoftwareEngineeringAgent."""
    agent = SoftwareEngineeringAgent(
        ai_client=DummyAIClient(),
        repo_path=".",
        aider_service=create_aider_service(verbose=True),
    )

    result = await agent._execute_function("list_directory", {"path": "."})
    print("Directory listing:\n", result.get("stdout", result))

    await agent._execute_function("create_todo", {"text": "finish docs"})
    snapshot = await agent._execute_function("snapshot_memory", {})
    print("Current TODOs:", snapshot.get("todos"))

    dummy = await agent._process_dev_command("Refactor utils.py")
    print("\nDummy model response:", dummy["response"])


if __name__ == "__main__":
    asyncio.run(run_demo())
