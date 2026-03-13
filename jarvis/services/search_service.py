from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional
import httpx

from ..logging import JarvisLogger

# Scopes required for Custom Search API
_SEARCH_SCOPES = ["https://www.googleapis.com/auth/cse"]


class GoogleSearchService:
    """Service for performing Google Custom Search API queries.

    Supports two auth modes:
    - Service account (preferred): set GOOGLE_SERVICE_ACCOUNT_FILE
    - API key (fallback): set GOOGLE_SEARCH_API_KEY
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        search_engine_id: Optional[str] = None,
        service_account_file: Optional[str] = None,
        logger: Optional[JarvisLogger] = None,
    ) -> None:
        self.logger = logger or JarvisLogger()
        self.search_engine_id = search_engine_id or os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        self.base_url = "https://www.googleapis.com/customsearch/v1"

        # Prefer service account OAuth, fall back to API key
        sa_file = service_account_file or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        self._credentials = None
        self.api_key = None

        if sa_file and Path(sa_file).exists():
            try:
                from google.oauth2 import service_account
                self._credentials = service_account.Credentials.from_service_account_file(
                    sa_file, scopes=_SEARCH_SCOPES
                )
                self.logger.log("INFO", "Google Search using service account OAuth", "")
            except Exception as e:
                self.logger.log("WARNING", f"Service account init failed, falling back to API key: {e}", "")
                self.api_key = api_key or os.getenv("GOOGLE_SEARCH_API_KEY")
        else:
            self.api_key = api_key or os.getenv("GOOGLE_SEARCH_API_KEY")

        self.logger.log(
            "INFO",
            "Google Search service initialized",
            {
                "auth_mode": "service_account" if self._credentials else "api_key",
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
        if not self._credentials and not self.api_key:
            error_msg = "Google Search API credentials not configured"
            self.logger.log("WARNING", error_msg, "")
            return {
                "success": False,
                "results": [],
                "total_results": 0,
                "error": error_msg,
            }

        if not self.search_engine_id:
            error_msg = "Google Search Engine ID not configured"
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
            headers = {}
            params: Dict[str, Any] = {
                "cx": self.search_engine_id,
                "q": query,
                "num": num_results,
            }

            if self._credentials:
                # Refresh token if expired
                from google.auth.transport.requests import Request
                if not self._credentials.valid:
                    self._credentials.refresh(Request())
                headers["Authorization"] = f"Bearer {self._credentials.token}"
            else:
                params["key"] = self.api_key

            self.logger.log("DEBUG", "Performing Google search", f"query: {query}")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params, headers=headers)
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




