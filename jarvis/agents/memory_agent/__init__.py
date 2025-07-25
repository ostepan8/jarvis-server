from __future__ import annotations

import json
import datetime
from typing import Any, Dict, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ...services.vector_memory import VectorMemoryService
from ...logger import JarvisLogger
from ...ai_clients.base import BaseAIClient


class MemoryAgent(NetworkAgent):
    """Agent providing shared vector memory services."""

    def __init__(
        self,
        memory_service: VectorMemoryService,
        logger: Optional[JarvisLogger] = None,
        ai_client: Optional[BaseAIClient] = None,
    ) -> None:
        super().__init__("MemoryAgent", logger, memory=memory_service)
        self.vector_memory = memory_service
        self.ai_client = ai_client

    @property
    def description(self) -> str:
        return "Stores and retrieves memories for other agents"

    @property
    def capabilities(self) -> Set[str]:
        return {"add_to_memory", "recall_from_memory"}

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Convert metadata to ChromaDB-compatible format (str, int, float only)."""
        sanitized = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float)):
                sanitized[key] = value
            elif isinstance(value, bool):
                sanitized[key] = str(value).lower()
            elif isinstance(value, list):
                # Convert lists to comma-separated strings
                sanitized[key] = ", ".join(str(item) for item in value)
            elif isinstance(value, dict):
                # Convert dicts to JSON strings
                sanitized[key] = json.dumps(value)
            elif value is None:
                sanitized[key] = ""
            else:
                # Convert other types to strings
                sanitized[key] = str(value)
        return sanitized

    async def _handle_capability_request(self, message: Message) -> None:
        capability = message.content.get("capability")
        data = message.content.get("data", {})

        if capability == "add_to_memory":
            content = data.get("prompt", "")
            metadata = data.get("metadata", {})

            if not content:
                await self.send_error(
                    message.from_agent,
                    "No content provided to remember",
                    message.request_id,
                )
                return

            try:
                # Generate enhanced metadata using AI
                enhanced_metadata = await self._generate_enhanced_metadata(
                    content, metadata
                )

                # Store with enhanced metadata
                mem_id = await self.vector_memory.add_memory(content, enhanced_metadata)

                # Generate a confirmation response using AI
                confirmation_response = await self._generate_memory_confirmation(
                    content, enhanced_metadata
                )

                await self.send_capability_response(
                    message.from_agent,
                    {
                        "response": confirmation_response,
                        "success": True,
                        "memory_id": mem_id,
                    },
                    message.request_id,
                    message.id,
                )
            except Exception as exc:
                await self.send_error(message.from_agent, str(exc), message.request_id)

        elif capability == "recall_from_memory":
            query = data.get("prompt", "")
            top_k = data.get("top_k", 5)

            if not query:
                await self.send_error(
                    message.from_agent,
                    "No query provided for recall",
                    message.request_id,
                )
                return

            try:
                # Use AI to enhance the query for better retrieval
                enhanced_query = await self._enhance_recall_query(query)

                # Get results using enhanced query
                results = await self.vector_memory.similarity_search(
                    enhanced_query, top_k=top_k
                )
                print(results, "RECALL RESULTS")

                # Filter and rank results using AI
                filtered_results = await self._filter_and_rank_results(results, query)

                summary = await self._summarize_results(filtered_results, query)

                await self.send_capability_response(
                    message.from_agent,
                    {
                        "response": summary,
                        "memories_found": (
                            len(filtered_results) if filtered_results else 0
                        ),
                    },
                    message.request_id,
                    message.id,
                )
            except Exception as exc:
                await self.send_error(message.from_agent, str(exc), message.request_id)

    async def _generate_memory_confirmation(
        self, content: str, metadata: Dict[str, Any]
    ) -> str:
        """Generate a confirmation response for stored memories."""
        if not self.ai_client:
            return f"I've remembered that: {content}"

        category = metadata.get("category", "information")
        topics = metadata.get("topics", "")

        prompt = f"""The user asked me to remember: "{content}"

    I've successfully stored this memory with the following details:
    - Category: {category}
    - Topics: {topics}

    Generate a brief, natural confirmation response that:
    - Confirms I've remembered the information
    - Shows understanding of what was stored
    - Uses a conversational tone
    - Keep it concise (1-2 sentences)

    Example responses:
    - "Got it! I've noted that your favorite cookies are Insomnia Cookies."
    - "Remembered! I've stored that preference about Insomnia Cookies for you."
    - "Perfect, I've made a note that Insomnia Cookies are your go-to favorite."

    Generate a similar confirmation response:"""

        try:
            response, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}],
                [],
            )
            return response.content.strip()
        except Exception as exc:
            if self.logger:
                self.logger.log(
                    "WARNING", "Memory confirmation generation failed", str(exc)
                )
            return f"I've remembered: {content}"

    async def _generate_enhanced_metadata(
        self, content: str, base_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Use AI to generate rich metadata for better recall."""
        if not self.ai_client:
            return self._sanitize_metadata(base_metadata)

        prompt = f"""Analyze this memory content and generate structured metadata to help with future recall:

Content: "{content}"

Generate metadata in the following categories:
1. Topics: Main subjects/themes (max 5 keywords)
2. Entities: People, places, organizations mentioned
3. Actions: What actions or events are described
4. Context: When/where/why this might be relevant
5. Intent: What the user might want to recall this for
6. Emotional_tone: The mood or sentiment
7. Urgency: How time-sensitive this information is (low/medium/high)
8. Category: General category (personal, work, learning, reminder, etc.)

Respond in JSON format only:
{{
    "topics": ["keyword1", "keyword2"],
    "entities": ["entity1", "entity2"],
    "actions": ["action1", "action2"],
    "context": "brief context description",
    "intent": "likely recall scenarios",
    "emotional_tone": "tone description",
    "urgency": "low/medium/high",
    "category": "category name"
}}"""

        try:
            response, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}],
                [],
            )

            # Parse JSON response
            ai_metadata = json.loads(response.content.strip())

            # Convert lists to comma-separated strings for ChromaDB compatibility
            ai_metadata = self._sanitize_metadata(ai_metadata)

            # Merge with base metadata
            enhanced_metadata = {
                **self._sanitize_metadata(base_metadata),
                **ai_metadata,
            }

            # Add timestamp and processing info
            enhanced_metadata.update(
                {
                    "stored_at": datetime.datetime.now().isoformat(),
                    "content_length": len(content),
                    "ai_enhanced": "true",  # String instead of boolean
                }
            )

            return enhanced_metadata

        except Exception as exc:
            if self.logger:
                self.logger.log("WARNING", "AI metadata generation failed", str(exc))
            return {**self._sanitize_metadata(base_metadata), "ai_enhanced": "false"}

    async def _enhance_recall_query(self, original_query: str) -> str:
        """Use AI to enhance the recall query with related terms and concepts."""
        if not self.ai_client:
            return original_query

        prompt = f"""Enhance this memory recall query to find more relevant results:

Original query: "{original_query}"

Generate an enhanced query that includes:
1. Synonyms and related terms
2. Different ways the concept might be expressed
3. Context that might be associated with this topic

Respond with just the enhanced query text (no explanations):"""

        try:
            response, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}],
                [],
            )

            enhanced = response.content.strip()
            return f"{original_query} {enhanced}"

        except Exception as exc:
            if self.logger:
                self.logger.log("WARNING", "Query enhancement failed", str(exc))
            return original_query

    async def _filter_and_rank_results(
        self, results: list[Dict[str, Any]], original_query: str
    ) -> list[Dict[str, Any]]:
        """Use AI to filter and rank results by relevance to the original query."""
        if not results or not self.ai_client:
            return results

        # Prepare results for AI analysis
        results_text = ""
        for i, result in enumerate(results):
            metadata = result.get("metadata", {})
            results_text += f"\nResult {i+1}:\nContent: {result.get('text', '')}\n"
            results_text += f"Topics: {metadata.get('topics', '')}\n"
            results_text += f"Category: {metadata.get('category', 'unknown')}\n"
            results_text += f"Context: {metadata.get('context', '')}\n---"

        prompt = f"""Given this user query: "{original_query}"

Rank these memory results by relevance (1 being most relevant). Consider:
- Direct content match
- Topical relevance
- Contextual appropriateness
- Likely user intent

Results to rank:
{results_text}

Respond with just the result numbers in order of relevance (e.g., "3,1,5,2,4"):"""

        try:
            response, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}],
                [],
            )

            # Parse the ranking
            ranking = [int(x.strip()) - 1 for x in response.content.strip().split(",")]

            # Reorder results based on AI ranking
            reordered = []
            for idx in ranking:
                if 0 <= idx < len(results):
                    reordered.append(results[idx])

            # Add any results not in the ranking
            ranked_indices = set(ranking)
            for i, result in enumerate(results):
                if i not in ranked_indices:
                    reordered.append(result)

            # Return top 3 most relevant
            return reordered[:3]

        except Exception as exc:
            if self.logger:
                self.logger.log("WARNING", "Result filtering failed", str(exc))
            return results[:3]

    async def _summarize_results(
        self, results: list[Dict[str, Any]] | None, query: str
    ) -> str:
        """Summarize memory search results using the attached AI client with query context."""
        if not results:
            return "I couldn't recall anything matching that, sir."

        # Include metadata context in the summary
        memory_context = []
        for i, r in enumerate(results):
            text = r.get("text", "")
            metadata = r.get("metadata", {})
            context_info = f"Category: {metadata.get('category', 'unknown')}, Context: {metadata.get('context', '')}"
            memory_context.append(f"{i+1}. {text}\n   [{context_info}]")

        memory_lines = "\n".join(memory_context)

        if not self.ai_client:
            return memory_lines

        prompt = f"""The user asked to recall: '{query}'

Based on this request, provide a helpful response using these relevant memories:

{memory_lines}

Instructions:
- Directly address what the user was looking for
- Synthesize information from multiple memories if relevant
- Use a natural, conversational tone
- If the memories contain actionable information, highlight it
- Keep the response concise but comprehensive"""

        try:
            message, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}],
                [],
            )
            return message.content
        except Exception as exc:
            if self.logger:
                self.logger.log("ERROR", "Memory summary failed", str(exc))
            return memory_lines

    async def _handle_capability_response(self, message: Message) -> None:
        # MemoryAgent does not currently send capability requests
        pass
