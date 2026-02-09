from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import httpx

from ..logging import JarvisLogger


class GoogleSearchService:
    """Service for performing Google Custom Search API queries."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        search_engine_id: Optional[str] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        """
        Initialize Google Search Service.

        Args:
            api_key: Google Custom Search API key (or from GOOGLE_SEARCH_API_KEY env var)
            search_engine_id: Google Custom Search Engine ID (or from GOOGLE_SEARCH_ENGINE_ID env var)
            logger: Optional logger instance
        """
        self.logger = logger or JarvisLogger()
        self.api_key = api_key or os.getenv("GOOGLE_SEARCH_API_KEY")
        self.search_engine_id = search_engine_id or os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        self.base_url = "https://www.googleapis.com/customsearch/v1"

        self.logger.log(
            "INFO",
            "Google Search service initialized",
            {
                "has_api_key": bool(self.api_key),
                "has_search_engine_id": bool(self.search_engine_id),
            },
        )

    async def search(
        self, query: str, num_results: int = 5
    ) -> Dict[str, Any]:
        """
        Perform a Google Custom Search query.

        Args:
            query: Search query string
            num_results: Number of results to return (max 10)

        Returns:
            Dictionary with:
            - success: bool
            - results: List of search results with title, snippet, link
            - total_results: Total number of results found
            - error: Error message if search failed
        """
        if not self.api_key or not self.search_engine_id:
            error_msg = "Google Search API credentials not configured"
            self.logger.log("WARNING", error_msg, "")
            return {
                "success": False,
                "results": [],
                "total_results": 0,
                "error": error_msg,
            }

        # Limit num_results to API maximum
        num_results = min(num_results, 10)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {
                    "key": self.api_key,
                    "cx": self.search_engine_id,
                    "q": query,
                    "num": num_results,
                }

                self.logger.log("DEBUG", "Performing Google search", f"query: {query}")

                response = await client.get(self.base_url, params=params)
                response.raise_for_status()

                data = response.json()

                # Extract search results
                items = data.get("items", [])
                results = [
                    {
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "link": item.get("link", ""),
                    }
                    for item in items
                ]

                total_results = int(data.get("searchInformation", {}).get("totalResults", 0))

                self.logger.log(
                    "INFO",
                    "Google search completed",
                    f"query: {query}, results: {len(results)}, total: {total_results}",
                )

                return {
                    "success": True,
                    "results": results,
                    "total_results": total_results,
                    "error": None,
                }

        except httpx.HTTPStatusError as e:
            error_msg = f"Google Search API error: {e.response.status_code} - {e.response.text}"
            self.logger.log("ERROR", "Google search failed", error_msg)
            return {
                "success": False,
                "results": [],
                "total_results": 0,
                "error": error_msg,
            }
        except httpx.TimeoutException:
            error_msg = "Google Search API request timed out"
            self.logger.log("ERROR", "Google search timeout", error_msg)
            return {
                "success": False,
                "results": [],
                "total_results": 0,
                "error": error_msg,
            }
        except Exception as e:
            error_msg = f"Google Search API error: {str(e)}"
            self.logger.log("ERROR", "Google search failed", error_msg)
            return {
                "success": False,
                "results": [],
                "total_results": 0,
                "error": error_msg,
            }




