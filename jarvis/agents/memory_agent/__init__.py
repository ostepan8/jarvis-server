from __future__ import annotations

import json
import datetime
from typing import Any, Dict, List, Optional, Set

from ..base import NetworkAgent
from ..message import Message
from ...services.vector_memory import VectorMemoryService
from ...services.fact_memory import FactMemoryService, UserFact
from ...logging import JarvisLogger
from ...ai_clients.base import BaseAIClient


class MemoryAgent(NetworkAgent):
    """Agent providing shared vector memory services and structured fact storage."""

    def __init__(
        self,
        memory_service: VectorMemoryService,
        fact_service: Optional[FactMemoryService] = None,
        logger: Optional[JarvisLogger] = None,
        ai_client: Optional[BaseAIClient] = None,
    ) -> None:
        super().__init__("MemoryAgent", logger, memory=memory_service)
        self.vector_memory = memory_service
        self.fact_service = fact_service or FactMemoryService()
        self.ai_client = ai_client

    @property
    def description(self) -> str:
        return "Stores and retrieves memories for other agents"

    @property
    def capabilities(self) -> Set[str]:
        return {
            "add_to_memory",
            "recall_from_memory",
            "store_fact",
            "get_facts",
            "extract_facts",
            "search_facts",
        }

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
        user_id = data.get("user_id")  # Extract user_id from request

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

                # Store with enhanced metadata and user_id
                mem_id = await self.vector_memory.add_memory(
                    content, enhanced_metadata, user_id=user_id
                )

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

        elif capability == "store_fact":
            fact_text = data.get("fact_text", "")
            category = data.get("category", "general")
            entity = data.get("entity")
            confidence = data.get("confidence", 1.0)
            source = data.get("source", "explicit")
            context = data.get("context")

            if not fact_text or user_id is None:
                await self.send_error(
                    message.from_agent,
                    "fact_text and user_id are required",
                    message.request_id,
                )
                return

            try:
                # Check for conflicts
                conflicts = self.fact_service.check_conflicts(
                    user_id, fact_text, category
                )

                fact_id = self.fact_service.add_fact(
                    user_id=user_id,
                    fact_text=fact_text,
                    category=category,
                    entity=entity,
                    confidence=confidence,
                    source=source,
                    context=context,
                )

                # Also store in vector memory for semantic search
                await self.vector_memory.add_memory(
                    fact_text,
                    {
                        "fact_id": fact_id,
                        "category": category,
                        "entity": entity,
                        "type": "fact",
                    },
                    user_id=user_id,
                )

                conflict_msg = ""
                if conflicts:
                    conflict_msg = (
                        f" Note: Found {len(conflicts)} potentially conflicting facts."
                    )

                await self.send_capability_response(
                    message.from_agent,
                    {
                        "response": f"Fact stored successfully.{conflict_msg}",
                        "fact_id": fact_id,
                        "conflicts": len(conflicts),
                    },
                    message.request_id,
                    message.id,
                )
            except Exception as exc:
                await self.send_error(message.from_agent, str(exc), message.request_id)

        elif capability == "get_facts":
            category = data.get("category")
            entity = data.get("entity")
            limit = data.get("limit", 10)

            if user_id is None:
                await self.send_error(
                    message.from_agent, "user_id is required", message.request_id
                )
                return

            try:
                facts = self.fact_service.get_facts(
                    user_id=user_id,
                    category=category,
                    entity=entity,
                    limit=limit,
                )
                await self.send_capability_response(
                    message.from_agent,
                    {
                        "facts": [
                            {
                                "id": f.id,
                                "text": f.fact_text,
                                "category": f.category,
                                "entity": f.entity,
                                "confidence": f.confidence,
                            }
                            for f in facts
                        ],
                        "count": len(facts),
                    },
                    message.request_id,
                    message.id,
                )
            except Exception as exc:
                await self.send_error(message.from_agent, str(exc), message.request_id)

        elif capability == "extract_facts":
            conversation_text = data.get("conversation_text", "")

            if not conversation_text or user_id is None:
                await self.send_error(
                    message.from_agent,
                    "conversation_text and user_id are required",
                    message.request_id,
                )
                return

            try:
                extracted_facts = await self._extract_facts_from_conversation(
                    conversation_text, user_id
                )
                await self.send_capability_response(
                    message.from_agent,
                    {
                        "extracted_facts": extracted_facts,
                        "count": len(extracted_facts),
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

                # Get results using enhanced query, scoped to user if provided
                results = await self.vector_memory.similarity_search(
                    enhanced_query, top_k=top_k, user_id=user_id
                )

                # Also search structured facts if user_id is provided
                fact_results = []
                if user_id is not None:
                    facts = self.fact_service.search_facts(user_id, query, limit=top_k)
                    fact_results = [
                        {
                            "text": f.fact_text,
                            "metadata": {
                                "category": f.category,
                                "entity": f.entity,
                                "type": "fact",
                            },
                        }
                        for f in facts
                    ]

                # Combine vector and fact results
                all_results = results + fact_results

                # Filter and rank results using AI
                filtered_results = await self._filter_and_rank_results(
                    all_results, query
                )

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

    async def _extract_facts_from_conversation(
        self, conversation_text: str, user_id: int
    ) -> List[Dict[str, Any]]:
        """Use AI to extract structured facts from conversation text."""
        if not self.ai_client:
            return []

        prompt = f"""Analyze this conversation and extract specific facts about the user:

Conversation:
{conversation_text}

Extract facts that represent:
1. Personal information (name, age, location, occupation, etc.)
2. Preferences (likes, dislikes, favorite things)
3. Relationships (family, friends, colleagues mentioned)
4. Important memories or experiences
5. Skills, hobbies, or interests
6. Goals or plans

For each fact, provide:
- fact_text: The fact as a clear statement
- category: personal_info, preference, relationship, memory, skill, goal
- entity: What/who the fact is about (if applicable)
- confidence: 0.0 to 1.0 based on certainty

Respond ONLY with a JSON array of fact objects:
[
    {{
        "fact_text": "The user's name is Alice",
        "category": "personal_info",
        "entity": "user",
        "confidence": 1.0
    }},
    {{
        "fact_text": "Alice loves Italian food",
        "category": "preference",
        "entity": "food",
        "confidence": 0.9
    }}
]

If no facts can be extracted, return an empty array []."""

        try:
            response, _ = await self.ai_client.weak_chat(
                [{"role": "user", "content": prompt}], []
            )

            # Parse JSON response
            facts_json = json.loads(response.content.strip())
            if not isinstance(facts_json, list):
                return []

            # Store extracted facts
            stored_facts = []
            for fact_data in facts_json:
                try:
                    fact_id = self.fact_service.add_fact(
                        user_id=user_id,
                        fact_text=fact_data.get("fact_text", ""),
                        category=fact_data.get("category", "general"),
                        entity=fact_data.get("entity"),
                        confidence=float(fact_data.get("confidence", 0.8)),
                        source="extracted",
                        context=f"Extracted from conversation",
                    )

                    # Also store in vector memory
                    await self.vector_memory.add_memory(
                        fact_data.get("fact_text", ""),
                        {
                            "fact_id": fact_id,
                            "category": fact_data.get("category", "general"),
                            "entity": fact_data.get("entity"),
                            "type": "fact",
                            "source": "extracted",
                        },
                        user_id=user_id,
                    )

                    stored_facts.append(
                        {
                            "fact_id": fact_id,
                            "fact_text": fact_data.get("fact_text", ""),
                            "category": fact_data.get("category", "general"),
                        }
                    )
                except Exception as exc:
                    if self.logger:
                        self.logger.log(
                            "WARNING", f"Failed to store extracted fact", str(exc)
                        )

            return stored_facts

        except Exception as exc:
            if self.logger:
                self.logger.log(
                    "ERROR", "Fact extraction from conversation failed", str(exc)
                )
            return []

    async def _handle_capability_response(self, message: Message) -> None:
        # MemoryAgent does not currently send capability requests
        pass
