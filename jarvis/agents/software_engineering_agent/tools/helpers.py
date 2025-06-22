import asyncio
from typing import Any, Dict


async def run_service(func: Any, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Run a blocking service method in an executor and return a dictionary."""
    loop = asyncio.get_running_loop()

    def call() -> Dict[str, Any]:
        result = func(*args, **kwargs)
        if hasattr(result, "to_dict"):
            return result.to_dict()  # type: ignore[return-value]
        return result

    return await loop.run_in_executor(None, call)
