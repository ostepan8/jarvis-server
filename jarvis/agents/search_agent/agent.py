from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ...services.search_service import GoogleSearchService
from ...logging import JarvisLogger

if __name__ != "__main__":
    from ...ai_clients import BaseAIClient


class SearchAgent(NetworkAgent):
    """Agent that performs web searches using Google Custom Search API."""

    def __init__(
        self,
        search_service: GoogleSearchService,
        logger: Optional[JarvisLogger] = None,
        ai_client: Optional[BaseAIClient] = None,
    ) -> None:
        super().__init__("SearchAgent", logger)
        self.search_service = search_service
        self.ai_client = ai_client

    @property
    def description(self) -> str:
        return "Performs web searches to answer general knowledge questions"

    @property
    def capabilities(self) -> Set[str]:
        return {"search"}

    def _format_raw_results(
        self, results: List[Dict[str, Any]], total_results: int
    ) -> str:
        """Format search results into a readable text response."""
        if not results:
            return "No results found for your search query."

        response_parts = []
        for result in results[:3]:
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            if snippet:
                response_parts.append(f"{title}: {snippet}")
            elif title:
                response_parts.append(title)

        response_text = "\n".join(response_parts)
        if total_results > len(results):
            response_text += f"\n\n(Found {total_results} total results)"
        return response_text

    async def _synthesize_response(
        self, query: str, results: List[Dict[str, Any]], total_results: int = 0
    ) -> str:
        """Use AI client to synthesize a natural answer from search results.

        Falls back to _format_raw_results if AI client is unavailable or fails.
        """
        if total_results == 0:
            total_results = len(results)
        if not self.ai_client or not results:
            return self._format_raw_results(results, total_results)

        try:
            context_parts = []
            for r in results[:5]:
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                link = r.get("link", "")
                context_parts.append(f"- {title}: {snippet} ({link})")
            context = "\n".join(context_parts)

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant. Synthesize a concise, "
                        "natural answer to the user's question using the search "
                        "results provided. Be direct and factual. If the results "
                        "don't contain enough information, say so."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question: {query}\n\n"
                        f"Search results:\n{context}\n\n"
                        "Provide a concise answer:"
                    ),
                },
            ]
            response = await self.ai_client.weak_chat(messages, [])
            content = response[0].content if hasattr(response[0], "content") else str(response[0])
            if content and content.strip():
                return content.strip()
        except Exception as exc:
            self.logger.log(
                "WARNING",
                "Search synthesis failed, falling back to raw results",
                str(exc),
            )

        return self._format_raw_results(results, total_results)

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

            # Use AI synthesis if available, otherwise format raw results
            response_text = await self._synthesize_response(query, results, total_results)

            await self.send_capability_response(
                message.from_agent,
                {
                    "response": response_text,
                    "success": True,
                    "results": results,
                    "total_results": total_results,
                    "raw_results": results,
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
