from __future__ import annotations

from typing import Any, Dict, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ...services.search_service import GoogleSearchService
from ...logging import JarvisLogger


class SearchAgent(NetworkAgent):
    """Agent that performs web searches using Google Custom Search API."""

    def __init__(
        self,
        search_service: GoogleSearchService,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        super().__init__("SearchAgent", logger)
        self.search_service = search_service

    @property
    def description(self) -> str:
        return "Performs web searches to answer general knowledge questions"

    @property
    def capabilities(self) -> Set[str]:
        return {"search"}

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        if capability != "search":
            return

        data = message.content.get("data", {})
        query = data.get("prompt", "")
        num_results = data.get("num_results", 5)

        if not query:
            await self.send_error(
                message.from_agent,
                "No search query provided",
                message.request_id,
            )
            return

        try:
            # Perform search
            search_results = await self.search_service.search(query, num_results)

            if not search_results.get("success"):
                error_msg = search_results.get("error", "Search failed")
                await self.send_capability_response(
                    message.from_agent,
                    {
                        "response": f"Unable to perform search: {error_msg}",
                        "success": False,
                        "results": [],
                        "error": error_msg,
                    },
                    message.request_id,
                    message.id,
                )
                return

            # Format response from search results
            results = search_results.get("results", [])
            total_results = search_results.get("total_results", 0)

            # Create a formatted response from the top results
            if results:
                # Combine top results into a readable response
                response_parts = []
                for i, result in enumerate(results[:3], 1):  # Use top 3 for response
                    title = result.get("title", "")
                    snippet = result.get("snippet", "")
                    if snippet:
                        response_parts.append(f"{title}: {snippet}")
                    elif title:
                        response_parts.append(title)

                response_text = "\n".join(response_parts)
                if total_results > len(results):
                    response_text += f"\n\n(Found {total_results} total results)"
            else:
                response_text = "No results found for your search query."

            await self.send_capability_response(
                message.from_agent,
                {
                    "response": response_text,
                    "success": True,
                    "results": results,
                    "total_results": total_results,
                    "raw_results": results,  # Include raw results for conditional logic
                },
                message.request_id,
                message.id,
            )

        except Exception as exc:
            self.logger.log("ERROR", f"SearchAgent error: {str(exc)}", "")
            await self.send_error(
                message.from_agent,
                f"Search failed: {str(exc)}",
                message.request_id,
            )

    async def _handle_capability_response(self, message: Message) -> None:
        # SearchAgent does not initiate capability requests currently
        pass

